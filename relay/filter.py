from typing import Any, List, Optional, Tuple

from pydantic import BaseModel, Field

from .event import NostrEvent

#from loguru import logger

class NostrFilter(BaseModel):
    subscription_id: Optional[str]

    ids: List[str] = []
    authors: List[str] = []
    kinds: List[int] = []
    e: List[str] = Field([], alias="#e")
    p: List[str] = Field([], alias="#p")
    since: Optional[int]
    until: Optional[int]
    limit: Optional[int]

    def matches(self, e: NostrEvent) -> bool:

        #logger.debug(f"NostrFilter::matches: e.id:{e.id}, self.ids:{self.ids}, e.pubkey:{e.pubkey}, self.authors:{self.authors}")
        if len(self.ids) != 0 and not e.id.startswith(tuple(self.ids)):
            return False
        if len(self.authors) != 0 and not e.pubkey.startswith(tuple(self.authors)):
            return False
        if len(self.kinds) != 0 and e.kind not in self.kinds:
            return False

        if self.since and e.created_at < self.since:
            return False
        if self.until and self.until > 0 and e.created_at > self.until:
            return False

        found_e_tag = self.tag_in_list(e.tags, "e")
        found_p_tag = self.tag_in_list(e.tags, "p")
        if not found_e_tag or not found_p_tag:
            return False

        #logger.debug(f"NostrFilter::matches: found a match")
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

    def to_sql_components(
        self, relay_id: str
    ) -> Tuple[List[str], List[str], List[Any]]:
        inner_joins: List[str] = []
        where = ["deleted=false", "nostrrelay.events.relay_id = ?"]
        values: List[Any] = [relay_id]

        if len(self.e):
            values += self.e
            e_s = ",".join(["?"] * len(self.e))
            inner_joins.append(
                "INNER JOIN nostrrelay.event_tags e_tags ON nostrrelay.events.id = e_tags.event_id"
            )
            where.append(f" (e_tags.value in ({e_s}) AND e_tags.name = 'e')")

        if len(self.p):
            values += self.p
            p_s = ",".join(["?"] * len(self.p))
            inner_joins.append(
                "INNER JOIN nostrrelay.event_tags p_tags ON nostrrelay.events.id = p_tags.event_id"
            )
            where.append(f" p_tags.value in ({p_s}) AND p_tags.name = 'p'")

        if len(self.ids) != 0:
            ids = ",".join(tuple([id + "%" for id in self.ids]))
            where.append(f"id LIKE ANY ('{{{ids}}}')")

        if len(self.authors) != 0:
            authors = ",".join(tuple([key + "%" for key in self.authors]))
            where.append(f"pubkey LIKE ANY ('{{{authors}}}')")

        if len(self.kinds) != 0:
            kinds = ",".join(["?"] * len(self.kinds))
            where.append(f"kind IN ({kinds})")
            values += self.kinds

        if self.since:
            where.append("created_at >= ?")
            values += [self.since]

        if self.until:
            where.append("created_at < ?")
            values += [self.until]

        #logger.debug(f"NosterFilter::to_sql_components: inner_joins:{inner_joins}, where:{where}, values:{values}")

        return inner_joins, where, values
