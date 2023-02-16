import json
import time
from typing import Any, Awaitable, Callable, List, Optional, Tuple

from fastapi import WebSocket
from loguru import logger

from lnbits.helpers import urlsafe_short_hash

from .crud import (
    create_event,
    delete_events,
    get_account,
    get_config_for_all_active_relays,
    get_event,
    get_events,
    get_storage_for_public_key,
    mark_events_deleted,
    prune_old_events,
)
from .helpers import extract_domain
from .models import NostrAccount, NostrEvent, NostrEventType, NostrFilter, RelaySpec


class NostrClientManager:
    def __init__(self: "NostrClientManager"):
        self._clients: dict = {}
        self._active_relays: dict = {}
        self._is_ready = False

    async def add_client(self, c: "NostrClientConnection") -> bool:
        if not self._is_ready:
            await self.init_relays()

        if not (await self._allow_client(c)):
            return False

        self._set_client_callbacks(c)
        self.clients(c.relay_id).append(c)

        return True

    def remove_client(self, c: "NostrClientConnection"):
        self.clients(c.relay_id).remove(c)

    async def broadcast_event(self, source: "NostrClientConnection", event: NostrEvent):
        for client in self.clients(source.relay_id):
            await client.notify_event(event)

    async def init_relays(self):
        self._active_relays = await get_config_for_all_active_relays()
        self._is_ready = True

    async def enable_relay(self, relay_id: str, config: RelaySpec):
        self._is_ready = True
        self._active_relays[relay_id] = config

    async def disable_relay(self, relay_id: str):
        await self._stop_clients_for_relay(relay_id)
        if relay_id in self._active_relays:
            del self._active_relays[relay_id]

    def get_relay_config(self, relay_id: str) -> RelaySpec:
        return self._active_relays[relay_id]

    def clients(self, relay_id: str) -> List["NostrClientConnection"]:
        if relay_id not in self._clients:
            self._clients[relay_id] = []
        return self._clients[relay_id]

    async def _stop_clients_for_relay(self, relay_id: str):
        for client in self.clients(relay_id):
            if client.relay_id == relay_id:
                await client.stop(reason=f"Relay '{relay_id}' has been deactivated.")

    async def _allow_client(self, c: "NostrClientConnection") -> bool:
        if c.relay_id not in self._active_relays:
            await c.stop(reason=f"Relay '{c.relay_id}' is not active")
            return False
        return True

    def _set_client_callbacks(self, client):
        setattr(client, "broadcast_event", self.broadcast_event)

        def get_client_config() -> RelaySpec:
            return self.get_relay_config(client.relay_id)

        setattr(client, "get_client_config", get_client_config)


class NostrClientConnection:
    def __init__(self, relay_id: str, websocket: WebSocket):
        self.websocket = websocket
        self.relay_id = relay_id
        self.filters: List[NostrFilter] = []
        self.authenticated = False
        self.pubkey: Optional[str] = None
        self._auth_challenge: Optional[str] = None
        self._auth_challenge_created_at = 0

        self._last_event_timestamp = 0  # in hours
        self._event_count_per_timestamp = 0

        self.broadcast_event: Optional[
            Callable[[NostrClientConnection, NostrEvent], Awaitable[None]]
        ] = None
        self.get_client_config: Optional[Callable[[], RelaySpec]] = None

    async def start(self):
        await self.websocket.accept()
        while True:
            json_data = await self.websocket.receive_text()
            try:
                data = json.loads(json_data)

                resp = await self._handle_message(data)
                for r in resp:
                    await self._send_msg(r)
            except Exception as e:
                logger.warning(e)

    async def stop(self, reason: Optional[str]):
        message = reason if reason else "Server closed webocket"
        try:
            await self._send_msg(["NOTICE", message])
        except:
            pass

        try:
            await self.websocket.close(reason=reason)
        except:
            pass

    async def notify_event(self, event: NostrEvent) -> bool:
        for filter in self.filters:
            if filter.matches(event):
                resp = event.serialize_response(filter.subscription_id)
                await self._send_msg(resp)
                return True
        return False

    async def _broadcast_event(self, e: NostrEvent):
        if self.broadcast_event:
            await self.broadcast_event(self, e)

    async def _handle_message(self, data: List) -> List:
        if len(data) < 2:
            return []

        message_type = data[0]
        if message_type == NostrEventType.EVENT:
            await self._handle_event(NostrEvent.parse_obj(data[1]))
            return []
        if message_type == NostrEventType.REQ:
            if len(data) != 3:
                return []
            return await self._handle_request(data[1], NostrFilter.parse_obj(data[2]))
        if message_type == NostrEventType.CLOSE:
            self._handle_close(data[1])
        if message_type == NostrEventType.AUTH:
            await self._handle_auth()

        return []

    async def _handle_event(self, e: NostrEvent):
        logger.info(f"nostr event: [{e.kind}, {e.pubkey}, '{e.content}']")
        resp_nip20: List[Any] = ["OK", e.id]

        if e.is_auth_response_event:
            valid, message = self._validate_auth_event(e)
            if not valid:
                resp_nip20 += [valid, message]
                await self._send_msg(resp_nip20)
                return None
            self.authenticated = True
            self.pubkey = e.pubkey
            return None

        if not self.authenticated and self.client_config.event_requires_auth(e.kind):
            await self._send_msg(["AUTH", self._current_auth_challenge()])
            resp_nip20 += [
                False,
                f"restricted: Relay requires authentication for events of kind '{e.kind}'",
            ]
            await self._send_msg(resp_nip20)
            return None

        valid, message = await self._validate_write(e)
        if not valid:
            resp_nip20 += [valid, message]
            await self._send_msg(resp_nip20)
            return None

        try:
            if e.is_replaceable_event:
                await delete_events(
                    self.relay_id, NostrFilter(kinds=[e.kind], authors=[e.pubkey])
                )
            await create_event(self.relay_id, e)
            await self._broadcast_event(e)

            if e.is_delete_event:
                await self._handle_delete_event(e)
            resp_nip20 += [True, ""]
        except Exception as ex:
            logger.debug(ex)
            event = await get_event(self.relay_id, e.id)
            # todo: handle NIP20 in detail
            message = "error: failed to create event"
            resp_nip20 += [event != None, message]

        await self._send_msg(resp_nip20)

    @property
    def client_config(self) -> RelaySpec:
        if not self.get_client_config:
            raise Exception("Client not ready!")
        return self.get_client_config()

    async def _send_msg(self, data: List):
        await self.websocket.send_text(json.dumps(data))

    async def _handle_delete_event(self, event: NostrEvent):
        # NIP 09
        filter = NostrFilter(authors=[event.pubkey])
        filter.ids = [t[1] for t in event.tags if t[0] == "e"]
        events_to_delete = await get_events(self.relay_id, filter, False)
        ids = [e.id for e in events_to_delete if not e.is_delete_event]
        await mark_events_deleted(self.relay_id, NostrFilter(ids=ids))

    async def _handle_request(self, subscription_id: str, filter: NostrFilter) -> List:
        if not self.authenticated and self.client_config.require_auth_filter:
            return [["AUTH", self._current_auth_challenge()]]

        filter.subscription_id = subscription_id
        self._remove_filter(subscription_id)
        if self._can_add_filter():
            return [
                [
                    "NOTICE",
                    f"Maximum number of filters ({self.client_config.max_client_filters}) exceeded.",
                ]
            ]

        filter.enforce_limit(self.client_config.limit_per_filter)
        self.filters.append(filter)
        events = await get_events(self.relay_id, filter)
        serialized_events = [
            event.serialize_response(subscription_id) for event in events
        ]
        resp_nip15 = ["EOSE", subscription_id]
        serialized_events.append(resp_nip15)
        return serialized_events

    def _remove_filter(self, subscription_id: str):
        self.filters = [f for f in self.filters if f.subscription_id != subscription_id]

    def _handle_close(self, subscription_id: str):
        self._remove_filter(subscription_id)

    async def _handle_auth(self):
        await self._send_msg(["AUTH", self._current_auth_challenge()])

    def _can_add_filter(self) -> bool:
        return (
            self.client_config.max_client_filters != 0
            and len(self.filters) >= self.client_config.max_client_filters
        )

    def _validate_auth_event(self, e: NostrEvent) -> Tuple[bool, str]:
        valid, message = self._validate_event(e)
        if not valid:
            return (valid, message)

        relay_tag = e.tag_values("relay")
        challenge_tag = e.tag_values("challenge")
        if len(relay_tag) == 0 or len(challenge_tag) == 0:
            return False, "error: NIP42 tags are missing for auth event"

        if self.client_config.domain != extract_domain(relay_tag[0]):
            return False, "error: wrong relay domain  for auth event"

        if self._auth_challenge != challenge_tag[0]:
            return False, "error: wrong chanlange value for auth event"

        return True, ""

    async def _validate_write(self, e: NostrEvent) -> Tuple[bool, str]:
        valid, message = self._validate_event(e)
        if not valid:
            return (valid, message)

        valid, message = await self._validate_storage(e.pubkey, e.size_bytes)
        if not valid:
            return (valid, message)

        return True, ""

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
        if self.client_config.is_read_only_relay:
            return False, "Cannot write event, relay is read-only"

        account = await get_account(self.relay_id, pubkey)
        if not account:
            account = NostrAccount.null_account()

        if account.blocked:
            return (
                False,
                f"Public key '{pubkey}' is not allowed in relay '{self.relay_id}'!",
            )

        if not account.can_join and self.client_config.is_paid_relay:
            return False, f"This is a paid relay: '{self.relay_id}'"

        stored_bytes = await get_storage_for_public_key(self.relay_id, pubkey)
        total_available_storage = (
            account.storage + self.client_config.free_storage_bytes_value
        )
        if (stored_bytes + event_size_bytes) <= total_available_storage:
            return True, ""

        if self.client_config.full_storage_action == "block":
            return (
                False,
                f"Cannot write event, no more storage available for public key: '{pubkey}'",
            )

        if event_size_bytes > total_available_storage:
            return False, "Message is too large. Not enough storage available for it."

        await prune_old_events(self.relay_id, pubkey, event_size_bytes)

        return True, ""

    def _exceeded_max_events_per_hour(self) -> bool:
        if self.client_config.max_events_per_hour == 0:
            return False

        current_time = round(time.time() / 3600)
        if self._last_event_timestamp == current_time:
            self._event_count_per_timestamp += 1
        else:
            self._last_event_timestamp = current_time
            self._event_count_per_timestamp = 0

        return (
            self._event_count_per_timestamp > self.client_config.max_events_per_hour
        )

    def _created_at_in_range(self, created_at: int) -> Tuple[bool, str]:
        current_time = round(time.time())
        if self.client_config.created_at_in_past != 0:
            if created_at < (current_time - self.client_config.created_at_in_past):
                return False, "created_at is too much into the past"
        if self.client_config.created_at_in_future != 0:
            if created_at > (current_time + self.client_config.created_at_in_future):
                return False, "created_at is too much into the future"
        return True, ""

    def _auth_challenge_expired(self):
        if self._auth_challenge_created_at == 0:
            return True
        current_time_seconds = round(time.time())
        chanllenge_max_age_seconds = 300  # 5 min
        return (
            current_time_seconds - self._auth_challenge_created_at
        ) >= chanllenge_max_age_seconds

    def _current_auth_challenge(self):
        if self._auth_challenge_expired():
            self._auth_challenge = self.relay_id + ":" + urlsafe_short_hash()
            self._auth_challenge_created_at = round(time.time())
        return self._auth_challenge
