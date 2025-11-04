import json

import pytest
from loguru import logger

from ..crud import (
    create_event,
    get_event,
    get_events,
)
from ..relay.event import NostrEvent
from ..relay.filter import NostrFilter
from .conftest import EventFixture

RELAY_ID = "r1"


def test_valid_event_id_and_signature(valid_events: list[EventFixture]):
    for f in valid_events:
        try:
            f.data.check_signature()
        except Exception as e:
            logger.error(f"Invalid 'id' of 'signature' for fixture: '{f.name}'")
            raise e


def test_invalid_event_id_and_signature(invalid_events: list[EventFixture]):
    for f in invalid_events:
        with pytest.raises(ValueError, match=f.exception):
            f.data.check_signature()


@pytest.mark.asyncio
async def test_valid_event_crud(valid_events: list[EventFixture]):
    author = "a24496bca5dd73300f4e5d5d346c73132b7354c597fcbb6509891747b4689211"
    event_id = "3219eec7427e365585d5adf26f5d2dd2709d3f0f2c0e1f79dc9021e951c67d96"
    reply_event_id = "6b2b6cb9c72caaf3dfbc5baa5e68d75ac62f38ec011b36cc83832218c36e4894"
    all_events = [f.data for f in valid_events]

    # insert all events in DB before doing an query
    for e in all_events:
        await create_event(e)

    for f in valid_events:
        await get_by_id(f.data, f.name)
        await filter_by_id(all_events, f.data, f.name)

    await filter_by_author(all_events, author)

    await filter_by_tag_p(all_events, author)

    await filter_by_tag_e(all_events, event_id)

    await filter_by_tag_e_and_p(all_events, author, event_id, reply_event_id)

    await filter_by_tag_e_p_and_author(all_events, author, event_id, reply_event_id)


async def get_by_id(data: NostrEvent, test_name: str):
    event = await get_event(RELAY_ID, data.id)
    assert event, f"Failed to restore event (id='{data.id}')"
    assert event.json() != json.dumps(
        data.json()
    ), f"Restored event is different for fixture '{test_name}'"


async def filter_by_id(all_events: list[NostrEvent], data: NostrEvent, test_name: str):
    nostr_filter = NostrFilter(ids=[data.id])

    events = await get_events(RELAY_ID, nostr_filter)
    assert len(events) == 1, f"Expected one queried event '{test_name}'"
    assert events[0].json() != json.dumps(
        data.json()
    ), f"Queried event is different for fixture '{test_name}'"

    filtered_events = [e for e in all_events if nostr_filter.matches(e)]
    assert len(filtered_events) == 1, f"Expected one filter event '{test_name}'"
    assert filtered_events[0].json() != json.dumps(
        data.json()
    ), f"Filtered event is different for fixture '{test_name}'"


async def filter_by_author(all_events: list[NostrEvent], author):
    nostr_filter = NostrFilter(authors=[author])
    events_by_author = await get_events(RELAY_ID, nostr_filter)
    assert len(events_by_author) == 5, "Failed to query by authors"

    filtered_events = [e for e in all_events if nostr_filter.matches(e)]
    assert len(filtered_events) == 5, "Failed to filter by authors"


async def filter_by_tag_p(all_events: list[NostrEvent], author):
    # todo: check why constructor does not work for fields with aliases (#e, #p)
    nostr_filter = NostrFilter()
    nostr_filter.p.append(author)

    events_related_to_author = await get_events(RELAY_ID, nostr_filter)
    assert len(events_related_to_author) == 5, "Failed to query by tag 'p'"

    filtered_events = [e for e in all_events if nostr_filter.matches(e)]
    assert len(filtered_events) == 5, "Failed to filter by tag 'p'"


async def filter_by_tag_e(all_events: list[NostrEvent], event_id):
    nostr_filter = NostrFilter()
    nostr_filter.e.append(event_id)

    events_related_to_event = await get_events(RELAY_ID, nostr_filter)
    assert len(events_related_to_event) == 2, "Failed to query by tag 'e'"

    filtered_events = [e for e in all_events if nostr_filter.matches(e)]
    assert len(filtered_events) == 2, "Failed to filter by tag 'e'"


async def filter_by_tag_e_and_p(
    all_events: list[NostrEvent], author, event_id, reply_event_id
):
    nostr_filter = NostrFilter()
    nostr_filter.p.append(author)
    nostr_filter.e.append(event_id)

    events_related_to_event = await get_events(RELAY_ID, nostr_filter)
    assert len(events_related_to_event) == 1, "Failed to quert by tags 'e' & 'p'"
    assert (
        events_related_to_event[0].id == reply_event_id
    ), "Failed to query the right event by tags 'e' & 'p'"

    filtered_events = [e for e in all_events if nostr_filter.matches(e)]
    assert len(filtered_events) == 1, "Failed to filter by tags 'e' & 'p'"
    assert (
        filtered_events[0].id == reply_event_id
    ), "Failed to find the right event by tags 'e' & 'p'"


async def filter_by_tag_e_p_and_author(
    all_events: list[NostrEvent], author, event_id, reply_event_id
):
    nostr_filter = NostrFilter(authors=[author])
    nostr_filter.p.append(author)
    nostr_filter.e.append(event_id)
    events_related_to_event = await get_events(RELAY_ID, nostr_filter)
    assert (
        len(events_related_to_event) == 1
    ), "Failed to query by 'author' and tags 'e' & 'p'"
    assert (
        events_related_to_event[0].id == reply_event_id
    ), "Failed to query the right event by 'author' and tags 'e' & 'p'"

    filtered_events = [e for e in all_events if nostr_filter.matches(e)]
    assert len(filtered_events) == 1, "Failed to filter by 'author' and tags 'e' & 'p'"
    assert (
        filtered_events[0].id == reply_event_id
    ), "Failed to filter the right event by 'author' and tags 'e' & 'p'"
