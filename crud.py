import json
from typing import List, Optional, Tuple

from . import db
from .models import NostrAccount
from .relay.event import NostrEvent
from .relay.filter import NostrFilter
from .relay.relay import NostrRelay, RelayPublicSpec, RelaySpec

########################## RELAYS ####################


async def create_relay(user_id: str, r: NostrRelay) -> NostrRelay:
    await db.execute(
        """
        INSERT INTO nostrrelay.relays (user_id, id, name, description, pubkey, contact, meta)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            r.id,
            r.name,
            r.description,
            r.pubkey,
            r.contact,
            json.dumps(dict(r.config)),
        ),
    )
    relay = await get_relay(user_id, r.id)
    assert relay, "Created relay cannot be retrieved"
    return relay


async def update_relay(user_id: str, r: NostrRelay) -> NostrRelay:
    await db.execute(
        """
        UPDATE nostrrelay.relays
        SET (name, description, pubkey, contact, active, meta) = (?, ?, ?, ?, ?, ?)
        WHERE user_id = ? AND id = ?
        """,
        (
            r.name,
            r.description,
            r.pubkey,
            r.contact,
            r.active,
            json.dumps(dict(r.config)),
            user_id,
            r.id,
        ),
    )

    return r


async def get_relay(user_id: str, relay_id: str) -> Optional[NostrRelay]:
    row = await db.fetchone(
        """SELECT * FROM nostrrelay.relays WHERE user_id = ? AND id = ?""",
        (
            user_id,
            relay_id,
        ),
    )

    return NostrRelay.from_row(row) if row else None


async def get_relay_by_id(relay_id: str) -> Optional[NostrRelay]:
    """Note: it does not require `user_id`. Can read any relay. Use it with care."""
    row = await db.fetchone(
        """SELECT * FROM nostrrelay.relays WHERE id = ?""",
        (relay_id,),
    )

    return NostrRelay.from_row(row) if row else None


async def get_relays(user_id: str) -> List[NostrRelay]:
    rows = await db.fetchall(
        """SELECT * FROM nostrrelay.relays WHERE user_id = ? ORDER BY id ASC""",
        (user_id,),
    )

    return [NostrRelay.from_row(row) for row in rows]


async def get_config_for_all_active_relays() -> dict:
    rows = await db.fetchall(
        "SELECT id, meta FROM nostrrelay.relays WHERE active = true",
    )
    active_relay_configs = {}
    for r in rows:
        active_relay_configs[r["id"]] = RelaySpec(
            **json.loads(r["meta"])
        )  # todo: from_json

    return active_relay_configs


async def get_public_relay(relay_id: str) -> Optional[dict]:
    row = await db.fetchone(
        """SELECT * FROM nostrrelay.relays WHERE id = ?""", (relay_id,)
    )

    if not row:
        return None

    relay = NostrRelay.from_row(row)
    return {
        **NostrRelay.info(),
        "id": relay.id,
        "name": relay.name,
        "description": relay.description,
        "pubkey": relay.pubkey,
        "contact": relay.contact,
        "config": RelayPublicSpec(**dict(relay.config)).dict(by_alias=True),
    }


async def delete_relay(user_id: str, relay_id: str):
    await db.execute(
        """DELETE FROM nostrrelay.relays WHERE user_id = ? AND id = ?""",
        (
            user_id,
            relay_id,
        ),
    )


########################## EVENTS ####################
async def create_event(relay_id: str, e: NostrEvent, publisher: Optional[str]):
    publisher = publisher if publisher else e.pubkey
    await db.execute(
        """
        INSERT INTO nostrrelay.events (
            relay_id,
            publisher,
            id,
            pubkey,
            created_at,
            kind,
            content,
            sig,
            size
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            relay_id,
            publisher,
            e.id,
            e.pubkey,
            e.created_at,
            e.kind,
            e.content,
            e.sig,
            e.size_bytes,
        ),
    )

    # todo: optimize with bulk insert
    for tag in e.tags:
        name, value, *rest = tag
        extra = json.dumps(rest) if rest else None
        await create_event_tags(relay_id, e.id, name, value, extra)


async def get_events(
    relay_id: str, filter: NostrFilter, include_tags=True
) -> List[NostrEvent]:
    query, values = build_select_events_query(relay_id, filter)

    rows = await db.fetchall(query, tuple(values))

    events = []
    for row in rows:
        event = NostrEvent.from_row(row)
        if include_tags:
            event.tags = await get_event_tags(relay_id, event.id)
        events.append(event)

    return events


async def get_event(relay_id: str, id: str) -> Optional[NostrEvent]:
    row = await db.fetchone(
        "SELECT * FROM nostrrelay.events WHERE relay_id = ? AND id = ?",
        (
            relay_id,
            id,
        ),
    )
    if not row:
        return None

    event = NostrEvent.from_row(row)
    event.tags = await get_event_tags(relay_id, id)
    return event


async def get_storage_for_public_key(relay_id: str, publisher_pubkey: str) -> int:
    """Returns the storage space in bytes for all the events of a public key. Deleted events are also counted"""

    row = await db.fetchone(
        "SELECT SUM(size) as sum FROM nostrrelay.events WHERE relay_id = ? AND publisher = ? GROUP BY publisher",
        (
            relay_id,
            publisher_pubkey,
        ),
    )
    if not row:
        return 0

    return round(row["sum"])


async def get_prunable_events(relay_id: str, pubkey: str) -> List[Tuple[str, int]]:
    """Return the oldest 10 000 events. Only the `id` and the size are returned, so the data size should be small"""
    query = """
            SELECT id, size FROM nostrrelay.events
            WHERE relay_id = ? AND pubkey = ?
            ORDER BY created_at ASC LIMIT 10000
        """

    rows = await db.fetchall(query, (relay_id, pubkey))

    return [(r["id"], r["size"]) for r in rows]


async def mark_events_deleted(relay_id: str, filter: NostrFilter):
    if filter.is_empty():
        return None
    _, where, values = filter.to_sql_components(relay_id)

    await db.execute(
        f"""UPDATE nostrrelay.events SET deleted=true WHERE {" AND ".join(where)}""",
        tuple(values),
    )


async def delete_events(relay_id: str, filter: NostrFilter):
    if filter.is_empty():
        return None
    _, where, values = filter.to_sql_components(relay_id)

    query = f"""DELETE from nostrrelay.events WHERE {" AND ".join(where)}"""
    await db.execute(query, tuple(values))
    # todo: delete tags


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
    query = "DELETE from nostrrelay.events WHERE relay_id = ?"
    await db.execute(query, (relay_id,))
    # todo: delete tags


async def create_event_tags(
    relay_id: str,
    event_id: str,
    tag_name: str,
    tag_value: str,
    extra_values: Optional[str],
):
    await db.execute(
        """
        INSERT INTO nostrrelay.event_tags (
            relay_id,
            event_id,
            name,
            value,
            extra
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (relay_id, event_id, tag_name, tag_value, extra_values),
    )


async def get_event_tags(relay_id: str, event_id: str) -> List[List[str]]:
    rows = await db.fetchall(
        "SELECT * FROM nostrrelay.event_tags WHERE relay_id = ? and event_id = ?",
        (relay_id, event_id),
    )

    tags: List[List[str]] = []
    for row in rows:
        tag = [row["name"], row["value"]]
        extra = row["extra"]
        if extra:
            tag += json.loads(extra)
        tags.append(tag)

    return tags


def build_select_events_query(relay_id: str, filter: NostrFilter):
    inner_joins, where, values = filter.to_sql_components(relay_id)

    query = f"""
        SELECT id, pubkey, created_at, kind, content, sig 
        FROM nostrrelay.events 
        {" ".join(inner_joins)} 
        WHERE { " AND ".join(where)}
        ORDER BY created_at DESC
        """

    # todo: check & enforce range
    if filter.limit and filter.limit > 0:
        query += f" LIMIT {filter.limit}"

    return query, values


########################## ACCOUNTS ####################


async def create_account(relay_id: str, a: NostrAccount) -> NostrAccount:
    await db.execute(
        """
        INSERT INTO nostrrelay.accounts (relay_id, pubkey, sats, storage, paid_to_join, allowed, blocked)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            relay_id,
            a.pubkey,
            a.sats,
            a.storage,
            a.paid_to_join,
            a.allowed,
            a.blocked,
        ),
    )
    account = await get_account(relay_id, a.pubkey)
    assert account, "Created account cannot be retrieved"
    return account


async def update_account(relay_id: str, a: NostrAccount) -> NostrAccount:
    await db.execute(
        """
        UPDATE nostrrelay.accounts
        SET (sats, storage, paid_to_join, allowed, blocked) = (?, ?, ?, ?, ?)
        WHERE relay_id = ? AND pubkey = ?
        """,
        (a.sats, a.storage, a.paid_to_join, a.allowed, a.blocked, relay_id, a.pubkey),
    )

    return a


async def get_account(
    relay_id: str,
    pubkey: str,
) -> Optional[NostrAccount]:
    row = await db.fetchone(
        "SELECT * FROM nostrrelay.accounts WHERE relay_id = ? AND pubkey = ?",
        (relay_id, pubkey),
    )

    return NostrAccount.from_row(row) if row else None


async def get_accounts(
    relay_id: str,
    allowed=True,
    blocked=False,
) -> List[NostrAccount]:
    rows = await db.fetchall(
        "SELECT * FROM nostrrelay.accounts WHERE relay_id = ? AND allowed = ? AND blocked = ?",
        (relay_id, allowed, blocked),
    )

    return [NostrAccount.from_row(row) for row in rows]
