"""Shared test helpers.

Endpoint handlers are called directly in most tests, so every handler that now depends on the
authenticated user receives one explicitly (`user=...`) instead of going through the JWT dependency.
"""

import uuid

from app.models import User

SEEDED_ORG_ID = "org-stratum-global-001"


def make_user(db, organization_id: str, role: str = "admin") -> User:
    """Create a persisted user in `organization_id` (password hash is a placeholder: tests never log in with it)."""
    user = User(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        email=f"{role}-{uuid.uuid4().hex[:10]}@test.local",
        hashed_password="!unusable-test-hash",
        full_name="Test User",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_superadmin(db) -> User:
    return make_user(db, SEEDED_ORG_ID, role="superadmin")
