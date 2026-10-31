"""
Authentication & authorization primitives.

- Signed JWT access tokens (HS256) for dashboard users.
- `get_current_user` dependency: validates the bearer token and loads the user from the DB.
- `org_id` is ALWAYS taken from the authenticated user, never from a client-supplied header.
- Short-lived signed "call tickets" so a browser can open /ws/voice/{call_id} without
  putting the long-lived access token in a URL.
- Constant-time shared-secret check for inbound lead webhooks.
"""

import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "org": user.organization_id,
        "role": user.role,
        "type": "access",
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise _CREDENTIALS_ERROR
    if payload.get("type") != expected_type:
        raise _CREDENTIALS_ERROR
    return payload


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise _CREDENTIALS_ERROR
    payload = decode_token(creds.credentials)
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or user.is_active is False:
        raise _CREDENTIALS_ERROR
    return user


def require_roles(*roles: str):
    """Dependency factory: `Depends(require_roles("admin", "superadmin"))`."""

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _checker


require_admin = require_roles("admin", "superadmin")
require_superadmin = require_roles("superadmin")


# ---------------------------------------------------------------------------
# WebSocket call tickets
# ---------------------------------------------------------------------------

def create_call_ticket(call_id: str, organization_id: str) -> str:
    payload = {
        "call": call_id,
        "org": organization_id,
        "type": "call_ticket",
        "exp": int((_now() + timedelta(seconds=settings.CALL_TICKET_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_call_ticket(ticket: Optional[str], call_id: str) -> Optional[dict]:
    """Returns the ticket payload if it is valid for exactly this call, else None."""
    if not ticket:
        return None
    try:
        payload = decode_token(ticket, expected_type="call_ticket")
    except HTTPException:
        return None
    if payload.get("call") != call_id:
        return None
    return payload


# ---------------------------------------------------------------------------
# Inbound lead webhook secret
# ---------------------------------------------------------------------------

def verify_webhook_secret(x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret")) -> None:
    expected = settings.WEBHOOK_SECRET or ""
    if not expected or not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing webhook secret")
