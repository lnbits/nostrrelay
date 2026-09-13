from unittest.mock import AsyncMock, MagicMock

import pytest

from ..relay.client_connection import NostrClientConnection
from ..relay.event import NostrEvent
from ..relay.filter import NostrFilter
from ..relay.relay import RelaySpec

RELAY_ID = "relay_notify"
WALLET = "1111111111111111111111111111111111111111111111111111111111111111"
CLIENT = "2222222222222222222222222222222222222222222222222222222222222222"
REQUEST_ID = "3" * 64
SIG = "0" * 128


def _connection() -> NostrClientConnection:
    conn = NostrClientConnection(relay_id=RELAY_ID, websocket=MagicMock())
    conn.get_client_config = lambda: RelaySpec()
    conn._send_msg = AsyncMock()  # type: ignore[method-assign]
    return conn


def _nwc_response() -> NostrEvent:
    return NostrEvent(
        id="4" * 64,
        relay_id=RELAY_ID,
        publisher=WALLET,
        pubkey=WALLET,
        created_at=0,
        kind=23195,
        tags=[["p", CLIENT], ["e", REQUEST_ID]],
        content="ciphertext",
        sig=SIG,
    )


def _sent_subscription_ids(conn: NostrClientConnection) -> list[str]:
    return [call.args[0][1] for call in conn._send_msg.await_args_list]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_event_reaches_every_matching_subscription():
    """
    Regression: delivery used to stop at the first matching filter, so when a
    wallet service (subscribed to its own kind-23195 responses) and a wallet
    app shared one connection via nostrclient, the app never got the reply.
    """
    conn = _connection()
    conn.filters = [
        NostrFilter(subscription_id="wallet-own", kinds=[23195], authors=[WALLET]),
        NostrFilter(subscription_id="unrelated", kinds=[1]),
        NostrFilter(
            subscription_id="app-reply",
            kinds=[23195],
            **{"#e": [REQUEST_ID], "#p": [CLIENT]},  # type: ignore[arg-type]
        ),
    ]

    assert await conn.notify_event(_nwc_response()) is True
    assert _sent_subscription_ids(conn) == ["wallet-own", "app-reply"]


@pytest.mark.asyncio
async def test_subscription_with_several_matching_filters_gets_event_once():
    conn = _connection()
    conn.filters = [
        NostrFilter(subscription_id="multi", kinds=[23195]),
        NostrFilter(subscription_id="multi", authors=[WALLET]),
    ]

    assert await conn.notify_event(_nwc_response()) is True
    assert _sent_subscription_ids(conn) == ["multi"]


@pytest.mark.asyncio
async def test_no_matching_filter_sends_nothing():
    conn = _connection()
    conn.filters = [NostrFilter(subscription_id="other", kinds=[1])]

    assert await conn.notify_event(_nwc_response()) is False
    conn._send_msg.assert_not_awaited()  # type: ignore[attr-defined]
