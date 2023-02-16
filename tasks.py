import asyncio

from loguru import logger

from lnbits.core.models import Payment
from lnbits.helpers import get_current_extension_name
from lnbits.tasks import register_invoice_listener

from .crud import create_account, get_account, update_account
from .models import NostrAccount


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, get_current_extension_name())

    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment):
    if payment.extra.get("tag") != "nostrrely":
        return

    relay_id = payment.extra.get("relay_id")
    pubkey = payment.extra.get("pubkey")

    if not relay_id or not pubkey:
        logger.warning(
            f"Invoice extra data missing for 'relay_id' and 'pubkey'. Payment hash: {payment.payment_hash}"
        )
        return

    if payment.extra.get("action") == "join":
        await invoice_paid_to_join(relay_id, pubkey, payment.amount)
        return

    if payment.extra.get("action") == "storage":
        storage_to_buy = payment.extra.get("storage_to_buy")
        if not storage_to_buy:
            logger.warning(
                f"Invoice extra data missing for 'storage_to_buy'. Payment hash: {payment.payment_hash}"
            )
            return
        await invoice_paid_for_storage(relay_id, pubkey, storage_to_buy, payment.amount)
        return


async def invoice_paid_to_join(relay_id: str, pubkey: str, amount: int):
    try:
        account = await get_account(relay_id, pubkey)
        if not account:
            await create_account(
                relay_id, NostrAccount(pubkey=pubkey, paid_to_join=True, sats=amount)
            )
            return

        if account.blocked or account.paid_to_join:
            return

        account.paid_to_join = True
        account.sats += amount
        await update_account(relay_id, account)

    except Exception as ex:
        logger.warning(ex)


async def invoice_paid_for_storage(
    relay_id: str, pubkey: str, storage_to_buy: int, amount: int
):
    try:
        account = await get_account(relay_id, pubkey)
        if not account:
            await create_account(
                relay_id,
                NostrAccount(pubkey=pubkey, storage=storage_to_buy, sats=amount),
            )
            return

        if account.blocked:
            return

        account.storage = storage_to_buy
        account.sats += amount
        await update_account(relay_id, account)

    except Exception as ex:
        logger.warning(ex)
