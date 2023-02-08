import json
from typing import Any, Callable, List, Optional

from fastapi import WebSocket
from loguru import logger

from .crud import (
    create_event,
    delete_events,
    get_event,
    get_events,
    get_config_for_all_active_relays,
    mark_events_deleted,
)
from .models import NostrEvent, NostrEventType, NostrFilter, RelayConfig


class NostrClientManager:
    def __init__(self: "NostrClientManager"):
        self.clients: dict = {}
        self.active_relays: dict = {}
        self.is_ready = False

    async def add_client(self, client: "NostrClientConnection") -> bool:
        if not self.is_ready:
            return False

        allow_connect = await self._allow_client_to_connect(client.relay_id, client.websocket)
        if not allow_connect:
            return False
        setattr(client, "broadcast_event", self.broadcast_event)
        self._clients(client.relay_id).append(client)

        return True

    def remove_client(self, c: "NostrClientConnection"):
        self._clients(c.relay_id).remove(c)

    async def broadcast_event(self, source: "NostrClientConnection", event: NostrEvent):
        for client in self._clients(source.relay_id):
            if client != source:
                await client.notify_event(event)

    async def init_relays(self):
        self.active_relays = await get_config_for_all_active_relays()
        self.is_ready = True

    async def enable_relay(self, relay_id: str, config: RelayConfig):
        self.is_ready = True
        self.active_relays[relay_id] = config

    async def disable_relay(self, relay_id: str):
        await self._stop_clients_for_relay(relay_id)
        del self.active_relays[relay_id]
            

    async def _stop_clients_for_relay(self, relay_id: str):
        for client in self._clients(relay_id):
            if client.relay_id == relay_id:
                await client.stop(reason=f"Relay '{relay_id}' has been deactivated.")

    def _clients(self, relay_id: str) -> List["NostrClientConnection"]:
        if relay_id not in self.clients:
            self.clients[relay_id] = []
        return self.clients[relay_id]

    async def _allow_client_to_connect(self, relay_id:str, websocket: WebSocket) -> bool:
        if relay_id not in self.active_relays:
            await websocket.close(reason=f"Relay '{relay_id}' is not active")
            return False
        return True
        
class NostrClientConnection:

    def __init__(self, relay_id: str, websocket: WebSocket):
        self.websocket = websocket
        self.relay_id = relay_id
        self.filters: List[NostrFilter] = []
        self.broadcast_event: Optional[Callable] = None

    async def start(self):
        await self.websocket.accept()
        while True:
            json_data = await self.websocket.receive_text()
            print("### received: ", json_data)
            try:
                data = json.loads(json_data)

                resp = await self._handle_message(data)
                for r in resp:
                    await self.websocket.send_text(json.dumps(r))
            except Exception as e:
                logger.warning(e)

    async def stop(self, reason: Optional[str]):
        try:
            message = reason if reason else "Server closed webocket"
            await self.websocket.send_text(json.dumps(["NOTICE", message]))
            await self.websocket.close()
        except:
            pass

    async def notify_event(self, event: NostrEvent) -> bool:
        for filter in self.filters:
            if filter.matches(event):
                resp = event.serialize_response(filter.subscription_id)
                await self.websocket.send_text(json.dumps(resp))
                return True
        return False

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

        return []

    async def _handle_event(self, e: NostrEvent):
        resp_nip20: List[Any] = ["OK", e.id]
        try:
            e.check_signature()
            if e.is_replaceable_event():
                await delete_events(
                    self.relay_id, NostrFilter(kinds=[e.kind], authors=[e.pubkey])
                )
            await create_event(self.relay_id, e)
            if self.broadcast_event:
                await self.broadcast_event(self, e)
            if e.is_delete_event():
                await self._handle_delete_event(e)
            resp_nip20 += [True, ""]
        except ValueError:
            resp_nip20 += [False, "invalid: wrong event `id` or `sig`"]
        except Exception as ex:
            logger.debug(ex)
            event = await get_event(self.relay_id, e.id)
            # todo: handle NIP20 in detail
            resp_nip20 += [event != None, f"error: failed to create event"]

        await self.websocket.send_text(json.dumps(resp_nip20))

    async def _handle_delete_event(self, event: NostrEvent):
        # NIP 09
        filter = NostrFilter(authors=[event.pubkey])
        filter.ids = [t[1] for t in event.tags if t[0] == "e"]
        events_to_delete = await get_events(self.relay_id, filter, False)
        ids = [e.id for e in events_to_delete if not e.is_delete_event()]
        await mark_events_deleted(self.relay_id, NostrFilter(ids=ids))

    async def _handle_request(self, subscription_id: str, filter: NostrFilter) -> List:
        filter.subscription_id = subscription_id
        self.remove_filter(subscription_id)
        self.filters.append(filter)
        events = await get_events(self.relay_id, filter)
        serialized_events = [
            event.serialize_response(subscription_id) for event in events
        ]
        resp_nip15 = ["EOSE", subscription_id]
        serialized_events.append(resp_nip15)
        return serialized_events

    def _handle_close(self, subscription_id: str):
        self.remove_filter(subscription_id)

    def remove_filter(self, subscription_id: str):
        self.filters = [f for f in self.filters if f.subscription_id != subscription_id]
