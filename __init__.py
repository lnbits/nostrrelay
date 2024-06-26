import asyncio

from fastapi import APIRouter
from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .relay.client_manager import NostrClientManager

db = Database("ext_nostrrelay")

nostrrelay_ext: APIRouter = APIRouter(prefix="/nostrrelay", tags=["NostrRelay"])

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


def nostrrelay_renderer():
    return template_renderer(["nostrrelay/templates"])


from .tasks import wait_for_paid_invoices
from .views import *  # noqa
from .views_api import *  # noqa

scheduled_tasks: list[asyncio.Task] = []


async def nostrrelay_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)
    try:
        await client_manager.stop()
    except Exception as ex:
        logger.warning(ex)


def nostrrelay_start():
    task = create_permanent_unique_task("ext_nostrrelay", wait_for_paid_invoices)
    scheduled_tasks.append(task)
