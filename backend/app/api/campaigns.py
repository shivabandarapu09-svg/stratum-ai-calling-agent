from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Campaign, CampaignContact, Customer, Agent, User
from app.security import get_current_user
from app.schemas import CampaignCreate, CampaignOut

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

@router.get("", response_model=List[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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
            agent_name=c.organization.agents[0].name if c.organization.agents else "Krishi AI",
            status=c.status,
            total_contacts=c.total_contacts,
            completed_calls=c.completed_calls,
            successful_calls=c.successful_calls,
            retry_limit=c.retry_limit,
            created_at=c.created_at
        ))
    return out

@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.id == payload.agent_id, Agent.organization_id == user.organization_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    camp = Campaign(
        organization_id=user.organization_id,
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
        # Find or create customer
        cust = (
            db.query(Customer)
            .filter(Customer.phone == phone, Customer.organization_id == user.organization_id)
            .first()
        )
        if not cust:
            cust = Customer(
                organization_id=user.organization_id,
                name=item.get("name"),
                phone=phone,
                preferred_language=agent.default_language or "te",
                status="Lead",
                tags=[camp.name]
            )
            db.add(cust)
            db.flush()

        contact = CampaignContact(
            campaign_id=camp.id,
            customer_id=cust.id,
            status="pending",
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
def start_campaign(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    camp = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.organization_id == user.organization_id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    camp.status = "running"
    db.commit()
    return {"status": "success", "message": f"Campaign '{camp.name}' is now running"}

@router.post("/{campaign_id}/pause")
def pause_campaign(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    camp = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.organization_id == user.organization_id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    camp.status = "paused"
    db.commit()
    return {"status": "success", "message": f"Campaign '{camp.name}' paused"}
