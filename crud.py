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
        """,
        (relay_id, e.id, e.pubkey, e.created_at, e.kind, e.content, e.sig),
    )

    # todo: optimize with bulk insert
    for tag in e.tags:
        name, value, *rest = tag
        extra = json.dumps(rest) if rest else None
        await create_event_tags(relay_id, e.id, name, value, extra)


async def get_events(relay_id: str, filter: NostrFilter, include_tags = True) -> List[NostrEvent]:
    values, query = build_select_events_query(relay_id, filter)

    rows = await db.fetchall(query, tuple(values))

    events = []
    for row in rows:
        event = NostrEvent.from_row(row)
        if include_tags:
            event.tags = await get_event_tags(relay_id, event.id)
        events.append(event)

    return events


async def get_event(relay_id: str, id: str) -> Optional[NostrEvent]:
    row = await db.fetchone("SELECT * FROM nostrrelay.events WHERE relay_id = ? AND id = ?", (relay_id, id,))
    if not row:
        return None

    event = NostrEvent.from_row(row)
    event.tags = await get_event_tags(relay_id, id)
    return event

async def mark_events_deleted(relay_id: str, id_list: List[str] = []):
    if len(id_list) == 0:
        return None
    ids = ",".join(["?"] * len(id_list))
    values = [relay_id] + id_list
    await db.execute(f"UPDATE nostrrelay.events SET deleted=true WHERE relay_id = ? AND id IN ({ids})", tuple(values))


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


def build_select_events_query(relay_id:str, filter:NostrFilter):
    inner_joins, where, values = build_where_clause(relay_id, filter)

    query = f"""
        SELECT id, pubkey, created_at, kind, content, sig 
        FROM nostrrelay.events 
        {" ".join(inner_joins)} 
        WHERE { " AND ".join(where)}
        ORDER BY created_at DESC
        """

    if filter.limit and filter.limit > 0:
        query += f" LIMIT {filter.limit}"

    return values, query

def build_where_clause(relay_id:str, filter:NostrFilter):
    inner_joins = []
    where = ["deleted=false", "nostrrelay.events.relay_id = ?"]
    values: List[Any] = [relay_id]

    if len(filter.e):
        values += filter.e
        e_s = ",".join(["?"] * len(filter.e))
        inner_joins.append("INNER JOIN nostrrelay.event_tags e_tags ON nostrrelay.events.id = e_tags.event_id")
        where.append(f" (e_tags.value in ({e_s}) AND e_tags.name = 'e')")

    if len(filter.p):
        values += filter.p
        p_s = ",".join(["?"] * len(filter.p))
        inner_joins.append("INNER JOIN nostrrelay.event_tags p_tags ON nostrrelay.events.id = p_tags.event_id")
        where.append(f" p_tags.value in ({p_s}) AND p_tags.name = 'p'")

    if len(filter.ids) != 0:
        ids = ",".join(["?"] * len(filter.ids))
        where.append(f"id IN ({ids})")
        values += filter.ids

    if len(filter.authors) != 0:
        authors = ",".join(["?"] * len(filter.authors))
        where.append(f"pubkey IN ({authors})")
        values += filter.authors

    if len(filter.kinds) != 0:
        kinds = ",".join(["?"] * len(filter.kinds))
        where.append(f"kind IN ({kinds})")
        values += filter.kinds

    if filter.since:
        where.append("reated_at >= ?")
        values += [filter.since]

    if filter.until:
        where.append("created_at <= ?")
        values += [filter.until]
    

    return inner_joins, where, values