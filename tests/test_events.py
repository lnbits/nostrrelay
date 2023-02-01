import json
from typing import List, Optional

import pytest
from loguru import logger
from pydantic import BaseModel

from lnbits.extensions.nostrrelay.crud import create_event, get_event, get_events
from lnbits.extensions.nostrrelay.models import NostrEvent, NostrFilter

FIXTURES_PATH = "tests/extensions/nostrrelay/fixture"

class EventFixture(BaseModel):
    name: str
    exception: Optional[str]
    data: NostrEvent


@pytest.fixture
def valid_events() -> List[EventFixture]:
    data = get_fixtures("events")
    return [EventFixture.parse_obj(e) for e in data["valid"]]

@pytest.fixture
def invalid_events() -> List[EventFixture]:
    data = get_fixtures("events")
    return [EventFixture.parse_obj(e) for e in data["invalid"]]


def test_valid_event_id_and_signature(valid_events: List[EventFixture]):
    for f in valid_events:
        try:
            f.data.check_signature()
        except Exception as e:
            logger.error(f"Invalid 'id' ot 'signature' for fixture: '{f.name}'")
            raise e

def test_invalid_event_id_and_signature(invalid_events: List[EventFixture]):
    for f in invalid_events:
        with pytest.raises(ValueError, match=f.exception):
            f.data.check_signature()


@pytest.mark.asyncio
async def test_valid_event_crud(valid_events: List[EventFixture]):
    relay_id = "r1"
    for f in valid_events:
        await create_event(relay_id, f.data)

    # insert all events before doing an query
    for f in valid_events:   
        event = await get_event(relay_id, f.data.id)
        assert event, f"Failed to restore event (id='{f.data.id}')"
        assert event.json() != json.dumps(f.data.json()), f"Restored event is different for fixture '{f.name}'"

        filter = NostrFilter(ids=[f.data.id])
        events = await get_events(relay_id, filter)
        assert len(events) == 1, f"Expected one filter event '{f.name}'"

        

def get_fixtures(file):
    """
    Read the content of the JSON file.
    """

    with open(f"{FIXTURES_PATH}/{file}.json") as f:
        raw_data = json.load(f)
    return raw_data
