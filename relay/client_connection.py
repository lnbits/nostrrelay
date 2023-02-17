import json
import time
from typing import Any, Awaitable, Callable, List, Optional

from fastapi import WebSocket
from loguru import logger

from lnbits.helpers import urlsafe_short_hash

from ..crud import (
    create_event,
    delete_events,
    get_event,
    get_events,
    mark_events_deleted,
)
from .event import NostrEvent, NostrEventType
from .event_validator import EventValidator
from .filter import NostrFilter
from .relay import RelaySpec


class NostrClientConnection:
    def __init__(self, relay_id: str, websocket: WebSocket):
        self.websocket = websocket
        self.relay_id = relay_id
        self.filters: List[NostrFilter] = []
        self.pubkey: Optional[str] = None  # set if authenticated
        self._auth_challenge: Optional[str] = None
        self._auth_challenge_created_at = 0

        self.event_validator = EventValidator(self.relay_id)

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

    def init_callbacks(self, broadcast_event: Callable, get_client_config: Callable):
        setattr(self, "broadcast_event", broadcast_event)
        setattr(self, "get_client_config", get_client_config)
        setattr(self.event_validator, "get_client_config", get_client_config)

    async def notify_event(self, event: NostrEvent) -> bool:
        if self._is_direct_message_for_other(event):
            return False

        for filter in self.filters:
            if filter.matches(event):
                resp = event.serialize_response(filter.subscription_id)
                await self._send_msg(resp)
                return True
        return False

    def _is_direct_message_for_other(self, event: NostrEvent) -> bool:
        """
        Direct messages are not inteded to be boradcast (even if encrypted).
        If the server requires AUTH for kind '4' then direct message will be sent only to the intended client.
        """
        if not event.is_direct_message:
            return False
        if not self.config.event_requires_auth(event.kind):
            return False
        if not self.pubkey:
            return True
        if event.has_tag_value("p", self.pubkey):
            return False
        return True

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
            valid, message = self.event_validator.validate_auth_event(
                e, self._auth_challenge
            )
            if not valid:
                resp_nip20 += [valid, message]
                await self._send_msg(resp_nip20)
                return None
            self.pubkey = e.pubkey
            return None

        if not self.pubkey and self.config.event_requires_auth(e.kind):
            await self._send_msg(["AUTH", self._current_auth_challenge()])
            resp_nip20 += [
                False,
                f"restricted: Relay requires authentication for events of kind '{e.kind}'",
            ]
            await self._send_msg(resp_nip20)
            return None

        publisher_pubkey = self.pubkey if self.pubkey else e.pubkey
        valid, message = await self.event_validator.validate_write(e, publisher_pubkey)
        if not valid:
            resp_nip20 += [valid, message]
            await self._send_msg(resp_nip20)
            return None

        try:
            if e.is_replaceable_event:
                await delete_events(
                    self.relay_id,
                    NostrFilter(kinds=[e.kind], authors=[e.pubkey], until=e.created_at),
                )
            if not e.is_ephemeral_event:
                await create_event(self.relay_id, e, self.pubkey)
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
    def config(self) -> RelaySpec:
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
        if not self.pubkey and self.config.require_auth_filter:
            return [["AUTH", self._current_auth_challenge()]]

        filter.subscription_id = subscription_id
        self._remove_filter(subscription_id)
        if self._can_add_filter():
            return [
                [
                    "NOTICE",
                    f"Maximum number of filters ({self.config.max_client_filters}) exceeded.",
                ]
            ]

        filter.enforce_limit(self.config.limit_per_filter)
        self.filters.append(filter)
        events = await get_events(self.relay_id, filter)
        events = [e for e in events if not self._is_direct_message_for_other(e)]
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
            self.config.max_client_filters != 0
            and len(self.filters) >= self.config.max_client_filters
        )

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
