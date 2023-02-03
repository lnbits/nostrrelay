import json
from typing import Any, Callable, List

from fastapi import WebSocket
from loguru import logger

from .crud import create_event, delete_events, get_events
from .models import NostrEvent, NostrEventType, NostrFilter


class NostrClientManager:
    def __init__(self):
        self.clients: List["NostrClientConnection"] = []

    def add_client(self, client: "NostrClientConnection"):
        setattr(client, "broadcast_event", self.broadcast_event)
        self.clients.append(client)

    def remove_client(self, client: "NostrClientConnection"):
        self.clients.remove(client)

    async def broadcast_event(self, source: "NostrClientConnection", event: NostrEvent):
        for client in self.clients:
            if client != source:
                await client.notify_event(event)


class NostrClientConnection:
    broadcast_event: Callable

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.filters: List[NostrFilter] = []

    async def start(self):
        await self.websocket.accept()
        while True:
            json_data = await self.websocket.receive_text()
            print('### received: ', json_data)
            try:
                data = json.loads(json_data)

                resp = await self.__handle_message(data)
                for r in resp:
                    await self.websocket.send_text(json.dumps(r))
            except Exception as e:
                logger.warning(e)

    async def notify_event(self, event: NostrEvent) -> bool:
        for filter in self.filters:
            if filter.matches(event):
                resp = event.serialize_response(filter.subscription_id)
                await self.websocket.send_text(json.dumps(resp))
                return True
        return False
                

    async def __handle_message(self, data: List) -> List:
        if len(data) < 2:
            return []

        message_type = data[0]
        if message_type == NostrEventType.EVENT:
            await self.__handle_event(NostrEvent.parse_obj(data[1]))
            return []
        if message_type == NostrEventType.REQ:
            if len(data) != 3:
                return []
            return await self.__handle_request(data[1], NostrFilter.parse_obj(data[2]))
        if message_type == NostrEventType.CLOSE:
            self.__handle_close(data[1])

        return []

    async def __handle_event(self, e: NostrEvent):
        resp_nip20: List[Any] = ["ok", e.id]
        try:
            e.check_signature()
            await create_event("111", e)
            await self.broadcast_event(self, e)
            if e.is_delete_event():
                await self.__delete_event(e)
            resp_nip20 += [True, ""]
        except Exception as ex:
            resp_nip20 += [False, f"error: failed to create event"]

        await self.websocket.send_text(json.dumps(resp_nip20))

    async def __delete_event(self, event: NostrEvent):
        # NIP 09
        filter = NostrFilter(authors=[event.pubkey])
        filter.ids = [t[1] for t in event.tags if t[0] == "e"]
        events_to_delete = await get_events("111", filter, False)
        ids = [e.id for e in events_to_delete]
        await delete_events("111", ids)

    async def __handle_request(self, subscription_id: str, filter: NostrFilter) -> List:
        filter.subscription_id = subscription_id
        self.remove_filter(subscription_id)
        self.filters.append(filter)
        events = await get_events("111", filter)
        serialized_events = [
            event.serialize_response(subscription_id) for event in events
        ]
        resp_nip15 = ["EOSE", subscription_id]
        serialized_events.append(resp_nip15)
        return serialized_events

    def __handle_close(self, subscription_id: str):
        self.remove_filter(subscription_id)

    def remove_filter(self, subscription_id: str):
        self.filters = [f for f in self.filters if f.subscription_id != subscription_id]
