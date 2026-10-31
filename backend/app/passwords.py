"""
Password hashing helpers.

New hashes use bcrypt (via passlib). Legacy unsalted SHA-256 hex digests created by earlier
versions of the project are still *verified* so existing databases keep working, and
`needs_rehash()` lets the login flow upgrade them transparently on the next successful login.
"""

import hashlib
import hmac
import re

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt only looks at the first 72 bytes; refuse longer inputs instead of silently truncating.
MAX_PASSWORD_BYTES = 72

_LEGACY_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def is_legacy_hash(stored_hash: str) -> bool:
    return bool(stored_hash and _LEGACY_SHA256_RE.match(stored_hash))


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
    return _pwd_context.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    if not password or not stored_hash:
        return False
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return False
    if is_legacy_hash(stored_hash):
        candidate = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(candidate, stored_hash)
    try:
        return _pwd_context.verify(password, stored_hash)
    except ValueError:
        return False


def needs_rehash(stored_hash: str) -> bool:
    if is_legacy_hash(stored_hash):
        return True
    try:
        return _pwd_context.needs_update(stored_hash)
    except ValueError:
        return True
