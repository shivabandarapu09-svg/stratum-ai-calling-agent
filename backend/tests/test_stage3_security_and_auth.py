import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db, hash_password, verify_password
from app.models import Organization, User, Agent, Call
from app.api.auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_current_admin_user,
    resolve_current_user,
    login,
)
from app.api.agents import get_agent, update_agent, delete_agent
from app.api.calls import get_call_detail
from app.api.telephony import update_telephony_config, TelephonyConfigRequest
from app.schemas import LoginRequest, AgentUpdate


@pytest.fixture(scope="module")
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


# ==============================================================================
# 1. PBKDF2 Password Hashing & Verification Tests
# ==============================================================================

def test_pbkdf2_password_hashing_and_verification():
    plain = "StratumSecurePass2026!"
    hashed = hash_password(plain)

    assert hashed.startswith("pbkdf2:sha256:")
    parts = hashed.split(":")
    assert len(parts) == 4
    assert len(parts[2]) == 32  # 16-byte hex salt

    # Correct password succeeds
    assert verify_password(plain, hashed) is True

    # Incorrect password fails
    assert verify_password("WrongPassword123", hashed) is False
    assert verify_password("", hashed) is False

    # Backward compatibility with legacy unsalted SHA-256
    import hashlib
    legacy_sha256 = hashlib.sha256("legacy123".encode("utf-8")).hexdigest()
    assert verify_password("legacy123", legacy_sha256) is True
    assert verify_password("wrong", legacy_sha256) is False


# ==============================================================================
# 2. Cryptographic JWT Token Signature, Expiry & Tamper Resistance
# ==============================================================================

def test_jwt_generation_verification_and_tamper_detection(db: Session):
    admin = db.query(User).filter(User.role == "superadmin").first()
    assert admin is not None

    token = create_access_token(admin, expires_delta=timedelta(minutes=15))
    assert token.count(".") == 2

    # Valid token decodes correctly
    payload = decode_access_token(token)
    assert payload["sub"] == admin.id
    assert payload["org_id"] == admin.organization_id
    assert payload["role"] == admin.role

    # Tampered signature is immediately rejected
    parts = token.split(".")
    tampered_sig = parts[0] + "." + parts[1] + ".tamperedSignature999"
    with pytest.raises(ValueError, match="Invalid signature"):
        decode_access_token(tampered_sig)

    # Expired token is rejected
    expired_token = create_access_token(admin, expires_delta=timedelta(seconds=-10))
    with pytest.raises(ValueError, match="Token expired"):
        decode_access_token(expired_token)


# ==============================================================================
# 3. Cross-Tenant Query & Mutation Isolation Tests
# ==============================================================================

def test_cross_tenant_isolation_on_agents_and_calls(db: Session):
    uid1 = uuid.uuid4().hex[:8]
    uid2 = uuid.uuid4().hex[:8]

    # Setup Tenant 1
    org1 = Organization(id=f"org-alpha-{uid1}", name="Alpha Corp")
    db.add(org1)
    db.flush()

    user1 = User(
        id=f"user-alpha-{uid1}",
        organization_id=org1.id,
        email=f"operator-{uid1}@alphacorp.example",
        hashed_password=hash_password("alphaPass123"),
        role="agent_manager"
    )
    db.add(user1)

    agent1 = Agent(
        id=f"agent-alpha-{uid1}",
        organization_id=org1.id,
        name="Alpha Advisor",
        company="Alpha Corp",
        system_prompt="Alpha SDR instructions",
        greeting="Hello from Alpha",
    )
    db.add(agent1)

    call1 = Call(
        id=f"call-alpha-{uid1}",
        organization_id=org1.id,
        agent_id=agent1.id,
        customer_phone="+919111122222",
        status="completed"
    )
    db.add(call1)

    # Setup Tenant 2
    org2 = Organization(id=f"org-beta-{uid2}", name="Beta Logistics")
    db.add(org2)
    db.flush()

    user2 = User(
        id=f"user-beta-{uid2}",
        organization_id=org2.id,
        email=f"analyst-{uid2}@betalogistics.example",
        hashed_password=hash_password("betaPass123"),
        role="agent_manager"
    )
    db.add(user2)

    db.commit()

    # User 2 (Beta) tries to read Agent 1 (Alpha) -> 404 Not Found (Cross-tenant invisible)
    with pytest.raises(HTTPException) as exc_info:
        get_agent(agent_id=agent1.id, db=db, current_user=user2)
    assert exc_info.value.status_code == 404

    # User 2 (Beta) tries to mutate Agent 1 (Alpha) -> 404 Not Found
    with pytest.raises(HTTPException) as exc_info:
        update_agent(agent_id=agent1.id, payload=AgentUpdate(name="Hacked Name"), db=db, current_user=user2)
    assert exc_info.value.status_code == 404

    # User 2 (Beta) tries to delete Agent 1 (Alpha) -> 404 Not Found
    with pytest.raises(HTTPException) as exc_info:
        delete_agent(agent_id=agent1.id, db=db, current_user=user2)
    assert exc_info.value.status_code == 404

    # User 2 (Beta) tries to read Call 1 (Alpha) -> 404 Not Found
    with pytest.raises(HTTPException) as exc_info:
        get_call_detail(call_id=call1.id, db=db, current_user=user2)
    assert exc_info.value.status_code == 404


# ==============================================================================
# 4. Role-Based Access Control: Telephony Config Protection
# ==============================================================================

def test_telephony_config_admin_role_enforcement(db: Session):
    uid = uuid.uuid4().hex[:8]
    org = db.query(Organization).first()
    non_admin = User(
        id=f"user-op-{uid}",
        organization_id=org.id,
        email=f"operator-{uid}@test.example",
        hashed_password=hash_password("op12345"),
        role="operator"
    )
    db.add(non_admin)
    db.commit()

    # Operator attempting to update system-level telephony config -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        update_telephony_config(
            req=TelephonyConfigRequest(provider="twilio", twilio_account_sid="ACmalicious00000000000000000000000000"),
            db=db,
            current_user=non_admin
        )
    assert exc_info.value.status_code == 403
    assert "Admin privileges required" in exc_info.value.detail
