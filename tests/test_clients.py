import asyncio
from json import dumps

import pytest
from fastapi import WebSocket

from lnbits.extensions.nostrrelay.client_manager import (
    NostrClientConnection,
    NostrClientManager,
)

from .helpers import get_fixtures

fixtures = get_fixtures("clients")
alice = fixtures["alice"]
bob = fixtures["bob"]


class MockWebSocket(WebSocket):
    def __init__(self):
        self.sent_messages = []
        self.fake_wire: asyncio.Queue[str] = asyncio.Queue(0)
        pass

    async def accept(self):
        await asyncio.sleep(0.1)

    async def receive_text(self) -> str:
        data = await self.fake_wire.get()
        return data

    async def send_text(self, data: str):
        self.sent_messages.append(data)

    async def wire_mock_data(self, data: dict):
        await self.fake_wire.put(dumps(data))


@pytest.mark.asyncio
async def test_alice_and_bob():
    ws_alice, ws_bob = init_clients()

    await alice_wire_meta_and_post01(ws_alice)

    await bob_wire_meta_and_folow_alice(ws_bob)

    await alice_wire_post02_and_bob_is_notified(ws_alice, ws_bob)

    await bob_likes_posts_alice_subscribes_and_receives_notifications(ws_alice, ws_bob)

    await bob_likes_and_comments___alice_receives_notifications(ws_alice, ws_bob)


def init_clients():
    client_manager = NostrClientManager()

    ws_alice = MockWebSocket()
    client_alice = NostrClientConnection(websocket=ws_alice)
    client_manager.add_client(client_alice)
    asyncio.create_task(client_alice.start())

    ws_bob = MockWebSocket()
    client_bob = NostrClientConnection(websocket=ws_bob)
    client_manager.add_client(client_bob)
    asyncio.create_task(client_bob.start())
    return ws_alice, ws_bob


async def alice_wire_meta_and_post01(ws_alice: MockWebSocket):
    ws_alice.sent_messages.clear()

    await ws_alice.wire_mock_data(alice["meta"])
    await ws_alice.wire_mock_data(alice["post01"])
    await ws_alice.wire_mock_data(alice["post01"])
    await asyncio.sleep(0.5)

    assert (
        len(ws_alice.sent_messages) == 3
    ), "Alice: Expected 3 confirmations to be sent"
    assert ws_alice.sent_messages[0] == dumps(
        alice["meta_response"]
    ), "Alice: Wrong confirmation for meta"
    assert ws_alice.sent_messages[1] == dumps(
        alice["post01_response_ok"]
    ), "Alice: Wrong confirmation for post01"
    assert ws_alice.sent_messages[2] == dumps(
        alice["post01_response_duplicate"]
    ), "Alice: Expected failure for double posting"

    await asyncio.sleep(0.1)


async def bob_wire_meta_and_folow_alice(ws_bob: MockWebSocket):
    ws_bob.sent_messages.clear()

    await ws_bob.wire_mock_data(bob["meta"])
    await ws_bob.wire_mock_data(bob["request_meta_alice"])
    await ws_bob.wire_mock_data(bob["request_posts_alice"])

    await asyncio.sleep(0.5)

    assert len(ws_bob.sent_messages) == 5, "Bob: Expected 5 confirmations to be sent"
    assert ws_bob.sent_messages[0] == dumps(
        bob["meta_response"]
    ), "Bob: Wrong confirmation for meta"
    assert ws_bob.sent_messages[1] == dumps(
        ["EVENT", "profile", alice["meta"][1]]
    ), "Bob: Wrong response for Alice's meta"
    assert ws_bob.sent_messages[2] == dumps(
        ["EOSE", "profile"]
    ), "Bob: Wrong End Of Streaming Event for profile"
    assert ws_bob.sent_messages[3] == dumps(
        ["EVENT", "sub0", alice["post01"][1]]
    ), "Bob: Wrong posts for Alice"
    assert ws_bob.sent_messages[4] == dumps(
        ["EOSE", "sub0"]
    ), "Bob: Wrong End Of Streaming Event for sub0"


async def alice_wire_post02_and_bob_is_notified(
    ws_alice: MockWebSocket, ws_bob: MockWebSocket
):
    ws_bob.sent_messages.clear()
    ws_alice.sent_messages.clear()

    await ws_alice.wire_mock_data(alice["post02"])
    await asyncio.sleep(0.5)

    assert ws_alice.sent_messages[0] == dumps(
        alice["post02_response_ok"]
    ), "Alice: Wrong confirmation for post02"
    assert ws_bob.sent_messages[0] == dumps(
        ["EVENT", "sub0", alice["post02"][1]]
    ), "Bob: Wrong notification for post02"


async def bob_likes_posts_alice_subscribes_and_receives_notifications(
    ws_alice: MockWebSocket, ws_bob: MockWebSocket
):
    ws_alice.sent_messages.clear()
    ws_bob.sent_messages.clear()

    await ws_bob.wire_mock_data(bob["like_post01"])
    await asyncio.sleep(0.1)
    await ws_alice.wire_mock_data(alice["subscribe_reactions_to_me"])
    await asyncio.sleep(0.1)

    assert (
        len(ws_alice.sent_messages) == 2
    ), "Alice: Expected 2 confirmations to be sent"

    assert ws_alice.sent_messages[0] == dumps(
        [
            "EVENT",
            "notifications:0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345",
            bob["like_post01"][1],
        ]
    ), "Alice: must receive 'like' notification"

    assert ws_alice.sent_messages[1] == dumps(
        ["EOSE", "notifications:0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345"]
    ), "Alice: receive stored notifications done"


async def bob_likes_and_comments___alice_receives_notifications(
    ws_alice: MockWebSocket, ws_bob: MockWebSocket
):
    ws_alice.sent_messages.clear()
    ws_bob.sent_messages.clear()

    await ws_bob.wire_mock_data(bob["like_post02"])
    await ws_bob.wire_mock_data(bob["comment_on_alice_post01"])
    await asyncio.sleep(0.5)

    assert (
        len(ws_bob.sent_messages) == 2
    ), "Bob: Expected 2 confirmations to be sent (for like & comment)"
    assert ws_bob.sent_messages[0] == dumps(
        bob["like_post02_response"]
    ), "Bob: Wrong confirmation for like on post02"
    assert ws_bob.sent_messages[1] == dumps(
        bob["comment_on_alice_post01_response"]
    ), "Bob: Wrong confirmation for comment on post01"
    assert (
        len(ws_alice.sent_messages) == 2
    ), "Alice: Expected 2 notifications to be sent (for like & comment)"
    assert ws_alice.sent_messages[0] == dumps(
        [
            "EVENT",
            "notifications:0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345",
            bob["like_post02"][1],
        ]
    ), "Alice: Wrong notification for like on post02"
    assert ws_alice.sent_messages[1] == dumps(
        [
            "EVENT",
            "notifications:0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345",
            bob["comment_on_alice_post01"][1],
        ]
    ), "Alice: Wrong notification for comment on post01"
