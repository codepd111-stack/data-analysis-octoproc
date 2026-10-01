import hmac
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from app.core.auth import auth_enabled, create_token
from app.core.config import settings
from app.schemas.base import CamelModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

WINDOW_SECONDS = 300
MAX_FAILURES = 8
_failures: dict[str, list[float]] = {}  # in-memory throttle: fine for a single small instance


class LoginRequest(CamelModel):
    code: str = Field(min_length=1, max_length=200)


class LoginResponse(CamelModel):
    token: str
    expires_at: int


def _client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    return first or (request.client.host if request.client else "unknown")


@router.get("/status")
def status() -> dict:
    return {"authRequired": auth_enabled()}


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request):
    if not auth_enabled():
        raise HTTPException(400, "Sign-in is not enabled on this server.")

    client = _client_id(request)
    now = time.time()
    recent = [t for t in _failures.get(client, []) if now - t < WINDOW_SECONDS]
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")

    if not hmac.compare_digest(body.code.encode(), settings.access_code.encode()):
        recent.append(now)
        _failures[client] = recent
        raise HTTPException(401, "That code is not correct.")

    _failures.pop(client, None)
    token, expires_at = create_token()
    return LoginResponse(token=token, expires_at=expires_at)