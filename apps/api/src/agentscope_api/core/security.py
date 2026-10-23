import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from agentscope_api.core.config import Settings

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": expires_at,
        "jti": secrets.token_hex(16),
        "iss": "agentscope",
        "aud": "agentscope-dashboard",
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    return token, expires_at


def decode_access_token(token: str, settings: Settings) -> UUID:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        audience="agentscope-dashboard",
        issuer="agentscope",
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("unexpected token type")
    return UUID(payload["sub"])


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def keyed_hash(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def generate_api_key(environment_slug: str) -> tuple[str, str]:
    kind = "live" if environment_slug == "production" else "test"
    raw = f"as_{kind}_{secrets.token_urlsafe(32)}"
    return raw, raw[:16]
