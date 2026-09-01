from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.auth import COOKIE_NAME, AuthService
from app.config import Settings
from app.ffmpeg_manager import StreamManager
from app.ptz_registry import PTZRegistry
from app.store import CameraStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> CameraStore:
    return request.app.state.store


def get_stream_manager(request: Request) -> StreamManager:
    return request.app.state.stream_manager


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_ptz_registry(request: Request) -> PTZRegistry:
    return request.app.state.ptz_registry


def require_auth(request: Request) -> str:
    auth_service: AuthService = request.app.state.auth_service
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:]
    if not token or not auth_service.verify_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification requise")
    return token
