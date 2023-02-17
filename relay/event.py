import hashlib
import json
from enum import Enum
from sqlite3 import Row
from typing import List

from pydantic import BaseModel
from secp256k1 import PublicKey


class NostrEventType(str, Enum):
    EVENT = "EVENT"
    REQ = "REQ"
    CLOSE = "CLOSE"
    AUTH = "AUTH"


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

    @property
    def size_bytes(self) -> int:
        s = json.dumps(dict(self), separators=(",", ":"), ensure_ascii=False)
        return len(s.encode())

    @property
    def is_replaceable_event(self) -> bool:
        return self.kind in [0, 3, 41] or (self.kind >= 10000 and self.kind < 20000)

    @property
    def is_auth_response_event(self) -> bool:
        return self.kind == 22242

    @property
    def is_direct_message(self) -> bool:
        return self.kind == 4

    @property
    def is_delete_event(self) -> bool:
        return self.kind == 5

    @property
    def is_regular_event(self) -> bool:
        return self.kind >= 1000 and self.kind < 10000

    @property
    def is_ephemeral_event(self) -> bool:
        return self.kind >= 20000 and self.kind < 30000

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

    def tag_values(self, tag_name: str) -> List[str]:
        return [t[1] for t in self.tags if t[0] == tag_name]

    def has_tag_value(self, tag_name: str, tag_value: str) -> bool:
        return tag_value in self.tag_values(tag_name)

    def is_direct_message_for_pubkey(self, pubkey: str) -> bool:
        return self.is_direct_message and self.has_tag_value("p", pubkey)

    @classmethod
    def from_row(cls, row: Row) -> "NostrEvent":
        return cls(**dict(row))
