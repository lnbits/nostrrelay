from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from lnbits.core.crud import get_user
from lnbits.core.models import WalletTypeInfo
from lnbits.core.services import create_invoice
from lnbits.decorators import (
    require_admin_key,
    require_invoice_key,
)
from lnbits.helpers import urlsafe_short_hash
from loguru import logger
from starlette.responses import JSONResponse

from .client_manager import client_manager
from .crud import (
    create_account,
    create_relay,
    delete_account,
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
from .relay.client_manager import NostrClientConnection
from .relay.relay import NostrRelay

nostrrelay_api_router = APIRouter()


@nostrrelay_api_router.websocket("/{relay_id}")
@nostrrelay_api_router.websocket("/{relay_id}/")
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


@nostrrelay_api_router.post("/api/v1/relay")
async def api_create_relay(
    data: NostrRelay,
    request: Request,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> NostrRelay:
    data.user_id = key_info.wallet.user
    if len(data.id):
        user = await get_user(data.user_id)
        assert user, "User not found."
        assert user.admin, "Only admin users can set the relay ID"
    else:
        data.id = urlsafe_short_hash()[:8]

    data.meta.domain = extract_domain(str(request.url))
    relay = await create_relay(data)
    return relay


@nostrrelay_api_router.patch("/api/v1/relay/{relay_id}")
async def api_update_relay(
    relay_id: str, data: NostrRelay, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> NostrRelay:
    if relay_id != data.id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot change the relay id",
        )

    relay = await get_relay(wallet.wallet.user, data.id)
    if not relay:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Relay not found",
        )

    updated_relay = NostrRelay.parse_obj({**dict(relay), **dict(data)})
    updated_relay.user_id = wallet.wallet.user
    updated_relay = await update_relay(updated_relay)

    # activate & deactivate have their own endpoint
    updated_relay.active = relay.active

    if updated_relay.active:
        await client_manager.enable_relay(relay_id, updated_relay.meta)
    else:
        await client_manager.disable_relay(relay_id)

    return updated_relay


@nostrrelay_api_router.put("/api/v1/relay/{relay_id}")
async def api_toggle_relay(
    relay_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
) -> NostrRelay:
    relay = await get_relay(wallet.wallet.user, relay_id)
    if not relay:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Relay not found",
        )
    relay.active = not relay.active
    await update_relay(relay)

    if relay.active:
        await client_manager.enable_relay(relay_id, relay.meta)
    else:
        await client_manager.disable_relay(relay_id)

    return relay


@nostrrelay_api_router.get("/api/v1/relay")
async def api_get_relays(
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[NostrRelay]:
    return await get_relays(wallet.wallet.user)


@nostrrelay_api_router.get("/api/v1/relay-info")
async def api_get_relay_info() -> JSONResponse:
    return relay_info_response(NostrRelay.info())


@nostrrelay_api_router.get("/api/v1/relay/{relay_id}")
async def api_get_relay(
    relay_id: str, wallet: WalletTypeInfo = Depends(require_invoice_key)
) -> Optional[NostrRelay]:
    relay = await get_relay(wallet.wallet.user, relay_id)
    if not relay:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Cannot find relay",
        )
    return relay


@nostrrelay_api_router.put("/api/v1/account", dependencies=[Depends(require_admin_key)])
async def api_create_or_update_account(
    data: NostrPartialAccount,
) -> NostrAccount:
    data.pubkey = normalize_public_key(data.pubkey)
    account = await get_account(data.relay_id, data.pubkey)
    if not account:
        account = NostrAccount(
            pubkey=data.pubkey,
            relay_id=data.relay_id,
            blocked=data.blocked or False,
            allowed=data.allowed or False,
        )
        return await create_account(account)

    if data.blocked is not None:
        account.blocked = data.blocked
    if data.allowed is not None:
        account.allowed = data.allowed

    return await update_account(account)


@nostrrelay_api_router.delete(
    "/api/v1/account/{relay_id}/{pubkey}", dependencies=[Depends(require_admin_key)]
)
async def api_delete_account(
    relay_id: str,
    pubkey: str,
):
    try:
        pubkey = normalize_public_key(pubkey)
    except ValueError as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Invalid pubkey: {ex!s}",
        ) from ex
    return await delete_account(relay_id, pubkey)


@nostrrelay_api_router.get("/api/v1/account")
async def api_get_accounts(
    relay_id: str,
    allowed: bool = False,
    blocked: bool = True,
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[NostrAccount]:
    # make sure the user has access to the relay
    relay = await get_relay(wallet.wallet.user, relay_id)
    if not relay:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Relay not found",
        )
    accounts = await get_accounts(relay.id, allowed, blocked)
    return accounts


@nostrrelay_api_router.delete("/api/v1/relay/{relay_id}")
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
        ) from ex


@nostrrelay_api_router.put("/api/v1/pay")
async def api_pay_to_join(data: BuyOrder):
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
        amount = int(relay.meta.cost_to_join)
    elif data.action == "storage":
        if relay.meta.storage_cost_value == 0:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Relay storage cost is zero. Cannot buy!",
            )
        if data.units_to_buy == 0:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Must specify how much storage to buy!",
            )
        storage_to_buy = data.units_to_buy * relay.meta.storage_cost_value * 1024
        if relay.meta.storage_cost_unit == "MB":
            storage_to_buy *= 1024
        amount = data.units_to_buy * relay.meta.storage_cost_value
    else:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Unknown action: '{data.action}'",
        )

    payment = await create_invoice(
        wallet_id=relay.meta.wallet,
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
    return {"invoice": payment.bolt11}
