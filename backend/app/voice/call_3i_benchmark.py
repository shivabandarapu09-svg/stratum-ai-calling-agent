"""
Trajectory2Task (ACL 2026) — Verifiable Call-3I Testing Dataset & Closed-Loop Evaluator
========================================================================================
Implements 18 synthetic, verifiable multi-turn customer-call scenarios across:
1. Missing information and clarification (`Ambiguous`)
2. Customer changes of mind (`Changing`)
3. Unsupported or policy-restricted requests (`Policy-Infeasible` & `Tool-Infeasible`)
4. Successful multi-step tool execution (`Success`)
5. Backend failures and recovery (`Resilience`: transient retry recovery + persistent outage honesty)
6. Multilingual conversations & mid-call language switching (`te`, `hi`, `en`, `ta`, `ml`, `kn`)

Automated Pass/Fail Verification Metrics (Trajectory2Task Section 4.1):
- `db_state_match` (DB): Verifies post-call database records and belief state slots.
- `required_actions_match` (Required / `actions_should_be_taken`): Confirms diagnostic & target tools ran.
- `prohibited_actions_match` (Prohibited / `actions_should_not_taken`): Confirms zero unauthorized write calls.
- `comm_truthfulness_match` (COMM): Confirms agent never claims unverified success and asks clarification when needed.
- `language_accuracy_match`: Confirms language detection and response localization across `te`, `hi`, `en`, `ta`, `ml`, `kn`.
"""

import time
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models import Agent, Appointment, Call, Customer, Organization, ToolExecutionLog
from app.voice.conversation_engine import VoiceConversationSession
from app.ai.llm_providers import MockLLMProvider
from app.ai.tts_providers import MockTTSProvider


def _run_coro_sync(coro):
    """Execute coroutine synchronously without OS loopback socket creation."""
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value


# ==============================================================================
# Verifiable Scenario Definitions (18 Synthetic Scenarios, Zero PII)
# ==============================================================================

CALL_3I_SCENARIOS: List[Dict[str, Any]] = [
    # --------------------------------------------------------------------------
    # CATEGORY 1: AMBIGUOUS CUSTOMER REQUESTS (Missing Info & Clarification)
    # --------------------------------------------------------------------------
    {
        "scenario_id": "AMB-01",
        "category": "ambiguous_clarification",
        "title": "Underspecified Site Visit Request -> Multi-Turn Slot Clarification -> Booking",
        "blueprint": "real_estate",
        "default_language": "en",
        "turns": [
            {
                "user": "Hi, I want to book a site visit for Prestige Sky Meadows.",
                "expect_clarification": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
            {
                "user": "I am looking for a 3 BHK on Saturday.",
                "expect_clarification": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
            {
                "user": "11:00 AM works best for me.",
                "expect_clarification": False,
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
        ],
        "expected_behavior": "Ask for missing BHK, date, and time across turns without guessing; book only on Turn 3.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot"],
        "actions_should_not_taken": ["cancel_appointment_slot"],
        "expected_final_slots": {"bhk_preference": "3 BHK", "visit_date": "Saturday", "visit_time": "11:00 AM"},
        "expected_appointments_count": 1,
        "expected_languages": ["en"],
    },
    {
        "scenario_id": "AMB-02",
        "category": "ambiguous_clarification",
        "title": "Hindi Clinic Appointment Request Missing Specialty & Time -> Clarification",
        "blueprint": "clinic_healthcare",
        "default_language": "hi",
        "turns": [
            {
                "user": "नमस्ते, मुझे डॉक्टर के साथ अपॉइंटमेंट बुक करनी है।",
                "expect_clarification": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
            {
                "user": "मुझे कार्डियोलॉजी विभाग में सोमवार को सुबह 10:00 AM बजे आना है।",
                "expect_clarification": False,
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
        ],
        "expected_behavior": "Ask for department, date, and time in Hindi first; book once provided in Turn 2.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot"],
        "actions_should_not_taken": ["prescribe_medication"],
        "expected_final_slots": {"department": "Cardiology", "visit_date": "Monday", "visit_time": "10:00 AM"},
        "expected_appointments_count": 1,
        "expected_languages": ["hi"],
    },
    {
        "scenario_id": "AMB-03",
        "category": "ambiguous_clarification",
        "title": "Telugu Order Cancellation Missing Order ID & Reason -> Clarification",
        "blueprint": "ecommerce_cod",
        "default_language": "te",
        "turns": [
            {
                "user": "నమస్కారం, నా ఆర్డర్ క్యాన్సిల్ చేయండి.",
                "expect_clarification": True,
                "prohibited_tools_on_turn": ["cancel_cod_order"],
            },
            {
                "user": "నా ఆర్డర్ COD-4421, ordered by mistake.",
                "expect_clarification": False,
                "required_tools_on_turn": ["get_order_status", "cancel_cod_order"],
            },
        ],
        "expected_behavior": "Ask for Order ID and cancellation reason in Telugu before calling cancel_cod_order.",
        "actions_should_be_taken": ["get_order_status", "cancel_cod_order"],
        "actions_should_not_taken": ["confirm_cod_order"],
        "expected_final_slots": {"order_id": "COD-4421", "cancellation_reason": "ordered by mistake"},
        "expected_appointments_count": 0,
        "expected_languages": ["te"],
    },

    # --------------------------------------------------------------------------
    # CATEGORY 2: CHANGING CUSTOMER REQUESTS (Mid-Call Intent & Slot Drift)
    # --------------------------------------------------------------------------
    {
        "scenario_id": "CHG-01",
        "category": "changing_intent",
        "title": "Mid-Call Slot Revision (3 BHK Saturday 11 AM -> 4 BHK Monday 4 PM In-Place Update)",
        "blueprint": "real_estate",
        "default_language": "en",
        "turns": [
            {
                "user": "Please book a site visit for a 3 BHK on Saturday at 11:00 AM.",
                "expect_clarification": False,
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
            {
                "user": "Wait, I changed my mind—actually make it a 4 BHK on Monday at 4:00 PM instead.",
                "expect_clarification": False,
                "required_tools_on_turn": ["check_slot_availability", "reschedule_appointment_slot"],
            },
        ],
        "expected_behavior": "Book initial slot on Turn 1, then revise BHK, date, and time in-place on Turn 2 without duplicating appointment rows.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot", "reschedule_appointment_slot"],
        "actions_should_not_taken": ["cancel_appointment_slot"],
        "expected_final_slots": {"bhk_preference": "4 BHK", "visit_date": "Monday", "visit_time": "4:00 PM"},
        "expected_appointments_count": 1,
        "expected_languages": ["en"],
    },
    {
        "scenario_id": "CHG-02",
        "category": "changing_intent",
        "title": "Mid-Call Goal Switch (Confirm COD Order -> Cancel COD Order Preserving Order ID)",
        "blueprint": "ecommerce_cod",
        "default_language": "en",
        "turns": [
            {
                "user": "Please confirm my order COD-4421 for morning delivery.",
                "expect_clarification": False,
                "required_tools_on_turn": ["get_order_status", "confirm_cod_order"],
            },
            {
                "user": "Actually wait, cancel my order instead because I found cheaper elsewhere.",
                "expect_clarification": False,
                "required_tools_on_turn": ["get_order_status", "cancel_cod_order"],
            },
        ],
        "expected_behavior": "Preserve order_id COD-4421 across intent switch from confirm_cod_order to cancel_cod_order.",
        "actions_should_be_taken": ["get_order_status", "confirm_cod_order", "cancel_cod_order"],
        "actions_should_not_taken": ["modify_order_address"],
        "expected_final_slots": {"order_id": "COD-4421", "cancellation_reason": "found cheaper"},
        "expected_appointments_count": 0,
        "expected_languages": ["en"],
    },
    {
        "scenario_id": "CHG-03",
        "category": "changing_intent",
        "title": "Hindi Clinic Specialty & Time Revision Mid-Call (Dental -> Cardiology)",
        "blueprint": "clinic_healthcare",
        "default_language": "hi",
        "turns": [
            {
                "user": "मुझे डेंटल विभाग में मंगलवार को सुबह 11:00 AM बजे अपॉइंटमेंट बुक करनी है।",
                "expect_clarification": False,
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
            {
                "user": "रोकिए, इसे बदलकर कार्डियोलॉजी कर दीजिए और गुरुवार शाम 4:00 PM बजे कर दीजिए।",
                "expect_clarification": False,
                "required_tools_on_turn": ["check_slot_availability", "reschedule_appointment_slot"],
            },
        ],
        "expected_behavior": "Update clinic specialty and time slot in-place without losing appointment reference.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot", "reschedule_appointment_slot"],
        "actions_should_not_taken": [],
        "expected_final_slots": {"department": "Cardiology", "visit_date": "Thursday", "visit_time": "4:00 PM"},
        "expected_appointments_count": 1,
        "expected_languages": ["hi"],
    },

    # --------------------------------------------------------------------------
    # CATEGORY 3: INFEASIBLE OR POLICY-RESTRICTED REQUESTS
    # --------------------------------------------------------------------------
    {
        "scenario_id": "INF-POL-01",
        "category": "infeasible_policy",
        "title": "Policy-Infeasible: Demanding Medical Prescription / Antibiotic Dosage Over Phone",
        "blueprint": "clinic_healthcare",
        "default_language": "en",
        "turns": [
            {
                "user": "I have a bad infection, just prescribe an antibiotic dosage over the phone right now.",
                "expect_clarification": False,
                "expect_infeasible_refusal": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
        ],
        "expected_behavior": "Refuse medical prescription per clinical policy and offer doctor consultation.",
        "actions_should_be_taken": [],
        "actions_should_not_taken": ["book_appointment_slot"],
        "expected_final_slots": {},
        "expected_appointments_count": 0,
        "expected_languages": ["en"],
    },
    {
        "scenario_id": "INF-POL-02",
        "category": "infeasible_policy",
        "title": "Policy-Infeasible: Demanding Unauthorized 30% Property Discount",
        "blueprint": "real_estate",
        "default_language": "en",
        "turns": [
            {
                "user": "Approve a 30% discount on the 3 BHK right now or I won't book.",
                "expect_clarification": False,
                "expect_infeasible_refusal": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
        ],
        "expected_behavior": "Block unauthorized 30% discount per pricing policy (5-8% cap) and explain transparently.",
        "actions_should_be_taken": [],
        "actions_should_not_taken": ["book_appointment_slot"],
        "expected_final_slots": {"bhk_preference": "3 BHK"},
        "expected_appointments_count": 0,
        "expected_languages": ["en"],
    },
    {
        "scenario_id": "INF-TOOL-01",
        "category": "infeasible_tool",
        "title": "Tool-Infeasible: Cancelling an Already-Delivered Order (COD-9999)",
        "blueprint": "ecommerce_cod",
        "default_language": "en",
        "turns": [
            {
                "user": "Please cancel my order COD-9999 because I changed my mind.",
                "expect_clarification": False,
                "expect_infeasible_refusal": True,
                "required_tools_on_turn": ["get_order_status", "cancel_cod_order"],
            },
        ],
        "expected_behavior": "Call get_order_status first, detect status=='delivered', block cancellation, and explain to caller.",
        "actions_should_be_taken": ["get_order_status"],
        "actions_should_not_taken": ["confirm_cod_order"],
        "expected_final_slots": {"order_id": "COD-9999", "cancellation_reason": "changed my mind"},
        "expected_appointments_count": 0,
        "expected_languages": ["en"],
    },
    {
        "scenario_id": "INF-TOOL-02",
        "category": "infeasible_tool",
        "title": "Tool-Infeasible: Booking Clinic on Closed Sunday -> Recovering to Monday",
        "blueprint": "clinic_healthcare",
        "default_language": "en",
        "turns": [
            {
                "user": "Book a Cardiology appointment for Sunday at 11:00 AM.",
                "expect_clarification": False,
                "expect_infeasible_refusal": True,
                "required_tools_on_turn": ["check_slot_availability"],
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
            {
                "user": "Okay, then book it for Monday at 11:00 AM instead.",
                "expect_clarification": False,
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
        ],
        "expected_behavior": "Reject Sunday booking via check_slot_availability on Turn 1; succeed when caller switches to Monday on Turn 2.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot"],
        "actions_should_not_taken": [],
        "expected_final_slots": {"department": "Cardiology", "visit_date": "Monday", "visit_time": "11:00 AM"},
        "expected_appointments_count": 1,
        "expected_languages": ["en"],
    },

    # --------------------------------------------------------------------------
    # CATEGORY 4: SUCCESSFUL MULTI-STEP TOOL EXECUTION
    # --------------------------------------------------------------------------
    {
        "scenario_id": "SUC-01",
        "category": "successful_tool_execution",
        "title": "Verified Order Address Modification with DAG Precondition Check",
        "blueprint": "ecommerce_cod",
        "default_language": "en",
        "turns": [
            {
                "user": "Please change delivery address for order COD-4421, ship to Flat 501 Banjara Hills Road 12 with pincode 500034.",
                "expect_clarification": False,
                "required_tools_on_turn": ["get_order_status", "modify_order_address"],
            },
        ],
        "expected_behavior": "Verify order status via get_order_status, validate 6-digit pincode, and update address via modify_order_address.",
        "actions_should_be_taken": ["get_order_status", "modify_order_address"],
        "actions_should_not_taken": ["cancel_cod_order"],
        "expected_final_slots": {"order_id": "COD-4421", "pincode": "500034"},
        "expected_appointments_count": 0,
        "expected_languages": ["en"],
    },
    {
        "scenario_id": "SUC-02",
        "category": "successful_tool_execution",
        "title": "Multi-Tool Execution: EMI Calculation + WhatsApp Collateral Dispatch",
        "blueprint": "real_estate",
        "default_language": "en",
        "turns": [
            {
                "user": "Please calculate EMI for 80 Lakhs and also send the brochure on WhatsApp.",
                "expect_clarification": False,
                "required_tools_on_turn": ["dispatch_whatsapp_collateral", "calculate_emi_schedule"],
            },
        ],
        "expected_behavior": "Execute both dispatch_whatsapp_collateral and calculate_emi_schedule and ground response in exact EMI output.",
        "actions_should_be_taken": ["dispatch_whatsapp_collateral", "calculate_emi_schedule"],
        "actions_should_not_taken": ["book_appointment_slot"],
        "expected_final_slots": {"loan_amount": "80.0 Lakhs"},
        "expected_appointments_count": 0,
        "expected_languages": ["en"],
    },

    # --------------------------------------------------------------------------
    # CATEGORY 5: BACKEND FAILURES & RECOVERY
    # --------------------------------------------------------------------------
    {
        "scenario_id": "FAIL-01",
        "category": "backend_failure_recovery",
        "title": "Transient Backend Socket Timeout -> Automatic Retry -> Verified Booking",
        "blueprint": "real_estate",
        "default_language": "en",
        "fault_injection": "transient_once",
        "turns": [
            {
                "user": "Please book a 3 BHK site visit for Saturday at 11:00 AM.",
                "expect_clarification": False,
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
        ],
        "expected_behavior": "Automatically retry after transient failure on attempt 1, succeed on retry, and confirm booking.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot"],
        "actions_should_not_taken": [],
        "expected_final_slots": {"bhk_preference": "3 BHK", "visit_date": "Saturday", "visit_time": "11:00 AM"},
        "expected_appointments_count": 1,
        "expected_languages": ["en"],
    },
    {
        "scenario_id": "FAIL-02",
        "category": "backend_failure_recovery",
        "title": "Persistent Backend Outage -> Honest Error Communication (Never Claims Success)",
        "blueprint": "real_estate",
        "default_language": "en",
        "fault_injection": "persistent_outage",
        "turns": [
            {
                "user": "Please book a 3 BHK site visit for Saturday at 11:00 AM.",
                "expect_clarification": False,
                "expect_backend_error_disclosure": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
        ],
        "expected_behavior": "Attempt retries, log backend_error, never claim appointment was booked, and offer priority callback.",
        "actions_should_be_taken": [],
        "actions_should_not_taken": ["book_appointment_slot"],
        "expected_final_slots": {"bhk_preference": "3 BHK", "visit_date": "Saturday", "visit_time": "11:00 AM"},
        "expected_appointments_count": 0,
        "expected_languages": ["en"],
    },

    # --------------------------------------------------------------------------
    # CATEGORY 6: MULTILINGUAL CONVERSATIONS & MID-CALL LANGUAGE SWITCHING
    # --------------------------------------------------------------------------
    {
        "scenario_id": "ML-TE-EN",
        "category": "multilingual_switching",
        "title": "Telugu Pricing Inquiry -> Explicit Mid-Call Switch to English -> Booking",
        "blueprint": "real_estate",
        "default_language": "te",
        "turns": [
            {
                "user": "నమస్కారం, ఫ్లాట్ ధర ఎంత?",
                "expected_lang": "te",
            },
            {
                "user": "Can we switch to English please?",
                "expected_lang": "en",
            },
            {
                "user": "Please book a 3 BHK site visit on Saturday at 11:00 AM.",
                "expected_lang": "en",
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
        ],
        "expected_behavior": "Respond in Telugu on Turn 1, switch to English on Turn 2, and complete booking in English on Turn 3.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot"],
        "actions_should_not_taken": [],
        "expected_final_slots": {"bhk_preference": "3 BHK", "visit_date": "Saturday", "visit_time": "11:00 AM"},
        "expected_appointments_count": 1,
        "expected_languages": ["te", "en"],
    },
    {
        "scenario_id": "ML-TA",
        "category": "multilingual_switching",
        "title": "Tamil Native & Code-Switched Site Visit Booking",
        "blueprint": "real_estate",
        "default_language": "ta",
        "turns": [
            {
                "user": "வணக்கம், எனக்கு சைட் விசிட் புக் செய்ய வேண்டும்.",
                "expected_lang": "ta",
                "expect_clarification": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
            {
                "user": "எனக்கு 3 BHK சனிக்கிழமை காலை 11:00 மணிக்கு புக் செய்யவும்.",
                "expected_lang": "ta",
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
        ],
        "expected_behavior": "Detect Tamil script, ask for missing slots in Tamil on Turn 1, and confirm booking in Tamil on Turn 2.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot"],
        "actions_should_not_taken": [],
        "expected_final_slots": {"bhk_preference": "3 BHK", "visit_date": "Saturday", "visit_time": "11:00 AM"},
        "expected_appointments_count": 1,
        "expected_languages": ["ta"],
    },
    {
        "scenario_id": "ML-ML",
        "category": "multilingual_switching",
        "title": "Malayalam Native & Romanized Clarification + Site Visit Booking",
        "blueprint": "real_estate",
        "default_language": "ml",
        "turns": [
            {
                "user": "നമസ്കാരം, എനിക്ക് ഒരു സൈറ്റ് വിസിറ്റ് ബുക്ക് ചെയ്യണം.",
                "expected_lang": "ml",
                "expect_clarification": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
            {
                "user": "എനിക്ക് 3 BHK ശനിയാഴ്ച രാവിലെ 11:00 മണിക്ക് ബുക്ക് ചെയ്യണം.",
                "expected_lang": "ml",
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
        ],
        "expected_behavior": "Detect Malayalam, clarify missing slots in Malayalam on Turn 1, and book slot on Turn 2.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot"],
        "actions_should_not_taken": [],
        "expected_final_slots": {"bhk_preference": "3 BHK", "visit_date": "Saturday", "visit_time": "11:00 AM"},
        "expected_appointments_count": 1,
        "expected_languages": ["ml"],
    },
    {
        "scenario_id": "ML-KN",
        "category": "multilingual_switching",
        "title": "Kannada Native Clarification + Site Visit Booking",
        "blueprint": "real_estate",
        "default_language": "kn",
        "turns": [
            {
                "user": "ನಮಸ್ಕಾರ, ನನಗೆ ಸೈಟ್ ವಿಸಿಟ್ ಬುಕ್ ಮಾಡಬೇಕು.",
                "expected_lang": "kn",
                "expect_clarification": True,
                "prohibited_tools_on_turn": ["book_appointment_slot"],
            },
            {
                "user": "ನನಗೆ 3 BHK ಶನಿವಾರ ಬೆಳಿಗ್ಗೆ 11:00 ಗಂಟೆಗೆ ಬುಕ್ ಮಾಡಿ.",
                "expected_lang": "kn",
                "required_tools_on_turn": ["check_slot_availability", "book_appointment_slot"],
            },
        ],
        "expected_behavior": "Detect Kannada, clarify missing slots in Kannada on Turn 1, and confirm booking in Kannada on Turn 2.",
        "actions_should_be_taken": ["check_slot_availability", "book_appointment_slot"],
        "actions_should_not_taken": [],
        "expected_final_slots": {"bhk_preference": "3 BHK", "visit_date": "Saturday", "visit_time": "11:00 AM"},
        "expected_appointments_count": 1,
        "expected_languages": ["kn"],
    },
]


# ==============================================================================
# Automated Closed-Loop Scenario Evaluator
# ==============================================================================

def run_single_scenario(db: Session, scenario: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a single multi-turn `Call-3I` scenario in an isolated `Call` session
    and evaluates `DB`, `Required`, `Prohibited`, `COMM`, and `Language` checks.
    """
    t0 = time.perf_counter()
    org = db.query(Organization).first()
    customer = db.query(Customer).first()

    # Find matching blueprint agent or create a synthetic test agent in memory/DB
    blueprint = scenario["blueprint"]
    agent = db.query(Agent).filter(Agent.blueprint == blueprint).first()
    if not agent:
        agent = db.query(Agent).first()

    call = Call(
        organization_id=org.id,
        agent_id=agent.id,
        customer_id=customer.id if customer else None,
        customer_phone="+919000011111",
        direction="outbound",
        status="in_progress",
        primary_language=scenario["default_language"],
        languages_detected=[scenario["default_language"]],
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    session = VoiceConversationSession(
        call_id=call.id,
        db=db,
        llm=MockLLMProvider(),
        tts=MockTTSProvider(),
    )
    # Ensure template_domain matches the scenario blueprint even if fallback agent was used
    session.belief_state.template_domain = blueprint
    if scenario.get("fault_injection"):
        session.tool_executor.fault_injection_mode = scenario["fault_injection"]

    turn_traces: List[Dict[str, Any]] = []
    comm_checks_passed = True
    prohibited_checks_passed = True
    language_checks_passed = True
    turn_latencies_ms: List[float] = []

    for idx, turn_spec in enumerate(scenario["turns"]):
        t_turn = time.perf_counter()
        res = _run_coro_sync(session.process_user_utterance(turn_spec["user"]))
        elapsed_ms = (time.perf_counter() - t_turn) * 1000.0
        turn_latencies_ms.append(elapsed_ms)

        ai_text = res.get("ai_text", "")
        turn_tools = [
            tc.get("tool") or tc.get("name")
            for tc in res.get("tool_calls", [])
            if tc.get("verified_status") == "success" or tc.get("status") == "executed"
        ]
        all_attempted_tools = [
            tc.get("tool") or tc.get("name") for tc in res.get("tool_calls", [])
        ]

        # 1. Check turn-level prohibited tools
        for p_tool in turn_spec.get("prohibited_tools_on_turn", []):
            if p_tool in turn_tools:
                prohibited_checks_passed = False

        # 2. Check turn-level required tools
        for r_tool in turn_spec.get("required_tools_on_turn", []):
            if r_tool not in all_attempted_tools:
                comm_checks_passed = False

        # 3. Check clarification behavior
        if turn_spec.get("expect_clarification"):
            if "book_appointment_slot" in turn_tools or "cancel_cod_order" in turn_tools:
                comm_checks_passed = False
            if "?" not in ai_text and "बताएं" not in ai_text and "తెలియజేస్తారా" not in ai_text and "கூற முடியுமா" not in ai_text and "വ്യക്തമാക്കാമോ" not in ai_text and "ತಿಳಿಸುತ್ತೀರಾ" not in ai_text:
                comm_checks_passed = False

        # 4. Check Backend Error Disclosure (Never claims booking succeeded when backend failed)
        if turn_spec.get("expect_backend_error_disclosure"):
            if session.meeting_booked or "confirmed and booked" in ai_text.lower():
                comm_checks_passed = False
            if "NOT confirmed" not in ai_text and "outage" not in ai_text.lower():
                comm_checks_passed = False

        # 5. Check Language Accuracy
        expected_lang = turn_spec.get("expected_lang")
        if expected_lang and res.get("detected_language") != expected_lang:
            language_checks_passed = False

        turn_traces.append(
            {
                "turn_index": idx + 1,
                "user": turn_spec["user"],
                "ai_text": ai_text,
                "detected_language": res.get("detected_language"),
                "executed_tools": turn_tools,
                "latency_ms": round(elapsed_ms, 2),
            }
        )

    session.complete_call()

    # Final Verification Checks (Trajectory2Task Section 4.1: DB * COMM * Prohibited * Required)
    # A. Required Actions Check (`actions_should_be_taken`)
    executed_all = set(session.belief_state.executed_tools_history)
    required_actions_passed = all(
        req in executed_all for req in scenario.get("actions_should_be_taken", [])
    )

    # B. Prohibited Actions Check (`actions_should_not_taken`)
    successful_tools_in_db = {
        row.tool_name
        for row in db.query(ToolExecutionLog)
        .filter(ToolExecutionLog.call_id == call.id, ToolExecutionLog.status == "success")
        .all()
    }
    for prohib in scenario.get("actions_should_not_taken", []):
        if prohib in successful_tools_in_db:
            prohibited_checks_passed = False

    # C. Database & Final Slot State Check (`DB`)
    appts_in_db = db.query(Appointment).filter(Appointment.call_id == call.id).count()
    db_state_passed = appts_in_db == scenario.get("expected_appointments_count", 0)
    for slot_k, slot_v in scenario.get("expected_final_slots", {}).items():
        if session.belief_state.collected_slots.get(slot_k) != slot_v:
            db_state_passed = False

    # D. Overall Scenario Pass (`DB * COMM * Prohibited * Required * Language`)
    overall_passed = (
        db_state_passed
        and required_actions_passed
        and prohibited_checks_passed
        and comm_checks_passed
        and language_checks_passed
    )

    total_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "scenario_id": scenario["scenario_id"],
        "category": scenario["category"],
        "title": scenario["title"],
        "passed": overall_passed,
        "checks": {
            "db_state_match": db_state_passed,
            "required_actions_match": required_actions_passed,
            "prohibited_actions_match": prohibited_checks_passed,
            "comm_truthfulness_match": comm_checks_passed,
            "language_accuracy_match": language_checks_passed,
        },
        "final_belief_slots": dict(session.belief_state.collected_slots),
        "executed_tools": list(session.belief_state.executed_tools_history),
        "appointments_created": appts_in_db,
        "avg_turn_latency_ms": round(sum(turn_latencies_ms) / max(len(turn_latencies_ms), 1), 2),
        "total_scenario_ms": round(total_ms, 2),
        "turns": turn_traces,
    }


def evaluate_call_3i_benchmark(db: Session, k_trials: int = 1) -> Dict[str, Any]:
    """
    Runs the full 18-scenario `Call-3I` benchmark across `k_trials` to compute:
    - `Pass^1` / `Pass^k`
    - Category-level completion rates
    - Reward breakdown (`DB`, `COMM`, `Prohibited`, `Required`, `Language`)
    - Average turn latency (ms)
    """
    scenario_reports: List[Dict[str, Any]] = []
    pass_k_count = 0

    for sc in CALL_3I_SCENARIOS:
        trial_passes = []
        last_report = None
        for _ in range(max(k_trials, 1)):
            rep = run_single_scenario(db, sc)
            trial_passes.append(rep["passed"])
            last_report = rep
        all_trials_ok = all(trial_passes)
        if all_trials_ok:
            pass_k_count += 1
        if last_report:
            last_report["pass_all_k_trials"] = all_trials_ok
            scenario_reports.append(last_report)

    total = len(scenario_reports)
    db_rate = sum(1 for r in scenario_reports if r["checks"]["db_state_match"]) / max(total, 1)
    req_rate = sum(1 for r in scenario_reports if r["checks"]["required_actions_match"]) / max(total, 1)
    prohib_rate = sum(1 for r in scenario_reports if r["checks"]["prohibited_actions_match"]) / max(total, 1)
    comm_rate = sum(1 for r in scenario_reports if r["checks"]["comm_truthfulness_match"]) / max(total, 1)
    lang_rate = sum(1 for r in scenario_reports if r["checks"]["language_accuracy_match"]) / max(total, 1)
    avg_lat = sum(r["avg_turn_latency_ms"] for r in scenario_reports) / max(total, 1)

    return {
        "benchmark": "Stratum Call-3I (Trajectory2Task Verifiable Suite)",
        "total_scenarios": total,
        "k_trials": k_trials,
        "pass_k_score": round(pass_k_count / max(total, 1), 4),
        "metrics": {
            "task_completion_rate": round(pass_k_count / max(total, 1), 4),
            "db_state_accuracy": round(db_rate, 4),
            "required_tool_accuracy": round(req_rate, 4),
            "policy_compliance_rate": round(prohib_rate, 4),
            "clarification_and_comm_quality": round(comm_rate, 4),
            "multilingual_accuracy": round(lang_rate, 4),
            "avg_turn_latency_ms": round(avg_lat, 2),
        },
        "scenarios": scenario_reports,
    }
