from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Campaign, CampaignContact, Customer, Agent, Organization, User, Call
from app.api.auth import get_current_user, resolve_current_user
from app.schemas import CampaignCreate, CampaignOut

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


def check_trai_calling_hours(
    start_hour: int = 9,
    end_hour: int = 20,
    current_dt: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    TRAI (Telecom Regulatory Authority of India) Telemarketing Calling Window Policy:
    Strictly prohibits automated commercial / outbound dials outside 09:00 - 20:00 IST.
    """
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = (current_dt or datetime.now(timezone.utc)).astimezone(ist_tz)
    current_hour = now_ist.hour
    if start_hour <= current_hour < end_hour:
        return True, f"Calling hours active in IST ({now_ist.strftime('%I:%M %p IST')})"
    return (
        False,
        f"Calling window closed. TRAI limits automated dials between {start_hour:02d}:00 and {end_hour:02d}:00 IST. Current time: {now_ist.strftime('%I:%M %p IST')}.",
    )

@router.get("", response_model=List[CampaignOut])
def list_campaigns(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = resolve_current_user(current_user, db)
    camps = (
        db.query(Campaign)
        .filter(Campaign.organization_id == user.organization_id)
        .order_by(Campaign.created_at.desc())
        .all()
    )
    out = []
    for c in camps:
        out.append(CampaignOut(
            id=c.id,
            name=c.name,
            agent_id=c.agent_id,
            agent_name=c.organization.agents[0].name if c.organization.agents else "Stratum AI",
            status=c.status,
            total_contacts=c.total_contacts,
            completed_calls=c.completed_calls,
            successful_calls=c.successful_calls,
            retry_limit=c.retry_limit,
            created_at=c.created_at
        ))
    return out

@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = resolve_current_user(current_user, db)
    org_id = user.organization_id
    agent = db.query(Agent).filter(Agent.id == payload.agent_id, Agent.organization_id == org_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found in your organization")

    camp = Campaign(
        organization_id=org_id,
        agent_id=payload.agent_id,
        name=payload.name,
        status="draft",
        total_contacts=len(payload.contacts),
        completed_calls=0,
        successful_calls=0,
        retry_limit=payload.retry_limit,
        calling_hours_start=payload.calling_hours_start,
        calling_hours_end=payload.calling_hours_end
    )
    db.add(camp)
    db.flush()

    for item in payload.contacts:
        phone = item.get("phone")
        if not phone:
            continue
        # Find or create customer scoped to organization
        cust = db.query(Customer).filter(Customer.phone == phone, Customer.organization_id == org_id).first()
        if not cust:
            cust = Customer(
                organization_id=org_id,
                name=item.get("name"),
                phone=phone,
                preferred_language=agent.default_language or "te",
                status="Lead",
                tags=[camp.name]
            )
            db.add(cust)
            db.flush()

        is_dnc = (cust.status == "DNC") or ("DNC" in (cust.tags or [])) or ("dnc" in (cust.tags or []))
        contact = CampaignContact(
            campaign_id=camp.id,
            customer_id=cust.id,
            status="dnc" if is_dnc else "pending",
            attempts=0
        )
        db.add(contact)

    db.commit()
    db.refresh(camp)

    return CampaignOut(
        id=camp.id,
        name=camp.name,
        agent_id=camp.agent_id,
        agent_name=agent.name,
        status=camp.status,
        total_contacts=camp.total_contacts,
        completed_calls=camp.completed_calls,
        successful_calls=camp.successful_calls,
        retry_limit=camp.retry_limit,
        created_at=camp.created_at
    )

@router.post("/{campaign_id}/start")
def start_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = resolve_current_user(current_user, db)
    camp = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.organization_id == user.organization_id
    ).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    is_open, window_msg = check_trai_calling_hours(camp.calling_hours_start, camp.calling_hours_end)
    camp.status = "running"
    db.commit()
    return {
        "status": "success",
        "message": f"Campaign '{camp.name}' is now running",
        "trai_window_open": is_open,
        "trai_detail": window_msg,
    }

@router.post("/{campaign_id}/pause")
def pause_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = resolve_current_user(current_user, db)
    camp = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.organization_id == user.organization_id
    ).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    camp.status = "paused"
    db.commit()
    return {"status": "success", "message": f"Campaign '{camp.name}' paused"}

@router.post("/{campaign_id}/dispatch-batch")
def dispatch_campaign_batch(
    campaign_id: str,
    batch_size: int = 10,
    force_override_hours: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Durable database-backed outbound queue dispatcher.
    Enforces TRAI commercial calling window (09:00 - 20:00 IST) and DNC exclusion.
    Transitions pending campaign contacts into persistent Call records with direction='outbound'.
    """
    user = resolve_current_user(current_user, db)
    camp = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.organization_id == user.organization_id
    ).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if camp.status != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is in '{camp.status}' state. Start campaign before dispatching."
        )

    is_open, window_msg = check_trai_calling_hours(camp.calling_hours_start, camp.calling_hours_end)
    if not is_open and not force_override_hours:
        return {
            "status": "blocked",
            "reason": "calling_window_closed",
            "message": window_msg,
            "dispatched_count": 0,
            "calls": []
        }

    pending_contacts = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == camp.id,
            CampaignContact.status == "pending",
            CampaignContact.attempts < camp.retry_limit
        )
        .limit(batch_size)
        .all()
    )

    dispatched_calls = []
    for contact in pending_contacts:
        cust = contact.customer
        if not cust or cust.status == "DNC" or ("DNC" in (cust.tags or [])) or ("dnc" in (cust.tags or [])):
            contact.status = "dnc"
            continue

        call = Call(
            organization_id=user.organization_id,
            agent_id=camp.agent_id,
            customer_id=cust.id,
            customer_phone=cust.phone,
            direction="outbound",
            status="initiated",
            primary_language=cust.preferred_language or "hi",
        )
        db.add(call)
        db.flush()

        contact.status = "calling"
        contact.attempts += 1
        contact.last_attempt_at = datetime.now(timezone.utc).replace(tzinfo=None)
        dispatched_calls.append({"call_id": call.id, "phone": cust.phone, "customer_name": cust.name})

    db.commit()
    return {
        "status": "success",
        "campaign_id": camp.id,
        "dispatched_count": len(dispatched_calls),
        "trai_window_open": is_open,
        "calls": dispatched_calls
    }

@router.get("/{campaign_id}/progress")
def get_campaign_progress(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns durable queue contact breakdown, completion %, and compliance window state."""
    user = resolve_current_user(current_user, db)
    camp = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.organization_id == user.organization_id
    ).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    contacts = db.query(CampaignContact).filter(CampaignContact.campaign_id == camp.id).all()
    status_counts = {"pending": 0, "calling": 0, "completed": 0, "failed": 0, "dnc": 0}
    for c in contacts:
        st = c.status or "pending"
        status_counts[st] = status_counts.get(st, 0) + 1

    total = len(contacts)
    done = status_counts.get("completed", 0) + status_counts.get("failed", 0) + status_counts.get("dnc", 0)
    pct = round((done / total * 100), 1) if total > 0 else 0.0

    is_open, window_msg = check_trai_calling_hours(camp.calling_hours_start, camp.calling_hours_end)
    return {
        "campaign_id": camp.id,
        "name": camp.name,
        "status": camp.status,
        "total_contacts": total,
        "status_breakdown": status_counts,
        "completion_pct": pct,
        "trai_window_open": is_open,
        "trai_detail": window_msg
    }
