from unittest.mock import AsyncMock, MagicMock

import pytest

from ..crud import create_event, get_events
from ..relay.client_connection import NostrClientConnection
from ..relay.event import NostrEvent
from ..relay.filter import NostrFilter
from ..relay.relay import RelaySpec

ALICE = "a" * 64
BOB = "b" * 64
SIG = "0" * 128


def _connection(relay_id: str) -> NostrClientConnection:
    conn = NostrClientConnection(relay_id=relay_id, websocket=MagicMock())
    conn.get_client_config = lambda: RelaySpec()
    conn._send_msg = AsyncMock()  # type: ignore[method-assign]
    return conn


def _event(relay_id, id_, pubkey, kind, created_at, tags=None) -> NostrEvent:
    return NostrEvent(
        id=id_.rjust(64, "0"),
        relay_id=relay_id,
        publisher=pubkey,
        pubkey=pubkey,
        created_at=created_at,
        kind=kind,
        tags=tags or [],
        content="",
        sig=SIG,
    )


async def _remaining(relay_id: str) -> set[str]:
    events = await get_events(relay_id, NostrFilter(kinds=[1, 3, 30023]), False)
    return {e.id.lstrip("0") or "0" for e in events}


@pytest.mark.asyncio
async def test_a_tag_deletes_only_the_addressed_event():
    relay_id = "nip09_a_tag"
    await create_event(_event(relay_id, "1", ALICE, 30023, 100, [["d", "one"]]))
    await create_event(_event(relay_id, "2", ALICE, 30023, 100, [["d", "two"]]))
    await create_event(_event(relay_id, "3", BOB, 30023, 100, [["d", "one"]]))

    await _connection(relay_id)._handle_delete_event(
        _event(relay_id, "9", ALICE, 5, 200, [["a", f"30023:{ALICE}:one"]])
    )

    assert await _remaining(relay_id) == {"2", "3"}


@pytest.mark.asyncio
async def test_a_tag_keeps_versions_newer_than_the_request():
    relay_id = "nip09_until"
    await create_event(_event(relay_id, "1", ALICE, 30023, 100, [["d", "one"]]))
    await create_event(_event(relay_id, "2", ALICE, 30023, 300, [["d", "one"]]))

    await _connection(relay_id)._handle_delete_event(
        _event(relay_id, "9", ALICE, 5, 200, [["a", f"30023:{ALICE}:one"]])
    )

    assert await _remaining(relay_id) == {"2"}


@pytest.mark.asyncio
async def test_a_tag_for_replaceable_kind_has_empty_d():
    relay_id = "nip09_replaceable"
    await create_event(_event(relay_id, "1", ALICE, 3, 100))
    await create_event(_event(relay_id, "2", ALICE, 1, 100))

    await _connection(relay_id)._handle_delete_event(
        _event(relay_id, "9", ALICE, 5, 200, [["a", f"3:{ALICE}:"]])
    )

    assert await _remaining(relay_id) == {"2"}


@pytest.mark.asyncio
async def test_a_tag_for_non_addressable_kind_is_ignored():
    relay_id = "nip09_kind1"
    await create_event(_event(relay_id, "1", ALICE, 1, 100))

    await _connection(relay_id)._handle_delete_event(
        _event(relay_id, "9", ALICE, 5, 200, [["a", f"1:{ALICE}:"]])
    )

    assert await _remaining(relay_id) == {"1"}


@pytest.mark.asyncio
async def test_a_tag_d_value_may_contain_colons():
    relay_id = "nip09_colon"
    await create_event(_event(relay_id, "1", ALICE, 30023, 100, [["d", "a:b:c"]]))

    await _connection(relay_id)._handle_delete_event(
        _event(relay_id, "9", ALICE, 5, 200, [["a", f"30023:{ALICE}:a:b:c"]])
    )

    assert await _remaining(relay_id) == set()


@pytest.mark.asyncio
async def test_e_tag_deletes_only_own_events():
    relay_id = "nip09_e_tag"
    await create_event(_event(relay_id, "1", ALICE, 1, 100))
    await create_event(_event(relay_id, "2", BOB, 1, 100))

    await _connection(relay_id)._handle_delete_event(
        _event(
            relay_id,
            "9",
            ALICE,
            5,
            200,
            [["e", "1".rjust(64, "0")], ["e", "2".rjust(64, "0")]],
        )
    )

    assert await _remaining(relay_id) == {"2"}


@pytest.mark.asyncio
async def test_a_tag_with_empty_d_on_addressable_kind_is_specific():
    relay_id = "nip09_empty_d"
    await create_event(_event(relay_id, "1", ALICE, 30023, 100))
    await create_event(_event(relay_id, "2", ALICE, 30023, 100, [["d", ""]]))
    await create_event(_event(relay_id, "3", ALICE, 30023, 100, [["d", "one"]]))

    await _connection(relay_id)._handle_delete_event(
        _event(relay_id, "9", ALICE, 5, 200, [["a", f"30023:{ALICE}:"]])
    )

    assert await _remaining(relay_id) == {"3"}
