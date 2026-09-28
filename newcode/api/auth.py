"""Signed bearer-token authentication and role authorization dependencies."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status

from newcode.core.config import settings
from newcode.models.domain import UserRole


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Identity recovered from a server-signed access token."""

    user_id: str
    role: UserRole


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _signing_secret() -> bytes:
    if settings.AUTH_SECRET:
        return settings.AUTH_SECRET.encode("utf-8")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication is not configured.",
    )


def validate_auth_configuration() -> None:
    """Fail startup when the server has no stable token-signing secret."""
    if not settings.AUTH_SECRET:
        raise RuntimeError("AUTH_SECRET must be configured before starting SureDesk.")


def create_access_token(
    user_id: str,
    role: UserRole | str = UserRole.BUYER,
    expires_in_seconds: int | None = None,
) -> str:
    """Create an HMAC-signed token for trusted login or test infrastructure."""
    role_value = role.value if isinstance(role, UserRole) else UserRole(role).value
    ttl = expires_in_seconds or settings.ACCESS_TOKEN_TTL_SECONDS
    payload = {
        "user_id": user_id,
        "role": role_value,
        "exp": int(time.time()) + ttl,
    }
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        _signing_secret(), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded_payload}.{_base64url_encode(signature)}"


def decode_access_token(token: str) -> AuthenticatedPrincipal:
    """Validate a signed token and return its authenticated identity."""
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        expected_signature = hmac.new(
            _signing_secret(), encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        supplied_signature = _base64url_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise ValueError("invalid signature")
        payload = json.loads(_base64url_decode(encoded_payload))
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("expired token")
        return AuthenticatedPrincipal(
            user_id=str(payload["user_id"]),
            role=UserRole(str(payload["role"])),
        )
    except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal:
    """Authenticate the caller from an Authorization bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(authorization.removeprefix("Bearer ").strip())


def require_roles(*allowed_roles: UserRole) -> Callable[..., AuthenticatedPrincipal]:
    """Build a dependency that permits only the supplied application roles."""

    async def dependency(
        authorization: Annotated[str | None, Header()] = None,
    ) -> AuthenticatedPrincipal:
        principal = await get_current_principal(authorization)
        if principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This operation requires an authorized operator.",
            )
        return principal

    return dependency
