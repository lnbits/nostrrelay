
from typing import Any, Optional
import pytest
import os

from fastapi import WebSocket
from unittest import mock

from lnbits.extensions.nostrrelay.client_manager import NostrClientConnection, NostrClientManager

def simple_urandom():
    # print('### simple_urandom', x)
    return 3

class MockWebSocket(WebSocket):
    def __init__(self):
        pass

    async def accept(self):
        print('### mock accept')

    async def receive_text(self) -> str:
        print('### mock receive_text')
        return "mock_receive_data"
    
    async def send_text(self, s:str):
        print('### mock send_text',s)


@pytest.mark.asyncio
@mock.patch('os.listdir', side_effect=simple_urandom)
async def test_xxx(value):
    print('### test_xxx', value)
    client_manager = NostrClientManager()

    v = os.listdir()
    print('### os.listdir', v)
    websocket = MockWebSocket()
    client = NostrClientConnection(websocket=websocket)
    client_manager.add_client(client)
    await client.start()

