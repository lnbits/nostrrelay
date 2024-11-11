from typing import Optional

from pydantic import BaseModel


class BuyOrder(BaseModel):
    action: str
    relay_id: str
    pubkey: str
    units_to_buy: int = 0

    def is_valid_action(self) -> bool:
        return self.action in ["join", "storage"]


class NostrPartialAccount(BaseModel):
    relay_id: str
    pubkey: str
    allowed: Optional[bool] = None
    blocked: Optional[bool] = None


class NostrAccount(BaseModel):
    pubkey: str
    relay_id: str
    sats: int = 0
    storage: int = 0
    paid_to_join: bool = False
    allowed: bool = False
    blocked: bool = False

    @property
    def can_join(self):
        """If an account is explicitly allowed then it does not need to pay"""
        return self.paid_to_join or self.allowed

    @classmethod
    def null_account(cls) -> "NostrAccount":
        return NostrAccount(pubkey="", relay_id="")


class NostrEventTags(BaseModel):
    relay_id: str
    event_id: str
    name: str
    value: str
    extra: Optional[str] = None
