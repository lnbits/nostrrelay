from sqlite3 import Row
from typing import Optional

from pydantic import BaseModel


class BuyOrder(BaseModel):
    action: str
    relay_id: str
    pubkey: str
    units_to_buy = 0

    def is_valid_action(self):
        return self.action in ["join", "storage"]


class NostrPartialAccount(BaseModel):
    relay_id: str
    pubkey: str
    allowed: Optional[bool]
    blocked: Optional[bool]


class NostrAccount(BaseModel):
    pubkey: str
    allowed = False
    blocked = False
    sats = 0
    storage = 0
    paid_to_join = False

    @property
    def can_join(self):
        """If an account is explicitly allowed then it does not need to pay"""
        return self.paid_to_join or self.allowed

    @classmethod
    def null_account(cls) -> "NostrAccount":
        return NostrAccount(pubkey="")

    @classmethod
    def from_row(cls, row: Row) -> "NostrAccount":
        return cls(**dict(row))
