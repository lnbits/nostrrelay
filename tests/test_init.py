import pytest
from fastapi import APIRouter

from .. import nostrnip5_ext, nostrnip5_start, nostrnip5_stop


# just import router and add it to a test router
@pytest.mark.asyncio
async def test_router():
    router = APIRouter()
    router.include_router(nostrnip5_ext)


@pytest.mark.asyncio
async def test_start_and_stop():
    nostrnip5_start()
    nostrnip5_stop()
