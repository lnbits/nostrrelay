import asyncio
from json import dumps, loads
from typing import Optional

import pytest
from fastapi import WebSocket
from loguru import logger

from lnbits.extensions.nostrrelay.relay.client_connection import (  # type: ignore
    NostrClientConnection,
)
from lnbits.extensions.nostrrelay.relay.client_manager import (  # type: ignore
    NostrClientManager,
)
from lnbits.extensions.nostrrelay.relay.relay import RelaySpec  # type: ignore

from .helpers import get_fixtures

fixtures = get_fixtures("clients")
alice = fixtures["alice"]
bob = fixtures["bob"]

RELAY_ID = "relay_01"


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

    async def close(self, code: int = 1000, reason: Optional[str] = None) -> None:
        logger.info(reason)


@pytest.mark.asyncio
async def test_alice_and_bob():
    ws_alice, ws_bob = await init_clients()

    await alice_wires_meta_and_post01(ws_alice)

    await bob_wires_meta_and_folows_alice(ws_bob)

    await bob_wires_contact_list(ws_alice, ws_bob)

    await alice_wires_post02_____bob_is_notified(ws_alice, ws_bob)

    await bob_likes_post01_____alice_subscribes_and_receives_notifications(
        ws_alice, ws_bob
    )

    await bob_likes_and_comments_____alice_receives_notifications(ws_alice, ws_bob)

    await bob_writes_to_alice(ws_alice, ws_bob)

    await alice_writes_to_bob(ws_alice, ws_bob)

    await alice_deletes_post01__bob_is_notified(ws_alice, ws_bob)


async def init_clients():
    client_manager = NostrClientManager()
    await client_manager.enable_relay(RELAY_ID, RelaySpec())

    ws_alice = MockWebSocket()
    client_alice = NostrClientConnection(relay_id=RELAY_ID, websocket=ws_alice)
    await client_manager.add_client(client_alice)
    asyncio.create_task(client_alice.start())

    ws_bob = MockWebSocket()
    client_bob = NostrClientConnection(relay_id=RELAY_ID, websocket=ws_bob)
    await client_manager.add_client(client_bob)
    asyncio.create_task(client_bob.start())
    return ws_alice, ws_bob


async def alice_wires_meta_and_post01(ws_alice: MockWebSocket):
    ws_alice.sent_messages.clear()

    await ws_alice.wire_mock_data(alice["meta"])
    await ws_alice.wire_mock_data(alice["post01"])
    await ws_alice.wire_mock_data(alice["post01"])
    await ws_alice.wire_mock_data(alice["meta_update"])
    await asyncio.sleep(0.5)

    assert (
        len(ws_alice.sent_messages) == 4
    ), "Alice: Expected 4 confirmations to be sent"
    assert ws_alice.sent_messages[0] == dumps(
        alice["meta_response"]
    ), "Alice: Wrong confirmation for meta"
    assert ws_alice.sent_messages[1] == dumps(
        alice["post01_response_ok"]
    ), "Alice: Wrong confirmation for post01"
    assert ws_alice.sent_messages[2] == dumps(
        alice["post01_response_duplicate"]
    ), "Alice: Expected failure for double posting"
    assert ws_alice.sent_messages[3] == dumps(
        alice["meta_update_response"]
    ), "Alice: Expected confirmation for meta update"

    await asyncio.sleep(0.1)


async def bob_wires_meta_and_folows_alice(ws_bob: MockWebSocket):
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
        ["EVENT", "profile", alice["meta_update"][1]]
    ), "Bob: Wrong response for Alice's meta (updated version)"
    assert ws_bob.sent_messages[2] == dumps(
        ["EOSE", "profile"]
    ), "Bob: Wrong End Of Streaming Event for profile"
    assert ws_bob.sent_messages[3] == dumps(
        ["EVENT", "sub0", alice["post01"][1]]
    ), "Bob: Wrong posts for Alice"
    assert ws_bob.sent_messages[4] == dumps(
        ["EOSE", "sub0"]
    ), "Bob: Wrong End Of Streaming Event for sub0"


async def bob_wires_contact_list(ws_alice: MockWebSocket, ws_bob: MockWebSocket):
    ws_alice.sent_messages.clear()
    ws_bob.sent_messages.clear()

    await ws_bob.wire_mock_data(bob["contact_list_create"])
    await ws_bob.wire_mock_data(bob["contact_list_update"])
    await asyncio.sleep(0.1)
    await ws_alice.wire_mock_data(alice["subscribe_to_bob_contact_list"])
    await asyncio.sleep(0.1)

    print("### ws_alice.sent_message", ws_alice.sent_messages)
    print("### ws_bob.sent_message", ws_bob.sent_messages)

    assert (
        len(ws_bob.sent_messages) == 2
    ), "Bob: Expected 1 confirmation for create contact list"
    assert ws_bob.sent_messages[0] == dumps(
        bob["contact_list_create_response"]
    ), "Bob: Wrong confirmation for contact list create"
    assert ws_bob.sent_messages[1] == dumps(
        bob["contact_list_update_response"]
    ), "Bob: Wrong confirmation for contact list update"

    assert (
        len(ws_alice.sent_messages) == 2
    ), "Alice: Expected 3 messages for Bob's contact list"
    assert ws_alice.sent_messages[0] == dumps(
        ["EVENT", "contact", bob["contact_list_update"][1]]
    ), "Alice: Expected to receive the updated contact list (two items)"
    assert ws_alice.sent_messages[1] == dumps(
        ["EOSE", "contact"]
    ), "Alice: Wrong End Of Streaming Event for contact list"


async def alice_wires_post02_____bob_is_notified(
    ws_alice: MockWebSocket, ws_bob: MockWebSocket
):
    ws_bob.sent_messages.clear()
    ws_alice.sent_messages.clear()

    await ws_alice.wire_mock_data(alice["post02"])
    await asyncio.sleep(0.1)

    assert ws_alice.sent_messages[0] == dumps(
        alice["post02_response_ok"]
    ), "Alice: Wrong confirmation for post02"
    assert ws_bob.sent_messages[0] == dumps(
        ["EVENT", "sub0", alice["post02"][1]]
    ), "Bob: Wrong notification for post02"


async def bob_likes_post01_____alice_subscribes_and_receives_notifications(
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


async def bob_likes_and_comments_____alice_receives_notifications(
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


async def bob_writes_to_alice(ws_alice: MockWebSocket, ws_bob: MockWebSocket):
    ws_alice.sent_messages.clear()
    ws_bob.sent_messages.clear()

    await ws_bob.wire_mock_data(bob["direct_message01"])
    await asyncio.sleep(0.1)

    assert (
        len(ws_bob.sent_messages) == 1
    ), "Bob: Expected confirmation for direct message"
    assert ws_bob.sent_messages[0] == dumps(
        bob["direct_message01_response"]
    ), "Bob: Wrong confirmation for direct message"
    assert (
        len(ws_alice.sent_messages) == 1
    ), "Alice: Expected confirmation for direct message"
    assert ws_alice.sent_messages[0] == dumps(
        [
            "EVENT",
            "notifications:0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345",
            bob["direct_message01"][1],
        ]
    ), "Alice: Wrong direct message received"


async def alice_writes_to_bob(ws_alice: MockWebSocket, ws_bob: MockWebSocket):
    ws_alice.sent_messages.clear()
    ws_bob.sent_messages.clear()

    await ws_alice.wire_mock_data(alice["direct_message01"])
    await asyncio.sleep(0.1)

    assert (
        len(ws_alice.sent_messages) == 1
    ), "Alice: Expected confirmation for direct message"
    assert ws_alice.sent_messages[0] == dumps(
        alice["direct_message01_response"]
    ), "Alice: Wrong confirmation for direct message"
    assert len(ws_bob.sent_messages) == 0, "Bob: no subscription, no message"

    await ws_bob.wire_mock_data(bob["subscribe_to_direct_messages"])
    await asyncio.sleep(0.5)

    assert (
        len(ws_bob.sent_messages) == 2
    ), "Bob: Receive message and EOSE after subscribe"

    assert ws_bob.sent_messages[0] == dumps(
        [
            "EVENT",
            "notifications:d685447c43c7c18dbbea61923cf0b63e1ab46bed",
            alice["direct_message01"][1],
        ]
    ), "Bob: Finaly receives direct message from Alice"
    assert ws_bob.sent_messages[1] == dumps(
        ["EOSE", "notifications:d685447c43c7c18dbbea61923cf0b63e1ab46bed"]
    ), "Bob: Received all stored events"


async def alice_deletes_post01__bob_is_notified(
    ws_alice: MockWebSocket, ws_bob: MockWebSocket
):
    ws_bob.sent_messages.clear()
    await ws_bob.wire_mock_data(bob["request_posts_alice"])
    await asyncio.sleep(0.1)
    assert (
        len(ws_bob.sent_messages) == 3
    ), "Bob: Expected two posts from Alice plus and EOSE"

    ws_alice.sent_messages.clear()
    ws_bob.sent_messages.clear()

    await ws_bob.wire_mock_data(bob["subscribe_to_delete_from_alice"])
    await asyncio.sleep(0.1)
    await ws_alice.wire_mock_data(alice["delete_post01"])
    await asyncio.sleep(0.1)

    assert (
        len(ws_alice.sent_messages) == 1
    ), "Alice: Expected confirmation for delete post01"
    assert ws_alice.sent_messages[0] == dumps(
        alice["delete_post01_response"]
    ), "Alice: Wrong confirmation for delete post01"

    assert len(ws_bob.sent_messages) == 2, "Bob: Expects 2 messages for delete post01"
    assert ws_bob.sent_messages[0] == dumps(
        ["EOSE", "notifications:delete"]
    ), "Bob: Expect no delete notification on subscribe"
    assert loads(ws_bob.sent_messages[1]) == [
        "EVENT",
        "notifications:delete",
        alice["delete_post01"][1],
    ], "Bob: Expect delete notification later on"

    ws_bob.sent_messages.clear()
    await ws_bob.wire_mock_data(bob["request_posts_alice"])
    await asyncio.sleep(0.1)
    assert (
        len(ws_bob.sent_messages) == 2
    ), "Bob: Expected one posts from Alice plus and EOSE"
