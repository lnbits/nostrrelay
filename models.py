import hashlib
import json
from enum import Enum
from sqlite3 import Row
from typing import Any, List, Optional, Tuple

from pydantic import BaseModel, Field
from secp256k1 import PublicKey



class ClientConfig(BaseModel):
    max_client_filters = Field(0, alias="maxClientFilters")
    allowed_public_keys = Field([], alias="allowedPublicKeys")
    blocked_public_keys = Field([], alias="blockedPublicKeys")

    class Config:
        allow_population_by_field_name = True
class RelayConfig(ClientConfig):
    is_paid_relay = Field(False, alias="isPaidRelay")
    wallet = Field("")
    cost_to_join = Field(0, alias="costToJoin")
    free_storage = Field(0, alias="freeStorage")
    storage_cost_per_kb = Field(0, alias="storageCostPerKb")


class NostrRelay(BaseModel):
    id: str
    name: str
    description: Optional[str]
    pubkey: Optional[str]
    contact: Optional[str]
    active: bool = False

    config: "RelayConfig" = RelayConfig()


    @classmethod
    def from_row(cls, row: Row) -> "NostrRelay":
        relay = cls(**dict(row))
        relay.config = RelayConfig(**json.loads(row["meta"]))
        return relay

    @classmethod
    def info(cls,) -> dict:
        return {
            "contact": "https://t.me/lnbits",
            "supported_nips": [1, 9, 11, 15, 20],
            "software": "LNbits",
            "version": "",
        }


class NostrEventType(str, Enum):
    EVENT = "EVENT"
    REQ = "REQ"
    CLOSE = "CLOSE"


class NostrEvent(BaseModel):
    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: List[List[str]] = []
    content: str = ""
    sig: str

    def serialize(self) -> List:
        return [0, self.pubkey, self.created_at, self.kind, self.tags, self.content]

    def serialize_json(self) -> str:
        e = self.serialize()
        return json.dumps(e, separators=(",", ":"), ensure_ascii=False)

    @property
    def event_id(self) -> str:
        data = self.serialize_json()
        id = hashlib.sha256(data.encode()).hexdigest()
        return id

    def is_replaceable_event(self) -> bool:
        return self.kind in [0, 3]

    def is_delete_event(self) -> bool:
        return self.kind == 5

    def check_signature(self):
        event_id = self.event_id
        if self.id != event_id:
            raise ValueError(
                f"Invalid event id. Expected: '{event_id}' got '{self.id}'"
            )
        try:
            pub_key = PublicKey(bytes.fromhex("02" + self.pubkey), True)
        except Exception:
            raise ValueError(
                f"Invalid public key: '{self.pubkey}' for event '{self.id}'"
            )

        valid_signature = pub_key.schnorr_verify(
            bytes.fromhex(event_id), bytes.fromhex(self.sig), None, raw=True
        )
        if not valid_signature:
            raise ValueError(f"Invalid signature: '{self.sig}' for event '{self.id}'")

    def serialize_response(self, subscription_id):
        return [NostrEventType.EVENT, subscription_id, dict(self)]

    @classmethod
    def from_row(cls, row: Row) -> "NostrEvent":
        return cls(**dict(row))


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

        found_e_tag = self.tag_in_list(e.tags, "e")
        found_p_tag = self.tag_in_list(e.tags, "p")
        if not found_e_tag or not found_p_tag:
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

    def to_sql_components(self, relay_id: str) -> Tuple[List[str], List[str], List[Any]]:
        inner_joins: List[str] = []
        where = ["deleted=false", "nostrrelay.events.relay_id = ?"]
        values: List[Any] = [relay_id]

        if len(self.e):
            values += self.e
            e_s = ",".join(["?"] * len(self.e))
            inner_joins.append("INNER JOIN nostrrelay.event_tags e_tags ON nostrrelay.events.id = e_tags.event_id")
            where.append(f" (e_tags.value in ({e_s}) AND e_tags.name = 'e')")

        if len(self.p):
            values += self.p
            p_s = ",".join(["?"] * len(self.p))
            inner_joins.append("INNER JOIN nostrrelay.event_tags p_tags ON nostrrelay.events.id = p_tags.event_id")
            where.append(f" p_tags.value in ({p_s}) AND p_tags.name = 'p'")

        if len(self.ids) != 0:
            ids = ",".join(["?"] * len(self.ids))
            where.append(f"id IN ({ids})")
            values += self.ids

        if len(self.authors) != 0:
            authors = ",".join(["?"] * len(self.authors))
            where.append(f"pubkey IN ({authors})")
            values += self.authors

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
        

        return inner_joins, where, values
