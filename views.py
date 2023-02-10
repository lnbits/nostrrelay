from http import HTTPStatus

from fastapi import Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, JSONResponse

from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.extensions.nostrrelay.crud import get_public_relay

from . import nostrrelay_ext, nostrrelay_renderer

templates = Jinja2Templates(directory="templates")


@nostrrelay_ext.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return nostrrelay_renderer().TemplateResponse(
        "nostrrelay/index.html", {"request": request, "user": user.dict()}
    )


@nostrrelay_ext.get("/{relay_id}")
async def nostrrelay(request: Request, relay_id: str):
    relay_public_data = await get_public_relay(relay_id)
    if not relay_public_data:
        raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="Cannot find relay",
            )

    if request.headers.get("accept") == "application/nostr+json":
        return JSONResponse(
            content=relay_public_data,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "GET",
            },
        )

    return nostrrelay_renderer().TemplateResponse(
        "nostrrelay/public.html", {"request": request, "relay": relay_public_data}
    )
