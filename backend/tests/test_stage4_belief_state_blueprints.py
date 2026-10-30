"""
Unit Tests for Stage 4: Belief State Expansion across Industry Blueprints
========================================================================
Validates POMDP belief state tracking, slot extraction, intent detection,
ambiguity clarification, and infeasibility gatekeeping for:
1. Education Admissions (EdTech Counselor)
2. BFSI & FinTech (Credit Advisor)
3. B2B SaaS SDR (Speed-to-Lead)
4. Multilingual clarification in en, hi, te, ta, ml, kn.
"""

import pytest
from app.voice.belief_state import SessionBeliefState


def test_education_admissions_blueprint():
    # 1. Ambiguity detection on initial contact
    belief = SessionBeliefState(template_domain="education_admissions")
    s1 = belief.update_from_utterance("Hi, I want to book a counseling session for admissions.")
    assert s1["active_intent"] == "book_counseling_session"
    assert "course_interest" in s1["missing_required_slots"]
    assert "interview_date" in s1["missing_required_slots"]
    assert "interview_time" in s1["missing_required_slots"]

    # Natural clarification question in Hindi and Telugu
    q_hi = belief.build_clarification_question("hi")
    assert "प्रोग्राम" in q_hi or "काउंसलिंग" in q_hi
    q_te = belief.build_clarification_question("te")
    assert "ప్రోగ్రామ్" in q_te or "కౌన్సిలింగ్" in q_te

    # 2. Slot filling across turns
    s2 = belief.update_from_utterance("I am interested in the Executive AI program on Friday.")
    assert s2["collected_slots"]["course_interest"] == "Executive AI"
    assert s2["collected_slots"]["interview_date"] == "Friday"
    assert s2["missing_required_slots"] == ["interview_time"]

    s3 = belief.update_from_utterance("Let's do 4:00 PM.")
    assert s3["collected_slots"]["interview_time"] == "4:00 PM"
    assert s3["missing_required_slots"] == []

    # 3. Intent drift to scholarship evaluation
    s4 = belief.update_from_utterance("Wait, can I also apply for a scholarship? I have 5 years experience.")
    assert s4["active_intent"] == "apply_scholarship"
    assert s4["collected_slots"]["course_interest"] == "Executive AI"
    assert s4["collected_slots"]["work_experience"] == "5 Years"
    assert s4["missing_required_slots"] == []

    # 4. Infeasibility: Executive AI with < 2 years experience
    belief_junior = SessionBeliefState(template_domain="education_admissions")
    belief_junior.update_from_utterance("I want to apply for the Executive AI program, I have 1 year of experience.")
    assert belief_junior.tool_infeasible_flag == "insufficient_experience_for_executive_program"


def test_bfsi_fintech_blueprint():
    # 1. Business loan application
    belief = SessionBeliefState(template_domain="bfsi_fintech")
    s1 = belief.update_from_utterance("I need a business loan for working capital.")
    assert s1["active_intent"] == "apply_business_loan"
    assert "loan_amount" in s1["missing_required_slots"]
    assert "annual_turnover" in s1["missing_required_slots"]

    # 2. Slot extraction in Lakhs / Crores
    s2 = belief.update_from_utterance("We need 50 Lakhs and our annual turnover is 2.5 Crores.")
    assert "50.0 Lakhs" in s2["collected_slots"]["loan_amount"]
    assert "250.0 Lakhs" in s2["collected_slots"]["annual_turnover"]
    assert s2["missing_required_slots"] == []

    # 3. Credit score eligibility & Infeasibility gatekeeping
    belief_cibil = SessionBeliefState(template_domain="bfsi_fintech")
    s_cibil = belief_cibil.update_from_utterance("Check my loan eligibility, my CIBIL score is 520.")
    assert s_cibil["active_intent"] == "check_credit_eligibility"
    assert s_cibil["tool_infeasible_flag"] == "credit_score_below_minimum"


def test_b2b_saas_sdr_blueprint():
    belief = SessionBeliefState(template_domain="b2b_saas_sdr")
    s1 = belief.update_from_utterance("I would like to schedule a live architecture demo.")
    assert s1["active_intent"] == "book_saas_demo"
    assert "monthly_volume" in s1["missing_required_slots"]
    assert "demo_date" in s1["missing_required_slots"]
    assert "demo_time" in s1["missing_required_slots"]

    # Provide slots across turns
    s2 = belief.update_from_utterance("We handle around 10k calls each month.")
    assert "10k" in s2["collected_slots"]["monthly_volume"]
    assert "demo_date" in s2["missing_required_slots"]

    s3 = belief.update_from_utterance("Wednesday at 3 PM works best.")
    assert s3["collected_slots"]["demo_date"] == "Wednesday"
    assert s3["collected_slots"]["demo_time"] == "3:00 PM"
    assert s3["missing_required_slots"] == []
