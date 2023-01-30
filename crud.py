import json
from typing import Any, List, Optional

from . import db
from .models import NostrEvent, NostrFilter


async def create_event(relay_id: str, e: NostrEvent):
    await db.execute(
        """
        INSERT INTO nostrrelay.events (
            relay_id,
            id,
            pubkey,
            created_at,
            kind,
            content,
            sig
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO NOTHING
        """,
        (relay_id, e.id, e.pubkey, e.created_at, e.kind, e.content, e.sig),
    )

    # todo: optimize with bulk insert
    for tag in e.tags:
        name, value, *rest = tag
        extra = json.dumps(rest) if rest else None
        await create_event_tags(relay_id, e.id, name, value, extra)


async def get_events(relay_id: str, filter: NostrFilter) -> List[NostrEvent]:
    values: List[Any] = []
    query = "SELECT id, pubkey, created_at, kind, content, sig FROM nostrrelay.events"
    if len(filter.e) or len(filter.p):
        query += " INNER JOIN nostrrelay.event_tags ON nostrrelay.events.id = nostrrelay.event_tags.event_id WHERE"
        if len(filter.e):
            values += filter.e
            e_s = ",".join(["?"] * len(filter.e))
            query += f" nostrrelay.event_tags.value in ({e_s}) AND nostrrelay.event_tags.name = 'e'"

        if len(filter.p):
            values += filter.p
            p_s = ",".join(["?"] * len(filter.p))
            and_op = " AND " if len(filter.e) else ""
            query += f"{and_op} nostrrelay.event_tags.value in ({p_s}) AND nostrrelay.event_tags.name = 'p'"
        query += " AND nostrrelay.events.relay_id = ?"
    else:
        query += " WHERE nostrrelay.events.relay_id = ?"

    values.append(relay_id)

    if len(filter.ids) != 0:
        ids = ",".join(["?"] * len(filter.ids))
        query += f" AND id IN ({ids})"
        values += filter.ids
    if len(filter.authors) != 0:
        authors = ",".join(["?"] * len(filter.authors))
        query += f" AND pubkey IN ({authors})"
        values += filter.authors
    if len(filter.kinds) != 0:
        kinds = ",".join(["?"] * len(filter.kinds))
        query += f" AND kind IN ({kinds})"
        values += filter.kinds
    if filter.since:
        query += " AND created_at >= ?"
        values += [filter.since]
    if filter.until:
        query += " AND created_at <= ?"
        values += [filter.until]

    query += " ORDER BY created_at DESC"
    if filter.limit and type(filter.limit) == int and filter.limit > 0:
        query += f" LIMIT {filter.limit}"

    rows = await db.fetchall(query, tuple(values))

    events = []
    for row in rows:
        event = NostrEvent.from_row(row)
        event.tags = await get_event_tags(relay_id, event.id)
        events.append(event)

    return events


async def create_event_tags(
    relay_id: str, event_id: str, tag_name: str, tag_value: str, extra_values: Optional[str]
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


async def get_event_tags(
    relay_id: str, event_id: str
) -> List[List[str]]:
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
