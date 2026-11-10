"""Router web-admin credentials, used only to build a one-click shortcut
to the router's own admin page on the dashboard."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# The router's own web-admin login (optional, single global record) - used
# only to build a one-click "already logged in" shortcut to the router's
# own admin page on the dashboard. Kept behind settings_manage, same as
# the SMTP password above - just as able to grant real access if leaked.
_IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


def _validate_ipv4_override(value: Optional[str]) -> Optional[str]:
    if value and not _IPV4_RE.match(value):
        raise ValueError("doit etre une adresse IPv4 (ex: 192.168.1.1)")
    return value


class RouterCredentialsBase(BaseModel):
    username: Optional[str] = Field(default=None, max_length=200)
    password: Optional[str] = Field(default=None, max_length=200)
    # Most router admin pages are HTTPS-only (typically with a self-signed
    # certificate) - toggle this instead of the shortcut always assuming
    # plain HTTP.
    use_https: bool = False
    # SSH quick-access (username/port only, deliberately no password field -
    # see Camera.ssh_username above for why).
    ssh_username: Optional[str] = Field(default=None, max_length=200)
    ssh_port: Optional[int] = Field(default=None, ge=1, le=65535)
    # Overrides the ".1 of the camera's subnet" guess used to build the
    # router quick-access link (guess_gateway_ip in app.js) - set this once
    # if that heuristic is wrong for your network (e.g. router at .254,
    # VLANs) instead of correcting the address by hand every time.
    ip_override: Optional[str] = Field(default=None, max_length=45)

    @field_validator("ip_override")
    @classmethod
    def _check_ip_override(cls, value: Optional[str]) -> Optional[str]:
        return _validate_ipv4_override(value)


class RouterCredentials(RouterCredentialsBase):
    pass


class RouterCredentialsUpdate(BaseModel):
    username: Optional[str] = Field(default=None, max_length=200)
    password: Optional[str] = Field(default=None, max_length=200)
    use_https: Optional[bool] = None
    ssh_username: Optional[str] = Field(default=None, max_length=200)
    ssh_port: Optional[int] = Field(default=None, ge=1, le=65535)
    ip_override: Optional[str] = Field(default=None, max_length=45)

    @field_validator("ip_override")
    @classmethod
    def _check_ip_override(cls, value: Optional[str]) -> Optional[str]:
        return _validate_ipv4_override(value)
