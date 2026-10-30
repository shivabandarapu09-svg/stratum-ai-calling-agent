"""
Unit & Integration Tests for Trajectory2Task Conversation Intelligence & Verifiable Call-3I Suite
==================================================================================================
Covers:
1. Ambiguous customer requests & multi-turn slot clarification (te, hi, en, ta, ml, kn).
2. Changing customer requests (mid-call slot revisions & goal switches without context loss).
3. Infeasible or policy-restricted requests (Policy-Infeasible vs. Tool-Infeasible).
4. Reliable tool calling (Pydantic schema validation, DAG preconditions, idempotency, retries, logging).
5. Multilingual detection & code-switching across Telugu, Hindi, English, Tamil, Malayalam, Kannada.
6. Closed-loop evaluation of all 18 verifiable `Call-3I` scenarios (`Pass^1` and `Pass^2`).
"""

import pytest
from app.database import SessionLocal, init_db
from app.models import Agent, Appointment, Call, Customer, Organization, ToolExecutionLog
from app.voice.belief_state import SessionBeliefState
from app.voice.tool_runtime import ToolExecutor
from app.voice.language_detector import detector
from app.voice.call_3i_benchmark import (
    CALL_3I_SCENARIOS,
    run_single_scenario,
    evaluate_call_3i_benchmark,
)


@pytest.fixture(scope="module")
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


# ==============================================================================
# 1. Unit Tests: Belief State, Ambiguity Detection & Intent Revision
# ==============================================================================

def test_belief_state_ambiguity_and_multilingual_clarification():
    belief = SessionBeliefState(template_domain="real_estate")
    state = belief.update_from_utterance("Hi, I want to schedule a site visit sometime next week.")

    assert state["active_intent"] == "schedule_site_visit"
    # All 3 required slots are missing or ambiguous
    assert set(state["missing_required_slots"]) == {"bhk_preference", "visit_date", "visit_time"}
    assert "visit_date" in state["ambiguous_slots_flagged"]

    # Verify concise natural clarification generation across all 6 target languages
    for lang in ["en", "hi", "te", "ta", "ml", "kn"]:
        q = belief.build_clarification_question(lang)
        assert len(q) > 15

    # Turn 2: Provide BHK and day -> only visit_time remains missing
    state2 = belief.update_from_utterance("I prefer a 3 BHK on Saturday.")
    assert state2["collected_slots"]["bhk_preference"] == "3 BHK"
    assert state2["collected_slots"]["visit_date"] == "Saturday"
    assert state2["missing_required_slots"] == ["visit_time"]

    # Turn 3: Provide time -> zero missing slots
    state3 = belief.update_from_utterance("Let's do 11:00 AM.")
    assert state3["missing_required_slots"] == []


def test_belief_state_intent_drift_and_slot_revision():
    belief = SessionBeliefState(template_domain="ecommerce_cod")
    s1 = belief.update_from_utterance("Please confirm my order COD-4421 for morning delivery.")
    assert s1["active_intent"] == "confirm_cod_order"
    assert s1["collected_slots"]["order_id"] == "COD-4421"
    assert s1["missing_required_slots"] == []

    # Mid-call goal switch to cancellation without repeating the Order ID
    s2 = belief.update_from_utterance("Wait, cancel my order instead because I ordered by mistake.")
    assert s2["active_intent"] == "cancel_cod_order"
    assert s2["collected_slots"]["order_id"] == "COD-4421"
    assert s2["collected_slots"]["cancellation_reason"] == "ordered by mistake"
    assert s2["intent_shifts_count"] == 1
    assert s2["missing_required_slots"] == []


# ==============================================================================
# 2. Unit Tests: Tool Runtime, Idempotency, DAG Preconditions & Fault Recovery
# ==============================================================================

def test_tool_executor_idempotency_and_audit_logging(db):
    org = db.query(Organization).first()
    agent = db.query(Agent).first()
    cust = db.query(Customer).first()

    call = Call(
        organization_id=org.id,
        agent_id=agent.id,
        customer_id=cust.id if cust else None,
        customer_phone="+919876543210",
        status="in_progress",
        primary_language="en",
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    belief = SessionBeliefState(template_domain="real_estate")
    belief.update_from_utterance("Calculate EMI for 80 Lakhs")
    executor = ToolExecutor(db=db, call=call, belief_state=belief)

    res1 = executor.run_calculate_emi()
    assert res1.status == "success"
    assert res1.idempotent_replay is False
    assert res1.output["monthly_emi_inr"] > 60000

    # Calling identical tool with identical arguments in the same call must replay idempotently
    res2 = executor.run_calculate_emi()
    assert res2.status == "success"
    assert res2.idempotent_replay is True
    assert res2.output["monthly_emi_inr"] == res1.output["monthly_emi_inr"]

    logs = db.query(ToolExecutionLog).filter(ToolExecutionLog.call_id == call.id).all()
    assert len(logs) == 1
    assert logs[0].tool_name == "calculate_emi_schedule"


def test_tool_executor_high_value_order_verification_policy(db):
    org = db.query(Organization).first()
    agent = db.query(Agent).first()
    call = Call(
        organization_id=org.id,
        agent_id=agent.id,
        customer_phone="+919876543210",
        status="in_progress",
        primary_language="en",
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    belief = SessionBeliefState(template_domain="ecommerce_cod")
    belief.update_from_utterance("Cancel order COD-5510 because I changed my mind")
    executor = ToolExecutor(db=db, call=call, belief_state=belief)

    # First attempt without OTP verification -> blocked as policy_infeasible
    results = executor.evaluate_and_run_turn_tools("Cancel order COD-5510 because I changed my mind")
    statuses = {r.tool_name: r.status for r in results}
    assert statuses["get_order_status"] == "success"
    assert statuses["cancel_cod_order"] == "policy_infeasible"

    # Provide OTP verification -> succeeds
    belief.update_from_utterance("My verification OTP code is 9876, please cancel order COD-5510")
    results_verified = executor.evaluate_and_run_turn_tools("My verification OTP code is 9876")
    statuses_v = {r.tool_name: r.status for r in results_verified}
    assert statuses_v["cancel_cod_order"] == "success"


# ==============================================================================
# 3. Unit Tests: Multilingual Detection (Telugu, Hindi, English, Tamil, Malayalam, Kannada)
# ==============================================================================

def test_multilingual_script_and_romanized_detection():
    # Malayalam native script
    ml_res = detector.analyze("നമസ്കാരം, എനിക്ക് 3 BHK ഫ്ലാറ്റ് വിവരങ്ങൾ വേണം")
    assert ml_res["detected_language"] == "ml"

    # Malayalam Romanized markers
    ml_rom = detector.analyze("Enikku malayalathil samsarikkanam, flat ethra vila?")
    assert ml_rom["detected_language"] == "ml"

    # Tamil native script
    ta_res = detector.analyze("வணக்கம், எனக்கு அப்பாயின்ட்மென்ட் புக் செய்ய வேண்டும்")
    assert ta_res["detected_language"] == "ta"

    # Kannada native script
    kn_res = detector.analyze("ನಮಸ್ಕಾರ, ನನಗೆ ಸೈಟ್ ವಿಸಿಟ್ ಬುಕ್ ಮಾಡಬೇಕು")
    assert kn_res["detected_language"] == "kn"

    # Explicit switch to Malayalam & Kannada
    assert detector.detect_explicit_switch("Can we switch to Malayalam please?") == "ml"
    assert detector.detect_explicit_switch("Please speak in Kannada") == "kn"
    assert detector.detect_explicit_switch("Switch to Tamil") == "ta"


# ==============================================================================
# 4. Closed-Loop Integration Tests: All 18 Verifiable `Call-3I` Scenarios
# ==============================================================================

@pytest.mark.parametrize("scenario", CALL_3I_SCENARIOS, ids=[s["scenario_id"] for s in CALL_3I_SCENARIOS])
def test_call_3i_verifiable_scenario(db, scenario):
    report = run_single_scenario(db, scenario)
    assert report["checks"]["db_state_match"] is True, f"DB check failed for {scenario['scenario_id']}: {report}"
    assert report["checks"]["required_actions_match"] is True, f"Required tools failed for {scenario['scenario_id']}: {report}"
    assert report["checks"]["prohibited_actions_match"] is True, f"Prohibited tools failed for {scenario['scenario_id']}: {report}"
    assert report["checks"]["comm_truthfulness_match"] is True, f"COMM check failed for {scenario['scenario_id']}: {report}"
    assert report["checks"]["language_accuracy_match"] is True, f"Language check failed for {scenario['scenario_id']}: {report}"
    assert report["passed"] is True


def test_call_3i_full_benchmark_pass_k_consistency(db):
    summary = evaluate_call_3i_benchmark(db, k_trials=2)
    assert summary["total_scenarios"] == 18
    assert summary["pass_k_score"] == 1.0
    assert summary["metrics"]["policy_compliance_rate"] == 1.0
    assert summary["metrics"]["multilingual_accuracy"] == 1.0
    assert summary["metrics"]["avg_turn_latency_ms"] < 500.0
