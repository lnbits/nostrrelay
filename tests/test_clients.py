import asyncio
import json

import pytest
from fastapi import WebSocket

from lnbits.extensions.nostrrelay.client_manager import (
    NostrClientConnection,
    NostrClientManager,
)


def simple_urandom():
    # print('### simple_urandom', x)
    return 3


fixtures = {
    "alice": {
        "meta": [
            "EVENT",
            {
                "id": "9d4883c31d6ae3d80fd8882a248cc193800a096d87bd55d5c1df8a237e78ca09",
                "pubkey": "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816",
                "created_at": 1675332095,
                "kind": 0,
                "tags": [],
                "content": '{"name":"Alice"}',
                "sig": "95c30b6bbc70f3777d2b2b47ae3961e196eae0df72f3ae301ff1009cdabf9c50bb0eb7825891c842fc6ca5cb268342cc486850a6127ab40df871bd3e1fd0b0d7",
            },
        ],
        "meta_response": [
            "ok",
            "9d4883c31d6ae3d80fd8882a248cc193800a096d87bd55d5c1df8a237e78ca09",
            True,
            "",
        ],
        "post01": [
            "EVENT",
            {
                "id": "05741bda9079cdf66f3be977a4d31287366470d1337b1aeb09506da4fbf7cd85",
                "pubkey": "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816",
                "created_at": 1675332224,
                "kind": 1,
                "tags": [],
                "content": "Alice - post 01",
                "sig": "8d27c9f818ff194b491de1dc7d52d2d26916d87189ed1330315c4ff5509a986c80f34c2202302f8fe246c0b3f4e2f79103c000cbd6ca65bbe3921e14f30cb35b",
            },
        ],
        "post01_response_ok": [
            "ok",
            "05741bda9079cdf66f3be977a4d31287366470d1337b1aeb09506da4fbf7cd85",
            True,
            "",
        ],
        "post01_response_duplicate": [
            "ok",
            "05741bda9079cdf66f3be977a4d31287366470d1337b1aeb09506da4fbf7cd85",
            False,
            "error: failed to create event",
        ],
        "post02": [
            "EVENT",
            {
                "id": "79d89e66626c4c54b007259cf068a7ba9416ffb6262cc01ba8e7cebf79b9c0d5",
                "pubkey": "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816",
                "created_at": 1675332284,
                "kind": 1,
                "tags": [],
                "content": "Alice post 02",
                "sig": "012fc88407b0cfb967e80d1117acf6cf03410f6810039543d2290eef64e246d82ad130d08814b2564cee68e77dd0e99ea539e7a9751ef2e0914e7d93f345094e",
            },
        ],
        "subscribe_reactions_to_me": [
            "REQ",
            "sub0",
            {
                "kinds": [7],
                "authors": [
                    "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816"
                ],
                "limit": 50,
            },
        ],
    },
    "bob": {
        "meta": [
            "EVENT",
            {
                "id": "a3591f44f9f12e8d745a79c19affc1f9ea267a716981116835ddb7b327096be5",
                "pubkey": "d685447c43c7c18dbbea61923cf0b63e1ab46bed69b153a48279a95c40bd414a",
                "created_at": 1675332410,
                "kind": 0,
                "tags": [],
                "content": '{"name":"Bob"}',
                "sig": "52b142eb5bf95e46424d8f146a0efcfd1be35ec2ae446152ccc875bc82eee66bef6df1af9a4456ec8984540ac4e21905544b5291334e2b18a24e534b788b2d81",
            },
        ],
        "meta_response": [
            "ok",
            "a3591f44f9f12e8d745a79c19affc1f9ea267a716981116835ddb7b327096be5",
            True,
            "",
        ],
        "request_meta_alice": [
            "REQ",
            "profile",
            {
                "kinds": [0],
                "authors": [
                    "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816"
                ],
            },
        ],
        "request_posts_alice": [
            "REQ",
            "sub0",
            {
                "kinds": [1],
                "authors": [
                    "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816"
                ],
                "limit": 50,
            },
        ],
        "alice_post_01": [
            "EVENT",
            "sub0",
            {
                "id": "79d89e66626c4c54b007259cf068a7ba9416ffb6262cc01ba8e7cebf79b9c0d5",
                "pubkey": "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816",
                "created_at": 1675332284,
                "kind": 1,
                "tags": [],
                "content": "Alice post 02",
                "sig": "012fc88407b0cfb967e80d1117acf6cf03410f6810039543d2290eef64e246d82ad130d08814b2564cee68e77dd0e99ea539e7a9751ef2e0914e7d93f345094e",
            },
        ],
        "like_alice_post_02": [
            "EVENT",
            {
                "id": "920ee4e856acb3310e64415183da0dd7e2e2b7e7c5a517553b9a75981fbafcc9",
                "pubkey": "d685447c43c7c18dbbea61923cf0b63e1ab46bed69b153a48279a95c40bd414a",
                "created_at": 1675332450,
                "kind": 7,
                "tags": [
                    [
                        "e",
                        "79d89e66626c4c54b007259cf068a7ba9416ffb6262cc01ba8e7cebf79b9c0d5",
                    ],
                    [
                        "p",
                        "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816",
                    ],
                ],
                "content": "❤️",
                "sig": "90fa8093088ed9280277f10a97c41d68d9f51d24254f7b27c28f5d84ac25426f1bfc217bca0c6712a9965164b07db219ee7e583b94c4d26f00aee87344c3f17a",
            },
        ],
        "comment_on_alice_post_01": [
            "EVENT",
            {
                "id": "bb34749ffd3eb0e393e54cc90b61a7dd5f34108d4931467861d20281c0b7daea",
                "pubkey": "d685447c43c7c18dbbea61923cf0b63e1ab46bed69b153a48279a95c40bd414a",
                "created_at": 1675332468,
                "kind": 1,
                "tags": [
                    [
                        "e",
                        "05741bda9079cdf66f3be977a4d31287366470d1337b1aeb09506da4fbf7cd85",
                    ],
                    [
                        "p",
                        "0b29ecc73ba400e5b4bd1e4cb0d8f524e9958345749197ca21c8da38d0622816",
                    ],
                ],
                "content": "bob comment 01",
                "sig": "f9bb53e2adc27f3a49ec42d681833742e28d734327107ebba3076be226340503048116947a75274e5262fa03aa0430da6fe697e46e19342639ef208e5690d8c5",
            },
        ],
    },
}


class MockWebSocket(WebSocket):
    def __init__(self):
        self.sent_messages = []
        self.received_messages = []
        self.fake_wire: asyncio.Queue[str] = asyncio.Queue(0)
        pass

    async def accept(self):
        await asyncio.sleep(0.1)

    async def receive_text(self) -> str:
        # print("### mock receive_text")
        data = await self.fake_wire.get()
        self.received_messages.append(data)
        return data

    async def send_text(self, data: str):
        self.sent_messages.append(data)
        # print("### mock send_text", data)

    async def wire_mock_message(self, data: str):
        # print("#### wire_mock_message", data)
        await self.fake_wire.put(data)


@pytest.mark.asyncio
async def test_xxx():
    client_manager = NostrClientManager()

    ws_alice = MockWebSocket()
    client_alice = NostrClientConnection(websocket=ws_alice)
    client_manager.add_client(client_alice)
    asyncio.create_task(client_alice.start())

    ws_bob = MockWebSocket()
    client_bob = NostrClientConnection(websocket=ws_bob)
    client_manager.add_client(client_bob)
    asyncio.create_task(client_bob.start())

    await asyncio.sleep(1)

    await alice_wire_meta_and_post01(ws_alice, fixtures)

    

    print("### ws_alice.sent_messages", ws_alice.sent_messages)
    # print("### ws_alice.received_messages", ws_alice.received_messages)
    print("### ws_bob.sent_messages", ws_bob.sent_messages)
    print("### ws_bob.received_messages", ws_bob.received_messages)

    await bob_wire_meta_and_folow_alice(ws_bob, fixtures)

    await asyncio.sleep(1)


async def alice_wire_meta_and_post01(ws_alice: MockWebSocket, fixtures):
    await ws_alice.wire_mock_message(json.dumps(fixtures["alice"]["meta"]))
    await ws_alice.wire_mock_message(json.dumps(fixtures["alice"]["post01"]))
    await ws_alice.wire_mock_message(json.dumps(fixtures["alice"]["post01"]))
    await asyncio.sleep(0.5)
    assert (
        len(ws_alice.sent_messages) == 3
    ), "Alice: Expected 3 confirmations to be sent"
    assert ws_alice.sent_messages[0] == json.dumps(
        fixtures["alice"]["meta_response"]
    ), "Alice: Wrong confirmation for meta"
    assert ws_alice.sent_messages[1] == json.dumps(
        fixtures["alice"]["post01_response_ok"]
    ), "Alice: Wrong confirmation for post01"
    assert ws_alice.sent_messages[2] == json.dumps(
        fixtures["alice"]["post01_response_duplicate"]
    ), "Alice: Expected failure for double posting"

async def bob_wire_meta_and_folow_alice(ws_bob: MockWebSocket, fixtures):
    await ws_bob.wire_mock_message(json.dumps(fixtures["bob"]["meta"]))
    await ws_bob.wire_mock_message(
        json.dumps(fixtures["bob"]["request_meta_alice"])
    )
    await ws_bob.wire_mock_message(
        json.dumps(fixtures["bob"]["request_posts_alice"])
    )

    await asyncio.sleep(0.5)

    assert (
        len(ws_bob.sent_messages) == 5
    ), "Bob: Expected 5 confirmations to be sent"
    assert ws_bob.sent_messages[0] == json.dumps(
        fixtures["bob"]["meta_response"]
    ), "Bob: Wrong confirmation for meta"
    assert ws_bob.sent_messages[1] == json.dumps(
        ["EVENT", "profile", fixtures["alice"]["meta"][1]]
    ), "Bob: Wrong confirmation for Alice's meta"
    assert ws_bob.sent_messages[2] == json.dumps(
        ["EOSE", "profile"]
    ), "Bob: Wrong End Of Streaming Event for profile"
    assert ws_bob.sent_messages[3] == json.dumps(
        ["EVENT", "sub0", fixtures["alice"]["post01"][1]]
    ), "Bob: Wrong posts for Alice"
    assert ws_bob.sent_messages[4] == json.dumps(
        ["EOSE", "sub0"]
    ), "Bob: Wrong End Of Streaming Event for sub0"