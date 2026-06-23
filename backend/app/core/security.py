"""Password hashing and JWT token utilities.

Bcrypt for passwords (slow on purpose), HS256 JWTs for stateless auth.
Refresh tokens get a longer lifetime and a different `typ` claim so we
can distinguish them server-side.

We use the `bcrypt` library directly rather than passlib because passlib
1.7.x is unmaintained and its bcrypt backend breaks on bcrypt 4.x.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt has a 72-byte limit on input; longer passwords are silently
# truncated by some libraries. We hash everything to a known length first.
_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Bcrypt-hash a password. Returns the encoded hash as a str."""
    pw_bytes = plain.encode("utf-8")
    # Bcrypt only accepts the first 72 bytes — enforce explicitly rather than
    # relying on silent truncation.
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verify. Returns False on any decoding/verification error."""
    try:
        pw_bytes = plain.encode("utf-8")
        if len(pw_bytes) > 72:
            pw_bytes = pw_bytes[:72]
        return bcrypt.checkpw(pw_bytes, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | UUID,
    tenant_id: str | UUID,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    `expires_delta` overrides the default expiry from settings. Used for
    long-lived service tokens (e.g. the AI worker's 10-year token) where
    the standard 30-minute access window doesn't apply.
    """
    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expires = now + expires_delta
    else:
        expires = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(subject),
        "tid": str(tenant_id),
        "typ": "access",
        "iat": now,
        "exp": expires,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | UUID, tenant_id: str | UUID) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(subject),
        "tid": str(tenant_id),
        "typ": "refresh",
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on any failure."""
    try:
        return jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        raise
