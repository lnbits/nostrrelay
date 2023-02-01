import json
from typing import List, Optional

import pytest
from loguru import logger
from pydantic import BaseModel

from lnbits.extensions.nostrrelay.models import NostrEvent

FIXTURES_PATH = "tests/extensions/nostrrelay/fixture"

class EventFixture(BaseModel):
    name: str
    exception: Optional[str]
    data: NostrEvent


@pytest.fixture
def valid_events() -> List[EventFixture]:
    data = get_fixture("events")
    return [EventFixture.parse_obj(e) for e in data["valid"]]

@pytest.fixture
def invalid_events() -> List[EventFixture]:
    data = get_fixture("events")
    return [EventFixture.parse_obj(e) for e in data["invalid"]]


def test_event_id_and_signature_ok(valid_events: List[EventFixture]):
    for f in valid_events:
        try:
            f.data.check_signature()
        except Exception as e:
            logger.error(f"Failed for fixture: '{f.name}'")
            raise e

def test_event_id_and_signature_invalid(invalid_events: List[EventFixture]):
    for f in invalid_events:
        print("### test_event_id_and_signature_invalid", f.name)
        with pytest.raises(ValueError, match=f.exception) as e_info:
            print("### e.info", e_info)
            f.data.check_signature()
            



def get_fixture(file):
    """
    Read the content of the JSON file.
    """

    with open(f"{FIXTURES_PATH}/{file}.json") as f:
        raw_data = json.load(f)
    return raw_data
