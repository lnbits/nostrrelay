import asyncio
import inspect

import pytest
from lnbits.db import Database
from loguru import logger
from pydantic import BaseModel

from .. import migrations
from ..relay.event import NostrEvent
from .helpers import get_fixtures


class EventFixture(BaseModel):
    name: str
    exception: str | None
    data: NostrEvent


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def migrate_db():
    print("#### 999")
    db = Database("ext_nostrrelay")
    for key, migrate in inspect.getmembers(migrations, inspect.isfunction):
        print("### 1000")
        logger.info(f"Running migration '{key}'.")
        await migrate(db)
    return migrations


@pytest.fixture(scope="session")  # type: ignore
def valid_events(migrate_db) -> list[EventFixture]:
    data = get_fixtures("events")
    return [EventFixture.parse_obj(e) for e in data["valid"]]


@pytest.fixture(scope="session")  # type: ignore
def invalid_events(migrate_db) -> list[EventFixture]:
    data = get_fixtures("events")
    return [EventFixture.parse_obj(e) for e in data["invalid"]]
