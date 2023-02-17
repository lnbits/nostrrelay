import time
from typing import Callable, Optional, Tuple

from ..crud import get_account, get_storage_for_public_key, prune_old_events
from ..helpers import extract_domain
from ..models import NostrAccount
from .event import NostrEvent
from .relay import RelaySpec


class EventValidator:
    def __init__(self, relay_id: str):
        self.relay_id = relay_id

        self._last_event_timestamp = 0  # in hours
        self._event_count_per_timestamp = 0

        self.get_client_config: Optional[Callable[[], RelaySpec]] = None

    async def validate_write(
        self, e: NostrEvent, publisher_pubkey: str
    ) -> Tuple[bool, str]:
        valid, message = self._validate_event(e)
        if not valid:
            return (valid, message)

        if e.is_ephemeral_event:
            return True, ""

        valid, message = await self._validate_storage(publisher_pubkey, e.size_bytes)
        if not valid:
            return (valid, message)

        return True, ""

    def validate_auth_event(
        self, e: NostrEvent, auth_challenge: Optional[str]
    ) -> Tuple[bool, str]:
        valid, message = self._validate_event(e)
        if not valid:
            return (valid, message)

        relay_tag = e.tag_values("relay")
        challenge_tag = e.tag_values("challenge")
        if len(relay_tag) == 0 or len(challenge_tag) == 0:
            return False, "error: NIP42 tags are missing for auth event"

        if self.config.domain != extract_domain(relay_tag[0]):
            return False, "error: wrong relay domain for auth event"

        if auth_challenge != challenge_tag[0]:
            return False, "error: wrong chanlange value for auth event"

        return True, ""

    @property
    def config(self) -> RelaySpec:
        if not self.get_client_config:
            raise Exception("EventValidator not ready!")
        return self.get_client_config()

    def _validate_event(self, e: NostrEvent) -> Tuple[bool, str]:
        if self._exceeded_max_events_per_hour():
            return False, f"Exceeded max events per hour limit'!"

        try:
            e.check_signature()
        except ValueError:
            return False, "invalid: wrong event `id` or `sig`"

        in_range, message = self._created_at_in_range(e.created_at)
        if not in_range:
            return False, message

        return True, ""

    async def _validate_storage(
        self, pubkey: str, event_size_bytes: int
    ) -> Tuple[bool, str]:
        if self.config.is_read_only_relay:
            return False, "Cannot write event, relay is read-only"

        account = await get_account(self.relay_id, pubkey)
        if not account:
            account = NostrAccount.null_account()

        if account.blocked:
            return (
                False,
                f"Public key '{pubkey}' is not allowed in relay '{self.relay_id}'!",
            )

        if not account.can_join and self.config.is_paid_relay:
            return False, f"This is a paid relay: '{self.relay_id}'"

        stored_bytes = await get_storage_for_public_key(self.relay_id, pubkey)
        total_available_storage = account.storage + self.config.free_storage_bytes_value
        if (stored_bytes + event_size_bytes) <= total_available_storage:
            return True, ""

        if self.config.full_storage_action == "block":
            return (
                False,
                f"Cannot write event, no more storage available for public key: '{pubkey}'",
            )

        if event_size_bytes > total_available_storage:
            return False, "Message is too large. Not enough storage available for it."

        await prune_old_events(self.relay_id, pubkey, event_size_bytes)

        return True, ""

    def _exceeded_max_events_per_hour(self) -> bool:
        if self.config.max_events_per_hour == 0:
            return False

        current_time = round(time.time() / 3600)
        if self._last_event_timestamp == current_time:
            self._event_count_per_timestamp += 1
        else:
            self._last_event_timestamp = current_time
            self._event_count_per_timestamp = 0

        return self._event_count_per_timestamp > self.config.max_events_per_hour

    def _created_at_in_range(self, created_at: int) -> Tuple[bool, str]:
        current_time = round(time.time())
        if self.config.created_at_in_past != 0:
            if created_at < (current_time - self.config.created_at_in_past):
                return False, "created_at is too much into the past"
        if self.config.created_at_in_future != 0:
            if created_at > (current_time + self.config.created_at_in_future):
                return False, "created_at is too much into the future"
        return True, ""
