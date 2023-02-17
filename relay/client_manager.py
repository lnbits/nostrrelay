from typing import List

from ..crud import get_config_for_all_active_relays
from .client_connection import NostrClientConnection
from .event import NostrEvent
from .relay import RelaySpec


class NostrClientManager:
    def __init__(self: "NostrClientManager"):
        self._clients: dict = {}
        self._active_relays: dict = {}
        self._is_ready = False

    async def add_client(self, c: NostrClientConnection) -> bool:
        if not self._is_ready:
            await self.init_relays()

        if not (await self._allow_client(c)):
            return False

        self._set_client_callbacks(c)
        self.clients(c.relay_id).append(c)

        return True

    def remove_client(self, c: NostrClientConnection):
        self.clients(c.relay_id).remove(c)

    async def broadcast_event(self, source: NostrClientConnection, event: NostrEvent):
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

    def clients(self, relay_id: str) -> List[NostrClientConnection]:
        if relay_id not in self._clients:
            self._clients[relay_id] = []
        return self._clients[relay_id]

    async def stop(self):
        for relay_id in self._active_relays:
            await self._stop_clients_for_relay(relay_id)

    async def _stop_clients_for_relay(self, relay_id: str):
        for client in self.clients(relay_id):
            if client.relay_id == relay_id:
                await client.stop(reason=f"Relay '{relay_id}' has been deactivated.")

    async def _allow_client(self, c: NostrClientConnection) -> bool:
        if c.relay_id not in self._active_relays:
            await c.stop(reason=f"Relay '{c.relay_id}' is not active")
            return False
        return True

    def _set_client_callbacks(self, client: NostrClientConnection):
        def get_client_config() -> RelaySpec:
            return self.get_relay_config(client.relay_id)

        setattr(client, "get_client_config", get_client_config)
        client.init_callbacks(self.broadcast_event, get_client_config)
