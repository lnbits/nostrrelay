from http import HTTPStatus

from fastapi import Query, WebSocket
from fastapi.responses import JSONResponse
from loguru import logger

from . import nostrrelay_ext
from .client_manager import NostrClientConnection, NostrClientManager
from .models import NostrRelayInfo

client_manager = NostrClientManager()


@nostrrelay_ext.websocket("/client")
async def websocket_endpoint(websocket: WebSocket):
    client = NostrClientConnection(websocket=websocket)
    client_manager.add_client(client)
    try:
        await client.start()
    except Exception as e:
        logger.warning(e)
        client_manager.remove_client(client)


@nostrrelay_ext.get("/client", status_code=HTTPStatus.OK)
async def api_nostrrelay_info():
    headers = {
        "Access-Control-Allow-Origin": "*", 
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET"
    }
    info = NostrRelayInfo()
    return JSONResponse(content=dict(info), headers=headers)


@nostrrelay_ext.get("/api/v1/enable", status_code=HTTPStatus.OK)
async def api_nostrrelay(enable: bool = Query(True)):
    return await enable_relay(enable)


async def enable_relay(enable: bool):
    return enable
