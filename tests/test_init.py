import pytest
from fastapi import APIRouter

from .. import nostrrelay_ext, nostrrelay_start, nostrrelay_stop


# just import router and add it to a test router
@pytest.mark.asyncio
async def test_router():
    router = APIRouter()
    router.include_router(nostrrelay_ext)


@pytest.mark.asyncio
async def test_start_and_stop():
    nostrrelay_start()
    await nostrrelay_stop()
