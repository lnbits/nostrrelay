import asyncio

from fastapi import APIRouter
from lnbits.db import Database
from loguru import logger

from .relay.client_manager import NostrClientManager
from .tasks import wait_for_paid_invoices
from .views import nostrrelay_generic_router
from .views_api import nostrrelay_api_router

db = Database("ext_nostrrelay")

nostrrelay_ext: APIRouter = APIRouter(prefix="/nostrrelay", tags=["NostrRelay"])
nostrrelay_ext.include_router(nostrrelay_generic_router)
nostrrelay_ext.include_router(nostrrelay_api_router)

client_manager: NostrClientManager = NostrClientManager()

nostrrelay_static_files = [
    {
        "path": "/nostrrelay/static",
        "name": "nostrrelay_static",
    }
]

nostrrelay_redirect_paths = [
    {
        "from_path": "/",
        "redirect_to_path": "/api/v1/relay-info",
        "header_filters": {"accept": "application/nostr+json"},
    }
]

scheduled_tasks: list[asyncio.Task] = []


def nostrrelay_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)
    try:
        asyncio.run(client_manager.stop())
    except Exception as ex:
        logger.warning(ex)


def nostrrelay_start():
    from lnbits.tasks import create_permanent_unique_task

    task = create_permanent_unique_task("ext_nostrrelay", wait_for_paid_invoices)
    scheduled_tasks.append(task)
