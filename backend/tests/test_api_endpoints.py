import pytest
from app.main import health_check, root
from app.database import SessionLocal, init_db
from app.api.agents import list_agents, get_blueprint_templates, get_available_voices
from app.api.analytics import get_dashboard_analytics
from app.api.calls import list_calls, get_call_detail
from app.api.leads import simulate_speed_to_lead
from app.schemas import SpeedToLeadSimulateRequest

@pytest.fixture(scope="module")
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()

def test_health_endpoint(db):
    data = health_check()
    assert data["status"] == "healthy"
    assert "Stratum" in data["platform"]

def test_list_agents(db):
    agents = list_agents(db=db)
    assert len(agents) >= 5
    names = [a.name for a in agents]
    assert "Aarav" in names or "Kavya" in names

def test_blueprint_templates(db):
    blueprints = get_blueprint_templates()
    assert len(blueprints) >= 6
    bps = [b["blueprint"] for b in blueprints]
    assert "real_estate" in bps
    assert "clinic_healthcare" in bps
    assert "bfsi_fintech" in bps

def test_available_voices(db):
    voices = get_available_voices()
    assert "hi" in voices
    assert "en" in voices
    assert "personas" in voices["hi"]

def test_dashboard_analytics(db):
    data = get_dashboard_analytics(db=db)
    assert "kpis" in data
    assert "languages" in data
    assert "outcomes" in data
    assert data["kpis"].total_calls >= 1
    assert data["kpis"].speed_to_lead_avg_seconds > 0

def test_list_and_get_call(db):
    calls = list_calls(language=None, status_filter=None, db=db)
    assert len(calls) >= 1
    target = next((c for c in calls if c.id == "call-demo-001" or c.status in ("completed", "transferred")), calls[0])
    call_id = target.id
    detail = get_call_detail(call_id=call_id, db=db)
    assert detail.id == call_id
    assert len(detail.transcripts) >= 1

def test_speed_to_lead_simulate(db):
    agents = list_agents(db=db)
    agent_id = agents[0].id

    payload = SpeedToLeadSimulateRequest(
        agent_id=agent_id,
        lead_name="Rohan Mehra",
        phone="+919811223344",
        source="meta_ads",
        product_interest="Luxury Apartment"
    )
    data = simulate_speed_to_lead(payload=payload, db=db)
    assert data.status == "initiated"
    assert data.speed_to_lead_time_sec > 0
