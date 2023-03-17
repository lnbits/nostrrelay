import asyncio
from typing import List

from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles

from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import catch_everything_and_restart

db = Database("ext_nostrrelay")

nostrrelay_ext: APIRouter = APIRouter(prefix="/nostrrelay", tags=["NostrRelay"])

nostrrelay_static_files = [
    {
        "path": "/nostrrelay/static",
        "app": StaticFiles(directory="lnbits/extensions/nostrrelay/static"),
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

scheduled_tasks: List[asyncio.Task] = []


def nostrrelay_renderer():
    return template_renderer(["lnbits/extensions/nostrrelay/templates"])


from .tasks import wait_for_paid_invoices
from .views import *  # noqa
from .views_api import *  # noqa


def nostrrelay_start():
    loop = asyncio.get_event_loop()
    task = loop.create_task(catch_everything_and_restart(wait_for_paid_invoices))
    scheduled_tasks.append(task)
