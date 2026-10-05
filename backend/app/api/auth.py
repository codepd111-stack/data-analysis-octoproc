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
PRUNE_ABOVE = 500  # tidy the dict once this many clients have recorded a failure
# In-memory throttle: fine for a single instance with one worker, which is how this deploys.
# Several workers would each keep their own counts (the limit becomes MAX_FAILURES per worker).
_failures: dict[str, list[float]] = {}


class LoginRequest(CamelModel):
    code: str = Field(min_length=1, max_length=200)


class LoginResponse(CamelModel):
    token: str
    expires_at: int


def _client_id(request: Request) -> str:
    """
    Who is attempting to sign in. Behind a reverse proxy the real client is the LAST address in
    X-Forwarded-For (the one the proxy appended); anything before it was sent by the client and
    could be forged to dodge the throttle. Without a trusted proxy the header is ignored entirely.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.rsplit(",", 1)[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def _prune_failures(now: float) -> None:
    if len(_failures) < PRUNE_ABOVE:
        return
    for client in [c for c, times in _failures.items() if now - times[-1] >= WINDOW_SECONDS]:
        del _failures[client]


@router.get("/status")
def status() -> dict:
    return {"authRequired": auth_enabled()}


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request):
    if not auth_enabled():
        raise HTTPException(400, "Sign-in is not enabled on this server.")

    client = _client_id(request)
    now = time.time()
    _prune_failures(now)
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