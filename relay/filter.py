from typing import Optional

from pydantic import BaseModel, Field

from .event import NostrEvent


class NostrFilter(BaseModel):
    e: list[str] = Field(default=[], alias="#e")
    p: list[str] = Field(default=[], alias="#p")
    d: list[str] = Field(default=[], alias="#d")
    ids: list[str] = []
    authors: list[str] = []
    kinds: list[int] = []
    subscription_id: Optional[str] = None
    since: Optional[int] = None
    until: Optional[int] = None
    limit: Optional[int] = None

    def matches(self, e: NostrEvent) -> bool:
        # todo: starts with
        if len(self.ids) != 0 and e.id not in self.ids:
            return False
        if len(self.authors) != 0 and e.pubkey not in self.authors:
            return False
        if len(self.kinds) != 0 and e.kind not in self.kinds:
            return False

        if self.since and e.created_at < self.since:
            return False
        if self.until and self.until > 0 and e.created_at > self.until:
            return False

        # Check tag filters - only fail if filter is specified and no match found
        if not self.tag_in_list(e.tags, "e"):
            return False
        if not self.tag_in_list(e.tags, "p"):
            return False
        if not self.tag_in_list(e.tags, "d"):
            return False

        return True

    def tag_in_list(self, event_tags, tag_name) -> bool:
        filter_tags = dict(self).get(tag_name, [])
        if len(filter_tags) == 0:
            return True

        event_tag_values = [t[1] for t in event_tags if t[0] == tag_name]

        common_tags = [
            event_tag for event_tag in event_tag_values if event_tag in filter_tags
        ]
        if len(common_tags) == 0:
            return False
        return True

    def is_empty(self):
        return (
            len(self.ids) == 0
            and len(self.authors) == 0
            and len(self.kinds) == 0
            and len(self.e) == 0
            and len(self.p) == 0
            and (not self.since)
            and (not self.until)
        )

    def enforce_limit(self, limit: int):
        if not self.limit or self.limit > limit:
            self.limit = limit

    def to_sql_components(self, relay_id: str) -> tuple[list[str], list[str], dict]:
        inner_joins: list[str] = []
        where = ["deleted=false", "nostrrelay.events.relay_id = :relay_id"]
        values: dict = {"relay_id": relay_id}

        if len(self.e):
            e_s = ",".join([f"'{e}'" for e in self.e])
            inner_joins.append(
                "INNER JOIN nostrrelay.event_tags e_tags "
                "ON nostrrelay.events.id = e_tags.event_id"
            )
            where.append(f" (e_tags.value in ({e_s}) AND e_tags.name = 'e')")

        if len(self.p):
            p_s = ",".join([f"'{p}'" for p in self.p])
            inner_joins.append(
                "INNER JOIN nostrrelay.event_tags p_tags "
                "ON nostrrelay.events.id = p_tags.event_id"
            )
            where.append(f" p_tags.value in ({p_s}) AND p_tags.name = 'p'")

        if len(self.d):
            d_s = ",".join([f"'{d}'" for d in self.d])
            d_join = (
                "INNER JOIN nostrrelay.event_tags d_tags"
                " ON nostrrelay.events.id = d_tags.event_id"
            )
            d_where = f" d_tags.value in ({d_s}) AND d_tags.name = 'd'"

            inner_joins.append(d_join)
            where.append(d_where)

        if len(self.ids) != 0:
            ids = ",".join([f"'{_id}'" for _id in self.ids])
            where.append(f"id IN ({ids})")

        if len(self.authors) != 0:
            authors = ",".join([f"'{author}'" for author in self.authors])
            where.append(f"pubkey IN ({authors})")

        if len(self.kinds) != 0:
            kinds = ",".join([f"'{kind}'" for kind in self.kinds])
            where.append(f"kind IN ({kinds})")

        if self.since:
            where.append("created_at >= :since")
            values["since"] = self.since

        if self.until:
            where.append("created_at < :until")
            values["until"] = self.until

        return inner_joins, where, values
