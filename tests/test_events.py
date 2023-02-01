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
        assert events[0].json() != json.dumps(f.data.json()), f"FIlter event is different for fixture '{f.name}'"

    author = "a24496bca5dd73300f4e5d5d346c73132b7354c597fcbb6509891747b4689211"
    event_id = "3219eec7427e365585d5adf26f5d2dd2709d3f0f2c0e1f79dc9021e951c67d96"
    events_by_author = await get_events(relay_id, NostrFilter(authors=[author]))
    assert len(events_by_author) == 5, f"Failed to filter by authors"


    # filter by tag 'p'
    filter = NostrFilter() # todo: check why constructor does not work for fields with aliases (#e, #p)
    filter.p.append(author)
    events_related_to_author = await get_events(relay_id, filter)
    assert len(events_related_to_author) == 5, f"Failed to filter by tag 'p'"

    # filter by tag 'e'
    filter = NostrFilter()
    filter.e.append(event_id)
    events_related_to_event = await get_events(relay_id, filter)
    assert len(events_related_to_event) == 2, f"Failed to filter by tag 'e'"

    # filter by tag 'e' & 'p'
    reply_event_id = "6b2b6cb9c72caaf3dfbc5baa5e68d75ac62f38ec011b36cc83832218c36e4894"
    filter = NostrFilter()
    filter.p.append(author)
    filter.e.append(event_id)
    events_related_to_event = await get_events(relay_id, filter)
    assert len(events_related_to_event) == 1, f"Failed to filter by tags 'e' & 'p'"
    assert events_related_to_event[0].id == reply_event_id, f"Failed to find the right event by tags 'e' & 'p'"

    # filter by tag 'e' & 'p' and author
    reply_event_id = "6b2b6cb9c72caaf3dfbc5baa5e68d75ac62f38ec011b36cc83832218c36e4894"
    filter = NostrFilter(authors=[author])
    filter.p.append(author)
    filter.e.append(event_id)
    events_related_to_event = await get_events(relay_id, filter)
    assert len(events_related_to_event) == 1, f"Failed to filter by 'author' and tags 'e' & 'p'"
    assert events_related_to_event[0].id == reply_event_id, f"Failed to find the right event by 'author' and tags 'e' & 'p'"

        

def get_fixtures(file):
    """
    Read the content of the JSON file.
    """

    with open(f"{FIXTURES_PATH}/{file}.json") as f:
        raw_data = json.load(f)
    return raw_data
