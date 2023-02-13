import asyncio
import re

from loguru import logger

from lnbits.core.models import Payment
from lnbits.extensions.nostrrelay.models import NostrAccount
from lnbits.helpers import get_current_extension_name
from lnbits.tasks import register_invoice_listener

from .crud import create_account, get_account, update_account


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

    if payment.extra.get("action") == "join":
        await invoice_paid_to_join(relay_id, pubkey)
        return

async def invoice_paid_to_join(relay_id: str, pubkey: str):
    try:
        account = await get_account(relay_id, pubkey)
        if not account:
            await create_account(relay_id, NostrAccount(pubkey=pubkey, paid_to_join=True))
            return
        
        if account.blocked or account.paid_to_join:
            return

        account.paid_to_join = True
        await update_account(relay_id, account)

    except Exception as ex:
        logger.warning(ex)