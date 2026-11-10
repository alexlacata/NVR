"""Annuaire NVR - service independant.

Volontairement separe du code du NVR lui-meme (dossier app/ a la racine
du depot) : ce service se deploie sur sa propre machine (un petit VPS,
par exemple), pas sur un boitier NVR. Meme si tous vos boitiers NVR
tombent en meme temps (coupure secteur, panne reseau chez vous...),
cette page reste joignable et continue d'afficher la derniere liste
connue - puisqu'elle ne depend d'aucun d'entre eux pour fonctionner.

Un seul compte (le votre), un seul fichier de donnees (YAML, comme le
reste du NVR), pas de dependance au code de app/ : ce service peut
evoluer sans jamais risquer de casser le NVR, et inversement.
"""
from __future__ import annotations

import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Optional

import yaml
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DATA_DIR = Path(os.environ.get("DIRECTORY_DATA_DIR", "/data"))
DATA_FILE = DATA_DIR / "systems.yml"

try:
    PASSWORD = os.environ["DIRECTORY_PASSWORD"]
except KeyError as exc:
    raise RuntimeError(
        "DIRECTORY_PASSWORD doit etre definie (voir .env.example)"
    ) from exc

# Sessions en memoire (perdues au redemarrage - on revient alors juste a
# l'ecran de connexion, aucune donnee n'est affectee) : un service a un
# seul utilisateur n'a pas besoin d'un stockage de sessions persistant.
SESSION_TTL_SECONDS = 30 * 24 * 3600  # 30 jours
_sessions: dict[str, float] = {}

# Anti-bruteforce par adresse IP : ce service est expose sur internet,
# contrairement au NVR qui vit derriere un reseau local.
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300
_failed_attempts: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "inconnu"


def _is_locked_out(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < LOCKOUT_SECONDS]
    _failed_attempts[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def _record_failed_attempt(ip: str) -> None:
    _failed_attempts.setdefault(ip, []).append(time.time())


def _create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL_SECONDS
    return token


def _session_valid(token: Optional[str]) -> bool:
    if not token:
        return False
    expiry = _sessions.get(token)
    if expiry is None:
        return False
    if expiry < time.time():
        del _sessions[token]
        return False
    return True


def require_session(session: Optional[str] = Cookie(default=None)) -> None:
    if not _session_valid(session):
        raise HTTPException(status_code=401, detail="Non authentifie")


def _load_systems() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    return data


def _save_systems(systems: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(systems, f, allow_unicode=True, sort_keys=False)
    tmp.replace(DATA_FILE)


class SystemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    notes: str = Field(default="", max_length=500)


class SystemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=500)


class LoginRequest(BaseModel):
    password: str


app = FastAPI(title="Annuaire NVR")


@app.post("/api/login")
def login(payload: LoginRequest, request: Request, response: Response):
    ip = _client_ip(request)
    if _is_locked_out(ip):
        raise HTTPException(status_code=429, detail="Trop de tentatives, reessayez dans quelques minutes")
    if not secrets.compare_digest(payload.password, PASSWORD):
        _record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    token = _create_session()
    response.set_cookie(
        "session",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response, session: Optional[str] = Cookie(default=None)):
    if session in _sessions:
        del _sessions[session]
    response.delete_cookie("session")
    return {"ok": True}


@app.get("/api/session")
def session_status(session: Optional[str] = Cookie(default=None)):
    return {"authenticated": _session_valid(session)}


@app.get("/api/systems", dependencies=[Depends(require_session)])
def list_systems():
    return _load_systems()


@app.post("/api/systems", dependencies=[Depends(require_session)])
def create_system(payload: SystemCreate):
    systems = _load_systems()
    new = {"id": uuid.uuid4().hex[:12], **payload.model_dump()}
    systems.append(new)
    _save_systems(systems)
    return new


@app.patch("/api/systems/{system_id}", dependencies=[Depends(require_session)])
def update_system(system_id: str, payload: SystemUpdate):
    systems = _load_systems()
    for system in systems:
        if system["id"] == system_id:
            system.update({k: v for k, v in payload.model_dump().items() if v is not None})
            _save_systems(systems)
            return system
    raise HTTPException(status_code=404, detail="Systeme introuvable")


@app.delete("/api/systems/{system_id}", dependencies=[Depends(require_session)])
def delete_system(system_id: str):
    systems = _load_systems()
    remaining = [s for s in systems if s["id"] != system_id]
    if len(remaining) == len(systems):
        raise HTTPException(status_code=404, detail="Systeme introuvable")
    _save_systems(remaining)
    return {"ok": True}


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
