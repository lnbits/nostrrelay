from http import HTTPStatus
from typing import List, Optional

from fastapi import Depends, Request, WebSocket
from fastapi.exceptions import HTTPException
from loguru import logger
from pydantic.types import UUID4
from starlette.responses import JSONResponse

from lnbits.core.services import create_invoice
from lnbits.decorators import (
    WalletTypeInfo,
    check_admin,
    require_admin_key,
    require_invoice_key,
)
from lnbits.helpers import urlsafe_short_hash

from . import nostrrelay_ext, scheduled_tasks
from .crud import (
    create_account,
    create_relay,
    delete_all_events,
    delete_relay,
    get_account,
    get_accounts,
    get_relay,
    get_relay_by_id,
    get_relays,
    update_account,
    update_relay,
)
from .helpers import extract_domain, normalize_public_key, relay_info_response
from .models import BuyOrder, NostrAccount, NostrPartialAccount
from .relay.client_manager import NostrClientConnection, NostrClientManager
from .relay.relay import NostrRelay

client_manager = NostrClientManager()


@nostrrelay_ext.websocket("/{relay_id}")
async def websocket_endpoint(relay_id: str, websocket: WebSocket):
    client = NostrClientConnection(relay_id=relay_id, websocket=websocket)
    client_accepted = await client_manager.add_client(client)
    if not client_accepted:
        return

    try:
        await client.start()
    except Exception as e:
        logger.warning(e)
        client_manager.remove_client(client)


@nostrrelay_ext.post("/api/v1/relay")
async def api_create_relay(
    data: NostrRelay,
    request: Request,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> NostrRelay:
    if len(data.id):
        await check_admin(UUID4(wallet.wallet.user))
    else:
        data.id = urlsafe_short_hash()[:8]

    try:
        data.config.domain = extract_domain(str(request.url))
        relay = await create_relay(wallet.wallet.user, data)
        return relay

    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot create relay",
        )


@nostrrelay_ext.patch("/api/v1/relay/{relay_id}")
async def api_update_relay(
    relay_id: str, data: NostrRelay, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> NostrRelay:
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
        # activate & deactivate have their own endpoint
        updated_relay.active = relay.active

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


@nostrrelay_ext.put("/api/v1/relay/{relay_id}")
async def api_toggle_relay(
    relay_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> NostrRelay:

    try:
        relay = await get_relay(wallet.wallet.user, relay_id)
        if not relay:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Relay not found",
            )
        relay.active = not relay.active
        updated_relay = await update_relay(wallet.wallet.user, relay)

        if relay.active:
            await client_manager.enable_relay(relay_id, relay.config)
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
async def api_get_relays(
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> List[NostrRelay]:
    try:
        return await get_relays(wallet.wallet.user)
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot fetch relays",
        )


@nostrrelay_ext.get("/api/v1/relay-info")
async def api_get_relay_info() -> JSONResponse:
    return relay_info_response(NostrRelay.info())


@nostrrelay_ext.get("/api/v1/relay/{relay_id}")
async def api_get_relay(
    relay_id: str, wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> Optional[NostrRelay]:
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


@nostrrelay_ext.put("/api/v1/account")
async def api_create_or_update_account(
    data: NostrPartialAccount,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> NostrAccount:

    try:
        data.pubkey = normalize_public_key(data.pubkey)
        account = await get_account(data.relay_id, data.pubkey)
        if not account:
            account = NostrAccount(
                pubkey=data.pubkey,
                blocked=data.blocked or False,
                allowed=data.allowed or False,
            )
            return await create_account(data.relay_id, account)

        if data.blocked is not None:
            account.blocked = data.blocked
        if data.allowed is not None:
            account.allowed = data.allowed

        return await update_account(data.relay_id, account)

    except ValueError as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(ex),
        )
    except HTTPException as ex:
        raise ex
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot create account",
        )


@nostrrelay_ext.get("/api/v1/account")
async def api_get_accounts(
    relay_id: str,
    allowed=False,
    blocked=True,
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> List[NostrAccount]:
    try:
        # make sure the user has access to the relay
        relay = await get_relay(wallet.wallet.user, relay_id)
        if not relay:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Relay not found",
            )
        accounts = await get_accounts(relay.id, allowed, blocked)
        return accounts
    except ValueError as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(ex),
        )
    except HTTPException as ex:
        raise ex
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot fetch accounts",
        )


@nostrrelay_ext.delete("/api/v1/relay/{relay_id}")
async def api_delete_relay(
    relay_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
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


@nostrrelay_ext.put("/api/v1/pay")
async def api_pay_to_join(data: BuyOrder):
    try:
        pubkey = normalize_public_key(data.pubkey)
        relay = await get_relay_by_id(data.relay_id)
        if not relay:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Relay not found",
            )

        amount = 0
        storage_to_buy = 0
        if data.action == "join":
            if relay.is_free_to_join:
                raise ValueError("Relay is free to join")
            amount = int(relay.config.cost_to_join)
        elif data.action == "storage":
            if relay.config.storage_cost_value == 0:
                raise ValueError("Relay storage cost is zero. Cannot buy!")
            if data.units_to_buy == 0:
                raise ValueError("Must specify how much storage to buy!")
            storage_to_buy = data.units_to_buy * relay.config.storage_cost_value * 1024
            if relay.config.storage_cost_unit == "MB":
                storage_to_buy *= 1024
            amount = data.units_to_buy * relay.config.storage_cost_value
        else:
            raise ValueError(f"Unknown action: '{data.action}'")

        _, payment_request = await create_invoice(
            wallet_id=relay.config.wallet,
            amount=amount,
            memo=f"Pubkey '{data.pubkey}' wants to join {relay.id}",
            extra={
                "tag": "nostrrely",
                "action": data.action,
                "relay_id": relay.id,
                "pubkey": pubkey,
                "storage_to_buy": storage_to_buy,
            },
        )
        return {"invoice": payment_request}
    except ValueError as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(ex),
        )
    except HTTPException as ex:
        raise ex
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot create invoice for client to join",
        )


@nostrrelay_ext.delete("/api/v1", status_code=HTTPStatus.OK)
async def api_stop(wallet: WalletTypeInfo = Depends(check_admin)):
    for t in scheduled_tasks:
        try:
            t.cancel()
        except Exception as ex:
            logger.warning(ex)

    try:
        await client_manager.stop()
    except Exception as ex:
        logger.warning(ex)

    return {"success": True}
