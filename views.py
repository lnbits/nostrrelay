from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from starlette.responses import HTMLResponse

from .crud import get_public_relay
from .helpers import relay_info_response

templates = Jinja2Templates(directory="templates")

nostrrelay_generic_router: APIRouter = APIRouter()


def nostrrelay_renderer():
    return template_renderer(["nostrrelay/templates"])


@nostrrelay_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return nostrrelay_renderer().TemplateResponse(
        "nostrrelay/index.html", {"request": request, "user": user.dict()}
    )


@nostrrelay_generic_router.get("/{relay_id}")
async def nostrrelay(request: Request, relay_id: str):
    relay_public_data = await get_public_relay(relay_id)

    if not relay_public_data:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Cannot find relay",
        )

    if request.headers.get("accept") == "application/nostr+json":
        return relay_info_response(relay_public_data)

    return nostrrelay_renderer().TemplateResponse(
        "nostrrelay/public.html", {"request": request, "relay": relay_public_data}
    )
