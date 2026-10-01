import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import Header, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


def auth_enabled() -> bool:
    return bool(settings.access_code)


def validate_auth_config() -> None:
    """Called at startup: fail loudly on a half-configured login instead of running insecurely."""
    if not auth_enabled():
        logger.warning("ACCESS_CODE is not set: sign-in is DISABLED and anyone can use this API.")
        return
    if len(settings.auth_secret) < 16:
        raise RuntimeError(
            "AUTH_SECRET must be at least 16 random characters when ACCESS_CODE is set."
        )


def _sign(payload: str) -> str:
    return hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_token() -> tuple[str, int]:
    expires_at = int(time.time()) + settings.auth_token_days * 86400
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": expires_at}).encode()).decode().rstrip("=")
    )
    return f"{payload}.{_sign(payload)}", expires_at


def verify_token(token: str) -> bool:
    payload, _, signature = token.partition(".")
    if not payload or not signature:
        return False
    if not hmac.compare_digest(signature.encode(), _sign(payload).encode()):
        return False
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return int(data["exp"]) > time.time()
    except Exception:  # noqa: BLE001
        return False


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: every protected route checks the Bearer token."""
    if not auth_enabled():
        return
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not verify_token(token.strip()):
        raise HTTPException(
            status_code=401, detail="Please sign in.", headers={"WWW-Authenticate": "Bearer"}
        )