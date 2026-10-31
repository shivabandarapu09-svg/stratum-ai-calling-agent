import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.passwords import hash_password, needs_rehash, verify_password
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

# Basic in-process brute-force throttle: max 5 failures per (ip, email) per 5 minutes.
# For multi-worker deployments move this to Redis (already in docker-compose).
_MAX_FAILURES = 5
_WINDOW_SECONDS = 300
_failures: Dict[str, Deque[float]] = defaultdict(deque)


def _throttle_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}|{email.strip().lower()}"


def _check_throttle(key: str) -> None:
    now = time.time()
    attempts = _failures[key]
    while attempts and now - attempts[0] > _WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= _MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again in a few minutes.",
        )


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    key = _throttle_key(request, req.email)
    _check_throttle(key)

    user = db.query(User).filter(User.email == req.email.strip()).first()
    valid = bool(user and user.is_active is not False and verify_password(req.password, user.hashed_password))
    if not valid:
        _failures[key].append(time.time())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _failures.pop(key, None)

    # Transparently upgrade legacy unsalted SHA-256 hashes to bcrypt.
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(req.password)
        db.commit()

    org = user.organization
    return TokenResponse(
        access_token=create_access_token(user),
        user_name=user.full_name or "Admin User",
        organization_id=org.id,
        organization_name=org.name,
    )


@router.get("/me", response_model=UserOut)
def read_current_user(user: User = Depends(get_current_user)):
    return user
