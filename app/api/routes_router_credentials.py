"""Router's own web-admin login (optional) - see app.router_credentials_store.
Used only to build a one-click "already logged in" shortcut on the
dashboard to the router's own admin page. Kept entirely behind
settings_manage, same as the SMTP password in routes_notifications.py -
it's just as able to grant real access if leaked."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_router_credentials_store, require_settings_manage
from app.models import RouterCredentials, RouterCredentialsUpdate
from app.router_credentials_store import RouterCredentialsStore

router = APIRouter(
    prefix="/api/router-credentials", tags=["router-credentials"], dependencies=[Depends(require_settings_manage)]
)


@router.get("", response_model=RouterCredentials)
def get_router_credentials(store: RouterCredentialsStore = Depends(get_router_credentials_store)):
    return store.get()


@router.patch("", response_model=RouterCredentials)
def update_router_credentials(
    payload: RouterCredentialsUpdate,
    store: RouterCredentialsStore = Depends(get_router_credentials_store),
):
    return store.update(payload.model_dump(exclude_unset=True))
