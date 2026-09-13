from unittest.mock import AsyncMock, MagicMock

import pytest

from ..relay.client_connection import NostrClientConnection
from ..relay.relay import RelaySpec

RELAY_ID = "relay_req_filters"


def _connection(spec: RelaySpec | None = None) -> NostrClientConnection:
    conn = NostrClientConnection(relay_id=RELAY_ID, websocket=MagicMock())
    conn.get_client_config = lambda: spec or RelaySpec()
    conn._send_msg = AsyncMock()  # type: ignore[method-assign]
    return conn


def _subscriptions(conn: NostrClientConnection) -> list[str | None]:
    return [f.subscription_id for f in conn.filters]


@pytest.mark.asyncio
async def test_multi_filter_req_keeps_every_filter():
    conn = _connection()

    await conn._handle_message(["REQ", "sub", {"kinds": [1]}, {"kinds": [3]}])

    assert _subscriptions(conn) == ["sub", "sub"]
    assert sorted(f.kinds for f in conn.filters) == [[1], [3]]


@pytest.mark.asyncio
async def test_new_req_replaces_the_subscription():
    conn = _connection()
    await conn._handle_message(["REQ", "sub", {"kinds": [1]}, {"kinds": [3]}])
    await conn._handle_message(["REQ", "other", {"kinds": [7]}])

    await conn._handle_message(["REQ", "sub", {"kinds": [0]}])

    assert _subscriptions(conn) == ["other", "sub"]
    assert [f.kinds for f in conn.filters] == [[7], [0]]


@pytest.mark.asyncio
async def test_filter_cap_is_enforced():
    conn = _connection(RelaySpec(maxClientFilters=2))

    await conn._handle_message(["REQ", "a", {"kinds": [1]}])
    await conn._handle_message(["REQ", "b", {"kinds": [1]}])
    responses = await conn._handle_message(["REQ", "c", {"kinds": [1]}])

    assert _subscriptions(conn) == ["a", "b"]
    assert responses == [["NOTICE", "Maximum number of filters (2) exceeded."]]
