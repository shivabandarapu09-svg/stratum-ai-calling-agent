"""
Unit & Integration Tests for Stage 7: Durable Campaign Dialer, TRAI Compliance & DNC
=====================================================================================
Tests:
1. TRAI (09:00 - 20:00 IST) calling hours enforcement and compliance blocking.
2. National Customer Preference / DNC exclusion during contact import and dispatch.
3. Durable database-backed queue transition (pending -> calling -> completed) & Call record creation.
4. Campaign progress aggregation and tenant isolation.
"""

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from app.database import SessionLocal, init_db
from app.models import Agent, Campaign, CampaignContact, Customer, Organization, User, Call
from app.api.campaigns import (
    check_trai_calling_hours,
    create_campaign,
    start_campaign,
    pause_campaign,
    dispatch_campaign_batch,
    get_campaign_progress,
)
from app.schemas import CampaignCreate


@pytest.fixture(scope="module")
def setup_tenants():
    init_db()
    db = SessionLocal()
    org_id = f"org-camp-{uuid.uuid4().hex[:6]}"
    org = Organization(id=org_id, name="Urban Homes Realty")
    db.add(org)

    user = User(
        id=f"user-{uuid.uuid4().hex[:6]}",
        organization_id=org_id,
        email=f"manager-{uuid.uuid4().hex[:4]}@urbanhomes.in",
        hashed_password="pbkdf2_sha256$100000$test$hashedpassword",
        full_name="Urban Campaign Manager",
        role="tenant_admin",
    )
    db.add(user)

    agent = Agent(
        organization_id=org_id,
        name="Aditi",
        blueprint="real_estate",
        system_prompt="You are Aditi, a senior real estate qualification advisor.",
        greeting="नमस्ते, मैं अदिति बोल रही हूँ।",
        default_language="hi",
        voice_id="hi-IN-SwaraNeural",
    )
    db.add(agent)
    db.commit()
    db.refresh(user)
    db.refresh(agent)

    yield db, user, agent
    db.close()


def test_trai_calling_hours_compliance():
    # 1. 11:30 AM IST (06:00 AM UTC) -> Open
    dt_morning_ist = datetime(2026, 10, 30, 6, 0, tzinfo=timezone.utc)
    is_open, msg = check_trai_calling_hours(9, 20, dt_morning_ist)
    assert is_open is True
    assert "active in IST" in msg

    # 2. 10:30 PM IST (05:00 PM UTC) -> Closed
    dt_night_ist = datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc)
    is_open_night, msg_night = check_trai_calling_hours(9, 20, dt_night_ist)
    assert is_open_night is False
    assert "Calling window closed" in msg_night

    # 3. 07:00 AM IST (01:30 AM UTC) -> Closed
    dt_early_ist = datetime(2026, 10, 30, 1, 30, tzinfo=timezone.utc)
    is_open_early, msg_early = check_trai_calling_hours(9, 20, dt_early_ist)
    assert is_open_early is False
    assert "Calling window closed" in msg_early


def test_campaign_dnc_filtering_and_durable_dispatch(setup_tenants):
    db, user, agent = setup_tenants

    # Pre-seed a DNC customer and an active customer
    dnc_phone = "+919111111111"
    cust_dnc = Customer(
        organization_id=user.organization_id,
        name="Vikram DNC",
        phone=dnc_phone,
        status="DNC",
        tags=["DNC", "OptOut"],
    )
    db.add(cust_dnc)

    valid_phone_1 = "+919222222222"
    valid_phone_2 = "+919333333333"

    payload = CampaignCreate(
        name="Prestige Festival Outbound",
        agent_id=agent.id,
        retry_limit=2,
        calling_hours_start=9,
        calling_hours_end=20,
        contacts=[
            {"name": "Vikram DNC", "phone": dnc_phone},
            {"name": "Rahul Verma", "phone": valid_phone_1},
            {"name": "Sneha Reddy", "phone": valid_phone_2},
        ],
    )

    # 1. Create campaign
    camp_out = create_campaign(payload=payload, db=db, current_user=user)
    assert camp_out.total_contacts == 3

    # 2. Check contacts: DNC customer must be auto-flagged as 'dnc'
    contacts = db.query(CampaignContact).filter(CampaignContact.campaign_id == camp_out.id).all()
    assert len(contacts) == 3
    dnc_contacts = [c for c in contacts if c.status == "dnc"]
    assert len(dnc_contacts) == 1
    assert dnc_contacts[0].customer.phone == dnc_phone

    pending_contacts = [c for c in contacts if c.status == "pending"]
    assert len(pending_contacts) == 2

    # 3. Cannot dispatch before starting
    with pytest.raises(Exception):
        dispatch_campaign_batch(campaign_id=camp_out.id, db=db, current_user=user)

    # 4. Start campaign
    start_res = start_campaign(campaign_id=camp_out.id, db=db, current_user=user)
    assert start_res["status"] == "success"

    # 5. Dispatch batch with override flag (to ensure test passes regardless of wall-clock time)
    batch_res = dispatch_campaign_batch(
        campaign_id=camp_out.id,
        batch_size=10,
        force_override_hours=True,
        db=db,
        current_user=user,
    )
    assert batch_res["status"] == "success"
    assert batch_res["dispatched_count"] == 2
    assert len(batch_res["calls"]) == 2

    # 6. Verify Call records created in DB
    call_ids = [c["call_id"] for c in batch_res["calls"]]
    calls = db.query(Call).filter(Call.id.in_(call_ids)).all()
    assert len(calls) == 2
    for call in calls:
        assert call.direction == "outbound"
        assert call.status == "initiated"
        assert call.organization_id == user.organization_id

    # 7. Verify Campaign progress aggregation
    prog = get_campaign_progress(campaign_id=camp_out.id, db=db, current_user=user)
    assert prog["total_contacts"] == 3
    assert prog["status_breakdown"]["calling"] == 2
    assert prog["status_breakdown"]["dnc"] == 1
    assert prog["status_breakdown"]["pending"] == 0

    # 8. Pause campaign
    pause_res = pause_campaign(campaign_id=camp_out.id, db=db, current_user=user)
    assert pause_res["status"] == "success"
