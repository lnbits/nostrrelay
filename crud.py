import json

from lnbits.db import Database

from .models import NostrAccount, NostrEventTags
from .relay.event import NostrEvent
from .relay.filter import NostrFilter
from .relay.relay import NostrRelay, RelayPublicSpec

db = Database("ext_nostrrelay")


async def create_relay(relay: NostrRelay) -> NostrRelay:
    await db.insert("nostrrelay.relays", relay)
    return relay


async def update_relay(relay: NostrRelay) -> NostrRelay:
    await db.update("nostrrelay.relays", relay, "WHERE user_id = :user_id AND id = :id")
    return relay


async def get_relay(user_id: str, relay_id: str) -> NostrRelay | None:
    return await db.fetchone(
        "SELECT * FROM nostrrelay.relays WHERE user_id = :user_id AND id = :id",
        {"user_id": user_id, "id": relay_id},
        NostrRelay,
    )


async def get_relay_by_id(relay_id: str) -> NostrRelay | None:
    """Note: it does not require `user_id`. Can read any relay. Use it with care."""
    return await db.fetchone(
        "SELECT * FROM nostrrelay.relays WHERE id = :id",
        {"id": relay_id},
        NostrRelay,
    )


async def get_relays(user_id: str) -> list[NostrRelay]:
    return await db.fetchall(
        "SELECT * FROM nostrrelay.relays WHERE user_id = :user_id ORDER BY id ASC",
        {"user_id": user_id},
        NostrRelay,
    )


async def get_config_for_all_active_relays() -> dict:
    relays = await db.fetchall(
        "SELECT * FROM nostrrelay.relays WHERE active = true",
        model=NostrRelay,
    )
    active_relay_configs = {}
    for relay in relays:
        active_relay_configs[relay.id] = relay.meta

    return active_relay_configs


async def get_public_relay(relay_id: str) -> dict | None:
    relay = await db.fetchone(
        "SELECT * FROM nostrrelay.relays WHERE id = :id",
        {"id": relay_id},
        NostrRelay,
    )
    if not relay:
        return None

    return {
        **NostrRelay.info(),
        "id": relay.id,
        "name": relay.name,
        "description": relay.description,
        "pubkey": relay.pubkey,
        "contact": relay.contact,
        "config": RelayPublicSpec(**relay.meta.dict()).dict(by_alias=True),
    }


async def delete_relay(user_id: str, relay_id: str):
    await db.execute(
        "DELETE FROM nostrrelay.relays WHERE user_id = :user_id AND id = :id",
        {"user_id": user_id, "id": relay_id},
    )


async def create_event(event: NostrEvent):
    event_ = await get_event(event.relay_id, event.id)
    if event_:
        return None
    await db.insert("nostrrelay.events", event)

    # todo: optimize with bulk insert
    for tag in event.tags:
        name, value, *rest = tag
        extra = json.dumps(rest) if rest else None
        _tag = NostrEventTags(
            relay_id=event.relay_id,
            event_id=event.id,
            name=name,
            value=value,
            extra=extra,
        )
        await create_event_tags(_tag)


async def get_events(
    relay_id: str, nostr_filter: NostrFilter, include_tags=True
) -> list[NostrEvent]:

    inner_joins, where, values = nostr_filter.to_sql_components(relay_id)
    query = f"""
        SELECT * FROM nostrrelay.events
        {" ".join(inner_joins)}
        WHERE { " AND ".join(where)}
        ORDER BY created_at DESC
        """

    # todo: check & enforce range
    if nostr_filter.limit and nostr_filter.limit > 0:
        query += f" LIMIT {nostr_filter.limit}"

    events = await db.fetchall(query, values, NostrEvent)

    for event in events:
        if include_tags:
            event.tags = await get_event_tags(relay_id, event.id)

    return events


async def get_event(relay_id: str, event_id: str) -> NostrEvent | None:
    event = await db.fetchone(
        "SELECT * FROM nostrrelay.events WHERE relay_id = :relay_id AND id = :id",
        {"relay_id": relay_id, "id": event_id},
        NostrEvent,
    )
    if not event:
        return None
    event.tags = await get_event_tags(relay_id, event_id)
    return event


async def get_storage_for_public_key(relay_id: str, publisher_pubkey: str) -> int:
    """
    Returns the storage space in bytes for all the events of a public key.
    Deleted events are also counted
    """
    row: dict = await db.fetchone(
        """
        SELECT SUM(size) as sum FROM nostrrelay.events
        WHERE relay_id = :relay_id AND publisher = :publisher GROUP BY publisher
        """,
        {"relay_id": relay_id, "publisher": publisher_pubkey},
    )

    if not row:
        return 0

    return round(row["sum"])


async def get_prunable_events(relay_id: str, pubkey: str) -> list[tuple[str, int]]:
    """
    Return the oldest 10 000 events. Only the `id` and the size are returned,
    so the data size should be small
    """
    events = await db.fetchall(
        """
        SELECT * FROM nostrrelay.events
        WHERE relay_id = :relay_id AND pubkey = :pubkey
        ORDER BY created_at ASC LIMIT 10000
        """,
        {"relay_id": relay_id, "pubkey": pubkey},
        NostrEvent,
    )

    return [(event.id, event.size_bytes) for event in events]


async def mark_events_deleted(relay_id: str, nostr_filter: NostrFilter):
    if nostr_filter.is_empty():
        return None
    _, where, values = nostr_filter.to_sql_components(relay_id)

    await db.execute(
        f"UPDATE nostrrelay.events SET deleted=true WHERE {' AND '.join(where)}",
        values,
    )


async def delete_events(relay_id: str, nostr_filter: NostrFilter):
    if nostr_filter.is_empty():
        return None
    inner_joins, where, values = nostr_filter.to_sql_components(relay_id)

    if inner_joins:
        # Use subquery for DELETE operations with JOINs
        subquery = f"""
            SELECT nostrrelay.events.id FROM nostrrelay.events
            {" ".join(inner_joins)}
            WHERE {" AND ".join(where)}
        """
        query = f"DELETE FROM nostrrelay.events WHERE id IN ({subquery})"
    else:
        # Simple DELETE without JOINs
        query = f"DELETE FROM nostrrelay.events WHERE {' AND '.join(where)}"

    await db.execute(query, values)
    # todo: delete tags


# move to services
async def prune_old_events(relay_id: str, pubkey: str, space_to_regain: int):
    prunable_events = await get_prunable_events(relay_id, pubkey)
    prunable_event_ids = []
    size = 0

    for pe in prunable_events:
        prunable_event_ids.append(pe[0])
        size += pe[1]

        if size > space_to_regain:
            break

    await delete_events(relay_id, NostrFilter(ids=prunable_event_ids))


async def delete_all_events(relay_id: str):
    await db.execute(
        "DELETE from nostrrelay.events WHERE relay_id = :id",
        {"id": relay_id},
    )
    # todo: delete tags


async def create_event_tags(tag: NostrEventTags):
    await db.insert("nostrrelay.event_tags", tag)


async def get_event_tags(relay_id: str, event_id: str) -> list[list[str]]:
    _tags = await db.fetchall(
        """
        SELECT * FROM nostrrelay.event_tags
        WHERE relay_id = :relay_id and event_id = :event_id
        """,
        {"relay_id": relay_id, "event_id": event_id},
        model=NostrEventTags,
    )

    tags: list[list[str]] = []
    for tag in _tags:
        _tag = [tag.name, tag.value]
        if tag.extra:
            _tag += json.loads(tag.extra)
        tags.append(_tag)

    return tags


async def create_account(account: NostrAccount) -> NostrAccount:
    await db.insert("nostrrelay.accounts", account)
    return account


async def update_account(account: NostrAccount) -> NostrAccount:
    await db.update(
        "nostrrelay.accounts",
        account,
        "WHERE relay_id = :relay_id AND pubkey = :pubkey",
    )
    return account


async def delete_account(relay_id: str, pubkey: str):
    await db.execute(
        """
        DELETE FROM nostrrelay.accounts
        WHERE relay_id = :id AND pubkey = :pubkey
        """,
        {"id": relay_id, "pubkey": pubkey},
    )


async def get_account(
    relay_id: str,
    pubkey: str,
) -> NostrAccount | None:
    return await db.fetchone(
        """
        SELECT * FROM nostrrelay.accounts
        WHERE relay_id = :id AND pubkey = :pubkey
        """,
        {"id": relay_id, "pubkey": pubkey},
        NostrAccount,
    )


async def get_accounts(
    relay_id: str,
    allowed=True,
    blocked=False,
) -> list[NostrAccount]:
    if not allowed and not blocked:
        return []
    return await db.fetchall(
        """
        SELECT * FROM nostrrelay.accounts
        WHERE relay_id = :id AND allowed = :allowed OR blocked = :blocked
        """,
        {"id": relay_id, "allowed": allowed, "blocked": blocked},
        NostrAccount,
    )
