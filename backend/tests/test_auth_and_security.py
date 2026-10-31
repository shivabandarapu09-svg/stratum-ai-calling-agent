"""
Authentication, authorization & webhook-security tests.

Covers: bcrypt/legacy password handling, JWT + call-ticket validation, login throttling,
tenant scoping through the real HTTP stack (no handler is called directly in the `client` tests),
inbound lead webhook secret, Twilio signature enforcement and WebSocket ticket enforcement.
"""

import asyncio
import hashlib
import time
import uuid
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.database import SessionLocal, init_db
from app.main import app
from app.models import Agent, Organization, User
from app.passwords import hash_password, is_legacy_hash, needs_rehash, verify_password
from app.security import (
    ALGORITHM,
    create_access_token,
    create_call_ticket,
    decode_token,
    get_current_user,
    verify_call_ticket,
    verify_webhook_secret,
)
from app.telephony.twilio_security import compute_twilio_signature, require_twilio_signature

PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="module")
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


def _new_org_with_user(db, role="admin", password=PASSWORD, with_agent=True):
    org = Organization(name=f"Org {uuid.uuid4().hex[:8]}")
    db.add(org)
    db.flush()
    user = User(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        email=f"{uuid.uuid4().hex[:10]}@sec.test",
        hashed_password=hash_password(password),
        full_name="Sec Test",
        role=role,
    )
    db.add(user)
    agent = None
    if with_agent:
        agent = Agent(
            organization_id=org.id,
            name=f"Agent-{uuid.uuid4().hex[:6]}",
            system_prompt="You are a test agent.",
            greeting="Hello!",
        )
        db.add(agent)
    db.commit()
    db.refresh(user)
    if agent:
        db.refresh(agent)
    return org, user, agent


def _login_headers(client, user, password=PASSWORD):
    res = client.post("/api/auth/login", json={"email": user.email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ------------------------------------------------------------------------------
# Passwords
# ------------------------------------------------------------------------------

def test_bcrypt_hash_roundtrip_and_rejects_wrong_password():
    h = hash_password(PASSWORD)
    assert not is_legacy_hash(h)
    assert h != PASSWORD
    assert verify_password(PASSWORD, h)
    assert not verify_password("wrong-password", h)
    assert not verify_password("", h)
    # salted: hashing twice never gives the same value
    assert hash_password(PASSWORD) != h


def test_legacy_sha256_hash_still_verifies_and_is_flagged_for_upgrade():
    legacy = hashlib.sha256(PASSWORD.encode()).hexdigest()
    assert is_legacy_hash(legacy)
    assert verify_password(PASSWORD, legacy)
    assert not verify_password("nope", legacy)
    assert needs_rehash(legacy)
    assert not needs_rehash(hash_password(PASSWORD))


def test_overlong_password_is_rejected_not_truncated():
    with pytest.raises(ValueError):
        hash_password("a" * 73)
    assert not verify_password("a" * 73, hash_password("a" * 72))


# ------------------------------------------------------------------------------
# JWT access tokens & call tickets
# ------------------------------------------------------------------------------

def test_access_token_roundtrip_and_tamper_detection(db):
    _, user, _ = _new_org_with_user(db, with_agent=False)
    token = create_access_token(user)
    payload = decode_token(token)
    assert payload["sub"] == user.id and payload["org"] == user.organization_id

    with pytest.raises(HTTPException) as exc:
        decode_token(token[:-2] + ("AA" if not token.endswith("AA") else "BB"))
    assert exc.value.status_code == 401


def test_expired_and_wrong_type_tokens_are_rejected(db):
    _, user, _ = _new_org_with_user(db, with_agent=False)
    expired = jwt.encode(
        {"sub": user.id, "type": "access", "exp": int(time.time()) - 10},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    with pytest.raises(HTTPException):
        decode_token(expired)

    # a call ticket must never be accepted as an access token
    ticket = create_call_ticket("call-1", user.organization_id)
    with pytest.raises(HTTPException):
        decode_token(ticket)

    # token signed with a different key
    forged = jwt.encode({"sub": user.id, "type": "access", "exp": int(time.time()) + 600}, "other-key", algorithm=ALGORITHM)
    with pytest.raises(HTTPException):
        decode_token(forged)


def test_get_current_user_requires_valid_active_user(db):
    _, user, _ = _new_org_with_user(db, with_agent=False)

    with pytest.raises(HTTPException) as exc:
        get_current_user(creds=None, db=db)
    assert exc.value.status_code == 401

    creds = SimpleNamespace(credentials=create_access_token(user))
    assert get_current_user(creds=creds, db=db).id == user.id

    user.is_active = False
    db.commit()
    with pytest.raises(HTTPException):
        get_current_user(creds=creds, db=db)


def test_call_ticket_is_bound_to_a_single_call():
    ticket = create_call_ticket("call-A", "org-1")
    assert verify_call_ticket(ticket, "call-A")["org"] == "org-1"
    assert verify_call_ticket(ticket, "call-B") is None
    assert verify_call_ticket(None, "call-A") is None
    assert verify_call_ticket("garbage", "call-A") is None


def test_webhook_secret_check_is_strict():
    with pytest.raises(HTTPException) as exc:
        verify_webhook_secret(x_webhook_secret=None)
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException):
        verify_webhook_secret(x_webhook_secret="wrong")
    assert verify_webhook_secret(x_webhook_secret=settings.WEBHOOK_SECRET) is None


# ------------------------------------------------------------------------------
# Real HTTP stack
# ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client(db):
    return TestClient(app)


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/agents"),
        ("get", "/api/calls"),
        ("get", "/api/campaigns"),
        ("get", "/api/analytics/dashboard"),
        ("get", "/api/leads"),
        ("get", "/api/knowledge"),
        ("get", "/api/knowledge/tenants"),
        ("get", "/api/telephony/status"),
        ("post", "/api/telephony/config"),
        ("get", "/api/auth/me"),
    ],
)
def test_protected_routes_reject_anonymous_requests(client, method, path):
    res = getattr(client, method)(path)
    assert res.status_code == 401, f"{method.upper()} {path} -> {res.status_code}"


def test_health_is_public_and_leaks_no_config(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert set(res.json()) == {"status", "platform"}


def test_login_success_me_and_failure(client, db):
    _, user, _ = _new_org_with_user(db, with_agent=False)

    bad = client.post("/api/auth/login", json={"email": user.email, "password": "wrong"})
    assert bad.status_code == 401

    headers = _login_headers(client, user)
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == user.email


def test_legacy_hash_is_upgraded_to_bcrypt_on_login(client, db):
    _, user, _ = _new_org_with_user(db, with_agent=False)
    user.hashed_password = hashlib.sha256(PASSWORD.encode()).hexdigest()
    db.commit()

    _login_headers(client, user)
    db.refresh(user)
    assert not is_legacy_hash(user.hashed_password)
    assert verify_password(PASSWORD, user.hashed_password)


def test_login_is_throttled_after_repeated_failures(client, db):
    _, user, _ = _new_org_with_user(db, with_agent=False)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": user.email, "password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": user.email, "password": "bad"}).status_code == 429
    # even the right password is refused while throttled
    assert client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 429


def test_users_only_see_and_touch_their_own_organizations_data(client, db):
    _, user_a, agent_a = _new_org_with_user(db)
    _, user_b, agent_b = _new_org_with_user(db)
    ha, hb = _login_headers(client, user_a), _login_headers(client, user_b)

    ids_a = {a["id"] for a in client.get("/api/agents", headers=ha).json()}
    ids_b = {a["id"] for a in client.get("/api/agents", headers=hb).json()}
    assert agent_a.id in ids_a and agent_b.id not in ids_a
    assert agent_b.id in ids_b and agent_a.id not in ids_b

    # direct object access across tenants looks like "not found"
    assert client.get(f"/api/agents/{agent_b.id}", headers=ha).status_code == 404
    assert client.put(f"/api/agents/{agent_b.id}", json={"name": "pwned"}, headers=ha).status_code == 404
    assert client.delete(f"/api/agents/{agent_b.id}", headers=ha).status_code == 404

    # cannot start a call through another tenant's agent
    res = client.post(
        "/api/calls/initiate",
        json={"agent_id": agent_b.id, "customer_phone": "+919800000001", "provider": "web_simulator"},
        headers=ha,
    )
    assert res.status_code == 404

    # agent creation is always pinned to the caller's own org, whatever the payload says
    created = client.post(
        "/api/agents",
        json={
            "name": "Mine",
            "system_prompt": "p",
            "greeting": "g",
            "organization_id": agent_b.organization_id,
        },
        headers=ha,
    )
    assert created.status_code == 201
    assert created.json()["id"] not in ids_b
    assert client.get(f"/api/agents/{created.json()['id']}", headers=hb).status_code == 404


def test_knowledge_tenant_selector_cannot_cross_tenants_unless_superadmin(client, db):
    org_a, user_a, _ = _new_org_with_user(db)
    org_b, _, _ = _new_org_with_user(db)
    ha = _login_headers(client, user_a)

    # header / query pointing at another org is refused for a normal admin
    assert client.get("/api/knowledge", headers={**ha, "X-Tenant-ID": org_b.id}).status_code == 403
    assert client.get(f"/api/knowledge?organization_id={org_b.id}", headers=ha).status_code == 403
    assert client.get("/api/knowledge", headers={**ha, "X-Tenant-ID": org_a.id}).status_code == 200

    # tenant onboarding creates organizations: superadmin only
    res = client.post("/api/knowledge/tenants/onboard", json={"company_name": "X"}, headers=ha)
    assert res.status_code in (403, 422)  # 403 once body validates; never 201
    assert res.status_code != 201

    _, superadmin, _ = _new_org_with_user(db, role="superadmin")
    hs = _login_headers(client, superadmin)
    assert client.get("/api/knowledge", headers={**hs, "X-Tenant-ID": org_b.id}).status_code == 200


def test_lead_webhook_requires_shared_secret(client, db):
    body = {"name": "Lead", "phone": "+919811100000"}
    assert client.post("/api/leads/webhook", json=body).status_code == 401
    assert client.post("/api/leads/webhook", json=body, headers={"X-Webhook-Secret": "wrong"}).status_code == 401


def test_voice_websocket_rejects_missing_or_foreign_tickets(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/voice/call-xyz"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/voice/call-xyz?ticket=garbage"):
            pass
    other_call_ticket = create_call_ticket("some-other-call", "org-1")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/voice/call-xyz?ticket={other_call_ticket}"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/voice/call-xyz/{other_call_ticket}"):
            pass


# ------------------------------------------------------------------------------
# Twilio webhook signatures
# ------------------------------------------------------------------------------

PUBLIC_BASE = "https://voice.signature-test.example"
WEBHOOK_PATH = "/api/telephony/twilio/status/call-sig-1"


def _form_request(path, params, signature=None):
    body = urlencode(params).encode()
    headers = [(b"content-type", b"application/x-www-form-urlencoded")]
    if signature:
        headers.append((b"x-twilio-signature", signature.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "scheme": "https",
        "server": ("voice.signature-test.example", 443),
        "client": ("203.0.113.9", 4444),
    }
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.fixture()
def twilio_env(monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "test-auth-token-123")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", PUBLIC_BASE)
    monkeypatch.setattr(settings, "PUBLIC_WEBHOOK_URL", PUBLIC_BASE)
    monkeypatch.setattr(settings, "ENFORCE_TWILIO_SIGNATURES", True)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_twilio_webhook_accepts_valid_signature(twilio_env):
    params = {"CallStatus": "completed", "CallSid": "CA123"}
    sig = compute_twilio_signature(f"{PUBLIC_BASE}{WEBHOOK_PATH}", params, "test-auth-token-123")
    assert _run(require_twilio_signature(_form_request(WEBHOOK_PATH, params, sig))) is None


def test_twilio_webhook_rejects_missing_wrong_or_tampered_signature(twilio_env):
    params = {"CallStatus": "completed", "CallSid": "CA123"}
    good = compute_twilio_signature(f"{PUBLIC_BASE}{WEBHOOK_PATH}", params, "test-auth-token-123")

    for req in (
        _form_request(WEBHOOK_PATH, params, None),
        _form_request(WEBHOOK_PATH, params, "bogus"),
        _form_request(WEBHOOK_PATH, {**params, "CallStatus": "failed"}, good),  # body changed after signing
    ):
        with pytest.raises(HTTPException) as exc:
            _run(require_twilio_signature(req))
        assert exc.value.status_code == 403


def test_twilio_webhook_rejected_when_auth_token_not_configured(twilio_env, monkeypatch):
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "")
    with pytest.raises(HTTPException) as exc:
        _run(require_twilio_signature(_form_request(WEBHOOK_PATH, {"CallStatus": "completed"}, "anything")))
    assert exc.value.status_code == 403


def test_signature_enforcement_can_be_disabled_for_local_dev(twilio_env, monkeypatch):
    monkeypatch.setattr(settings, "ENFORCE_TWILIO_SIGNATURES", False)
    assert _run(require_twilio_signature(_form_request(WEBHOOK_PATH, {"CallStatus": "completed"}))) is None
