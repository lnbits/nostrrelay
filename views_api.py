from http import HTTPStatus
from typing import List, Optional

from fastapi import Depends, WebSocket
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic.types import UUID4

from lnbits.decorators import (
    WalletTypeInfo,
    check_admin,
    require_admin_key,
    require_invoice_key,
)
from lnbits.helpers import urlsafe_short_hash

from . import client_manager, nostrrelay_ext
from .client_manager import NostrClientConnection
from .crud import (
    create_relay,
    delete_all_events,
    delete_relay,
    get_public_relay,
    get_relay,
    get_relays,
    update_relay,
)
from .models import NostrRelay


@nostrrelay_ext.websocket("/{relay_id}")
async def websocket_endpoint(relay_id: str, websocket: WebSocket):
    client = NostrClientConnection(relay_id=relay_id, websocket=websocket)
    if not (await client_manager.add_client(client)):
        return

    try:
        await client.start()
    except Exception as e:
        logger.warning(e)
        client_manager.remove_client(client)



@nostrrelay_ext.get("/{relay_id}", status_code=HTTPStatus.OK)
async def api_nostrrelay_info(relay_id: str):
    relay = await get_public_relay(relay_id)
    if not relay:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Relay not found",
        )

    return JSONResponse(content=relay, headers={
        "Access-Control-Allow-Origin": "*", 
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET"
    })



@nostrrelay_ext.post("/api/v1/relay")
async def api_create_relay(data: NostrRelay, wallet: WalletTypeInfo = Depends(require_admin_key)) -> NostrRelay:
    if len(data.id):
        await check_admin(UUID4(wallet.wallet.user))
    else:
        data.id = urlsafe_short_hash()[:8]

    try:
        relay = await create_relay(wallet.wallet.user, data)
        return relay

    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot create relay",
        )

@nostrrelay_ext.put("/api/v1/relay/{relay_id}")
async def api_update_relay(relay_id: str, data: NostrRelay, wallet: WalletTypeInfo = Depends(require_admin_key)) -> NostrRelay:
    if relay_id != data.id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot change the relay id",
        )

    try:
        relay = await get_relay(wallet.wallet.user, data.id)
        if not relay:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Relay not found",
            )
        updated_relay = NostrRelay.parse_obj({**dict(relay), **dict(data)})
        updated_relay = await update_relay(wallet.wallet.user, updated_relay)
        
        if updated_relay.active:            
            await client_manager.enable_relay(relay_id, updated_relay.config)
        else:
            await client_manager.disable_relay(relay_id)

        return updated_relay

    except HTTPException as ex:
        raise ex
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot update relay",
        )


@nostrrelay_ext.get("/api/v1/relay")
async def api_get_relays(wallet: WalletTypeInfo = Depends(require_invoice_key)) -> List[NostrRelay]:
    try:
        return await get_relays(wallet.wallet.user)
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot fetch relays",
        )

@nostrrelay_ext.get("/api/v1/relay/{relay_id}")
async def api_get_relay(relay_id: str, wallet: WalletTypeInfo = Depends(require_invoice_key)) -> Optional[NostrRelay]:
    try:
        relay = await get_relay(wallet.wallet.user, relay_id)
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot fetch relay",
        )
    if not relay:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Cannot find relay",
        )
    return relay

@nostrrelay_ext.delete("/api/v1/relay/{relay_id}")
async def api_delete_relay(relay_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)):
    try:
        await client_manager.disable_relay(relay_id)
        await delete_relay(wallet.wallet.user, relay_id)
        await delete_all_events(relay_id)
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot delete relay",
        )
