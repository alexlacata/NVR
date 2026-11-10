"""Remote systems domain: the "Mes systemes" directory of other,
independent NVR installations."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.common import _ID_RE

# A directory of *other* NVR installations (each a fully separate system -
# its own cameras, its own accounts, its own disk) that this one simply
# links out to, for someone managing several sites. Deliberately just a
# name + address + note: reachability is checked client-side (each
# viewer's own browser, since whether an address is reachable depends on
# where that person currently is, not on this server) rather than stored,
# and clicking through opens that other system's own login page - there is
# no shared auth or data between entries.
class RemoteSystemBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=300)
    # SSH quick-access to the machine behind this system (username/port
    # only, deliberately no password field - see Camera.ssh_username
    # above for why). Rendered as a small door icon next to the system's
    # address, distinct from that address's own "remote path" link.
    # None here just means "unset" at the model level - RemoteSystemStore.
    # create() fills both in with root/22 by default so the door appears
    # with nothing to configure; explicitly clearing them afterwards (via
    # update) opts a system back out.
    ssh_username: Optional[str] = Field(default=None, max_length=200)
    ssh_port: Optional[int] = Field(default=None, ge=1, le=65535)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("L'adresse ne peut pas etre vide")
        if "://" not in v:
            v = f"http://{v}"
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("L'adresse doit etre une URL http(s):// (ou juste une IP/nom d'hote)")
        return v.rstrip("/")


class RemoteSystemCreate(RemoteSystemBase):
    id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if not _ID_RE.match(v):
            raise ValueError(
                "L'identifiant doit contenir uniquement des lettres minuscules, "
                "chiffres, tirets ou underscores (2-64 caracteres)"
            )
        return v


class RemoteSystemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=300)
    ssh_username: Optional[str] = Field(default=None, max_length=200)
    ssh_port: Optional[int] = Field(default=None, ge=1, le=65535)


class RemoteSystem(RemoteSystemBase):
    id: str

