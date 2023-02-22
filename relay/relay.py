import json
from sqlite3 import Row
from typing import Optional

from pydantic import BaseModel, Field


class Spec(BaseModel):
    class Config:
        allow_population_by_field_name = True


class FilterSpec(Spec):
    max_client_filters = Field(0, alias="maxClientFilters")
    limit_per_filter = Field(1000, alias="limitPerFilter")


class EventSpec(Spec):
    max_events_per_hour = Field(0, alias="maxEventsPerHour")

    created_at_days_past = Field(0, alias="createdAtDaysPast")
    created_at_hours_past = Field(0, alias="createdAtHoursPast")
    created_at_minutes_past = Field(0, alias="createdAtMinutesPast")
    created_at_seconds_past = Field(0, alias="createdAtSecondsPast")

    created_at_days_future = Field(0, alias="createdAtDaysFuture")
    created_at_hours_future = Field(0, alias="createdAtHoursFuture")
    created_at_minutes_future = Field(0, alias="createdAtMinutesFuture")
    created_at_seconds_future = Field(0, alias="createdAtSecondsFuture")

    @property
    def created_at_in_past(self) -> int:
        return (
            self.created_at_days_past * 86400
            + self.created_at_hours_past * 3600
            + self.created_at_minutes_past * 60
            + self.created_at_seconds_past
        )

    @property
    def created_at_in_future(self) -> int:
        return (
            self.created_at_days_future * 86400
            + self.created_at_hours_future * 3600
            + self.created_at_minutes_future * 60
            + self.created_at_seconds_future
        )


class StorageSpec(Spec):
    free_storage_value = Field(1, alias="freeStorageValue")
    free_storage_unit = Field("MB", alias="freeStorageUnit")
    full_storage_action = Field("prune", alias="fullStorageAction")

    @property
    def free_storage_bytes_value(self):
        value = self.free_storage_value * 1024
        if self.free_storage_unit == "MB":
            value *= 1024
        return value


class AuthSpec(Spec):
    require_auth_events = Field(False, alias="requireAuthEvents")
    skiped_auth_events = Field([], alias="skipedAuthEvents")
    forced_auth_events = Field([], alias="forcedAuthEvents")
    require_auth_filter = Field(False, alias="requireAuthFilter")

    def event_requires_auth(self, kind: int) -> bool:
        if self.require_auth_events:
            return kind not in self.skiped_auth_events
        return kind in self.forced_auth_events


class PaymentSpec(Spec):
    is_paid_relay = Field(False, alias="isPaidRelay")
    cost_to_join = Field(0, alias="costToJoin")

    storage_cost_value = Field(0, alias="storageCostValue")
    storage_cost_unit = Field("MB", alias="storageCostUnit")


class WalletSpec(Spec):
    wallet = Field("")


class RelayPublicSpec(FilterSpec, EventSpec, StorageSpec, PaymentSpec):
    domain: str = ""

    @property
    def is_read_only_relay(self):
        self.free_storage_value == 0 and not self.is_paid_relay


class RelaySpec(RelayPublicSpec, WalletSpec, AuthSpec):
    pass


class NostrRelay(BaseModel):
    id: str
    name: str
    description: Optional[str]
    pubkey: Optional[str]
    contact: Optional[str]
    active: bool = False

    config: "RelaySpec" = RelaySpec()

    @property
    def is_free_to_join(self):
        return not self.config.is_paid_relay or self.config.cost_to_join == 0

    @classmethod
    def from_row(cls, row: Row) -> "NostrRelay":
        relay = cls(**dict(row))
        relay.config = RelaySpec(**json.loads(row["meta"]))
        return relay

    @classmethod
    def info(
        cls,
    ) -> dict:
        return {
            "contact": "https://t.me/lnbits",
            "supported_nips": [1, 2, 4, 9, 11, 15, 16, 20, 22, 28, 42],
            "software": "LNbits",
            "version": "",
        }
