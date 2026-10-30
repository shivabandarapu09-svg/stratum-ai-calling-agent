"""
Trajectory2Task (ACL 2026) — Structured Belief State, Ambiguity Detection & Intent Revision Manager
===================================================================================================
Models the agent's internal belief state b_t = P(u_t, s_t | h^A_t) over non-stationary user intents u_t
and task slots s_t across multi-turn voice conversations in Indian languages (te, hi, en, ta, ml, kn).

Core Capabilities:
1. Ambiguous Customer Requests (When to Ask):
   - Identifies intents triggered by user utterances.
   - Tracks required vs. optional slots per domain intent.
   - Detects missing or vague/underspecified slot values and blocks premature tool execution.
   - Produces concise, natural clarification questions in the caller's active language.
2. Changing Customer Requests (How to Adapt):
   - Detects mid-call slot corrections (e.g. Saturday 11 AM -> Monday 4 PM, 3 BHK -> 4 BHK)
     and intent transitions (e.g. Confirm COD Order -> Cancel Order or Modify Address).
   - Preserves shared entities (order_id, customer_phone, active_appointment_id, verified_caller)
     across intent shifts without losing context.
   - Flags changes so the tool runtime updates existing DB records in-place and confirms updates.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class SlotUpdateEvent:
    turn_index: int
    slot_name: str
    previous_value: Optional[str]
    new_value: str
    is_revision: bool = False


@dataclass
class IntentShiftEvent:
    turn_index: int
    previous_intent: Optional[str]
    new_intent: str
    reason: str


# Domain-aware intent & required-slot specifications
INTENT_REQUIRED_SLOTS: Dict[str, List[str]] = {
    "schedule_site_visit": ["bhk_preference", "visit_date", "visit_time"],
    "book_clinic_appointment": ["department", "visit_date", "visit_time"],
    "reschedule_appointment": ["visit_date", "visit_time"],
    "cancel_appointment": ["cancellation_reason"],
    "confirm_cod_order": ["order_id", "delivery_slot"],
    "cancel_cod_order": ["order_id", "cancellation_reason"],
    "modify_order_address": ["order_id", "new_address", "pincode"],
    "calculate_emi": ["loan_amount"],
    "request_brochure": [],  # Uses caller phone from session context
}

# Multilingual localized slot labels for natural clarification questions
SLOT_LABELS_I18N: Dict[str, Dict[str, str]] = {
    "bhk_preference": {
        "en": "whether you prefer a 3 BHK or 4 BHK configuration",
        "hi": "आप 3 BHK या 4 BHK में से कौन सा विकल्प पसंद करेंगे",
        "te": "మీకు 3 BHK కావాలా లేదా 4 BHK కావాలా",
        "ta": "உங்களுக்கு 3 BHK வேண்டுமா அல்லது 4 BHK வேண்டுமா",
        "ml": "നിങ്ങൾക്ക് 3 BHK ആണോ 4 BHK ആണോ താല്പര്യം",
        "kn": "ನಿಮಗೆ 3 BHK ಬೇಕೇ ಅಥವಾ 4 BHK ಬೇಕೇ",
    },
    "department": {
        "en": "which specialist or department you would like to consult (e.g., General Physician, Cardiology, Dental, or Orthopedics)",
        "hi": "आप किस विभाग या डॉक्टर से परामर्श लेना चाहते हैं (जैसे जनरल फिजिशियन, कार्डियोलॉजी, डेंटल या ऑर्थोपेडिक्स)",
        "te": "మీరు ఏ విభాగం లేదా డాక్టర్‌ని సంప్రదించాలనుకుంటున్నారు (ఉదాహరణకు జనరల్ ఫిజీషియన్, కార్డియాలజీ, డెంటల్)",
        "ta": "எந்த துறை அல்லது மருத்துவரை பார்க்க விரும்புகிறீர்கள் (பொது மருத்துவர், இதய சிகிச்சை, பல் மருத்துவம்)",
        "ml": "ഏത് വിഭാഗത്തിലെ ഡോക്ടറെയാണ് കാണേണ്ടത് (ജനറൽ ഫിസിഷ്യൻ, കാർഡിയോളജി, ഡെന്റൽ)",
        "kn": "ನೀವು ಯಾವ ವಿಭಾಗದ ವೈದ್ಯರನ್ನು ಭೇಟಿ ಮಾಡಲು ಬಯಸುತ್ತೀರಿ (ಜನರಲ್ ಫಿಸಿಷಿಯನ್, ಕಾರ್ಡಿಯಾಲಜಿ, ಡೆಂಟಲ್)",
    },
    "visit_date": {
        "en": "your preferred day or date (for example, Saturday or Monday)",
        "hi": "आपकी पसंदीदा तारीख या दिन (जैसे शनिवार या सोमवार)",
        "te": "మీకు అనుకూలమైన రోజు లేదా తేదీ (ఉదాహరణకు శనివారం లేదా సోమవారం)",
        "ta": "உங்களுக்கு வசதியான நாள் அல்லது தேதி (உதாரணமாக சனிக்கிழமை அல்லது திங்கட்கிழமை)",
        "ml": "നിങ്ങൾക്ക് സൗകര്യപ്രദമായ ദിവസം അല്ലെങ്കിൽ തീയതി (ഉദാഹരണത്തിന് ശനിയാഴ്ച അല്ലെങ്കിൽ തിങ്കളാഴ്ച)",
        "kn": "ನಿಮಗೆ ಅನುಕೂಲಕರವಾದ ದಿನ ಅಥವಾ ದಿನಾಂಕ (ಉದಾಹರಣೆಗೆ ಶನಿವಾರ ಅಥವಾ ಸೋಮವಾರ)",
    },
    "visit_time": {
        "en": "your preferred time slot (for example, 11:00 AM or 4:00 PM)",
        "hi": "आपका पसंदीदा समय (जैसे सुबह 11:00 बजे या शाम 4:00 बजे)",
        "te": "మీకు అనుకూలమైన సమయం (ఉదాహరణకు ఉదయం 11:00 లేదా సాయంత్రం 4:00)",
        "ta": "உங்களுக்கு வசதியான நேரம் (உதாரணமாக காலை 11:00 மணி அல்லது மாலை 4:00 மணி)",
        "ml": "നിങ്ങൾക്ക് സൗകര്യപ്രദമായ സമയം (ഉദാഹരണത്തിന് രാവിലെ 11:00 മണി അല്ലെങ്കിൽ വൈകുന്നേരം 4:00 മണി)",
        "kn": "ನಿಮಗೆ ಅನುಕೂಲಕರವಾದ ಸಮಯ (ಉದಾಹರಣೆಗೆ ಬೆಳಿಗ್ಗೆ 11:00 ಅಥವಾ ಸಂಜೆ 4:00)",
    },
    "order_id": {
        "en": "your 4-digit Order ID (for example, COD-4421)",
        "hi": "आपका ऑर्डर आईडी नंबर (जैसे COD-4421)",
        "te": "మీ ఆర్డర్ ఐడి నంబర్ (ఉదాహరణకు COD-4421)",
        "ta": "உங்கள் ஆர்டர் ஐடி எண் (உதாரணமாக COD-4421)",
        "ml": "നിങ്ങളുടെ ഓർഡർ ഐഡി നമ്പർ (ഉദാഹരണത്തിന് COD-4421)",
        "kn": "ನಿಮ್ಮ ಆರ್ಡರ್ ಐಡಿ ಸಂಖ್ಯೆ (ಉದಾಹರಣೆಗೆ COD-4421)",
    },
    "delivery_slot": {
        "en": "whether morning (10 AM–1 PM) or evening (4 PM–8 PM) delivery works best for you",
        "hi": "क्या सुबह (10 AM–1 PM) या शाम (4 PM–8 PM) की डिलीवरी आपके लिए उपयुक्त रहेगी",
        "te": "మీకు ఉదయం (10 AM–1 PM) లేదా సాయంత్రం (4 PM–8 PM) డెలివరీ అనుకూలంగా ఉంటుందా",
        "ta": "உங்களுக்கு காலை (10 AM–1 PM) அல்லது மாலை (4 PM–8 PM) டெலிவரி வசதியா",
        "ml": "നിങ്ങൾക്ക് രാവിലെ (10 AM–1 PM) ആണോ വൈകുന്നേരം (4 PM–8 PM) ആണോ ഡെലിവറി സൗകര്യം",
        "kn": "ನಿಮಗೆ ಬೆಳಿಗ್ಗೆ (10 AM–1 PM) ಅಥವಾ ಸಂಜೆ (4 PM–8 PM) ಡೆಲಿವರಿ ಅನುಕೂಲಕರವೇ",
    },
    "cancellation_reason": {
        "en": "the reason for cancellation so I can log it accurately",
        "hi": "रद्द करने का कारण ताकि मैं इसे सही ढंग से दर्ज कर सकूँ",
        "te": "రద్దు చేయడానికి కారణం చెప్తారా, నేను సిస్టమ్‌లో నమోదు చేస్తాను",
        "ta": "ரத்து செய்வதற்கான காரணத்தை கூற முடியுமா",
        "ml": "റദ്ദാക്കാനുള്ള കാരണം ഒന്ന് പറയാമോ",
        "kn": "ರದ್ದುಗೊಳಿಸಲು ಕಾರಣವನ್ನು ತಿಳಿಸುವಿರಾ",
    },
    "new_address": {
        "en": "the complete new delivery street address or landmark",
        "hi": "नया पूरा डिलीवरी पता और लैंडमार्क",
        "te": "కొత్త పూర్తి డెలివరీ చిరునామా మరియు ల్యాండ్‌మార్క్",
        "ta": "புதிய முழு டெலிவரி முகவரி மற்றும் அடையாளம்",
        "ml": "പുതിയ പൂർണ്ണമായ ഡെലിവറി വിലാസം",
        "kn": "ಹೊಸ ಸಂಪೂರ್ಣ ಡೆಲಿವರಿ ವಿಳಾಸ",
    },
    "pincode": {
        "en": "the 6-digit area pincode for the new address",
        "hi": "नए पते का 6-अंकों का पिनकोड",
        "te": "కొత్త చిరునామా యొక్క 6-అంకెల పిన్‌కోడ్",
        "ta": "புதிய முகவரியின் 6 இலக்க பின்கோடு",
        "ml": "പുതിയ വിലാസത്തിന്റെ 6 അക്ക പിൻകോഡ്",
        "kn": "ಹೊಸ ವಿಳಾಸದ 6 ಅಂಕಿಯ ಪಿನ್‌ಕೋಡ್",
    },
    "loan_amount": {
        "en": "the approximate loan amount or property budget (e.g., 80 Lakhs or 1.5 Cr) for the EMI calculation",
        "hi": "ईएमआई गणना के लिए अनुमानित लोन राशि या बजट (जैसे 80 लाख या 1.5 करोड़)",
        "te": "EMI లెక్కించడానికి లోన్ మొత్తం లేదా బడ్జెట్ (ఉదాహరణకు 80 లక్షలు లేదా 1.5 కోట్లు)",
        "ta": "இஎம்ஐ கணக்கிட தோராயமான கடன் தொகை அல்லது பட்ஜெட்",
        "ml": "ഇഎംഐ കണക്കാക്കാൻ ഉദ്ദേശിക്കുന്ന ലോൺ തുക അല്ലെങ്കിൽ ബജറ്റ്",
        "kn": "ಇಎಂಐ ಲೆಕ್ಕಾಚಾರಕ್ಕಾಗಿ ಅಂದಾಜು ಸಾಲದ ಮೊತ್ತ ಅಥವಾ ಬಜೆಟ್",
    },
}


class SessionBeliefState:
    """
    Maintains the structured POMDP belief state b_t across a multi-turn call session.
    """

    def __init__(self, template_domain: str = "real_estate", caller_phone: str = "", caller_name: str = ""):
        self.template_domain = template_domain
        self.caller_phone = caller_phone
        self.caller_name = caller_name
        self.turn_index: int = 0
        self.active_intent: Optional[str] = None
        self.intent_history: List[IntentShiftEvent] = []
        self.collected_slots: Dict[str, str] = {}
        self.slot_revisions: List[SlotUpdateEvent] = []
        self.ambiguous_slots_flagged: List[str] = []
        self.verified_caller: bool = False
        self.active_appointment_id: Optional[str] = None
        self.active_order_id: Optional[str] = None
        self.executed_tools_history: List[str] = []
        self.last_revision_Turn: int = -1
        self.last_intent_shift_turn: int = -1
        # Policy/Constraint triggers detected directly from utterance
        self.policy_violation_flag: Optional[str] = None
        self.tool_infeasible_flag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_domain": self.template_domain,
            "active_intent": self.active_intent,
            "collected_slots": dict(self.collected_slots),
            "missing_required_slots": self.get_missing_required_slots(),
            "ambiguous_slots_flagged": list(self.ambiguous_slots_flagged),
            "verified_caller": self.verified_caller,
            "active_appointment_id": self.active_appointment_id,
            "active_order_id": self.active_order_id,
            "slot_revisions_count": len(self.slot_revisions),
            "intent_shifts_count": len(self.intent_history),
            "executed_tools_history": list(self.executed_tools_history),
            "policy_violation_flag": self.policy_violation_flag,
            "tool_infeasible_flag": self.tool_infeasible_flag,
        }

    def get_missing_required_slots(self) -> List[str]:
        if not self.active_intent:
            return []
        required = INTENT_REQUIRED_SLOTS.get(self.active_intent, [])
        missing = []
        for slot in required:
            val = self.collected_slots.get(slot)
            if not val or slot in self.ambiguous_slots_flagged:
                missing.append(slot)
        return missing

    def has_recent_revision(self) -> bool:
        return self.last_revision_Turn == self.turn_index or self.last_intent_shift_turn == self.turn_index

    def _update_slot(self, slot_name: str, new_value: str) -> None:
        prev = self.collected_slots.get(slot_name)
        if slot_name in self.ambiguous_slots_flagged:
            self.ambiguous_slots_flagged.remove(slot_name)

        if prev is not None and prev.lower() != new_value.lower():
            self.slot_revisions.append(
                SlotUpdateEvent(
                    turn_index=self.turn_index,
                    slot_name=slot_name,
                    previous_value=prev,
                    new_value=new_value,
                    is_revision=True,
                )
            )
            self.last_revision_Turn = self.turn_index
        elif prev is None:
            self.slot_revisions.append(
                SlotUpdateEvent(
                    turn_index=self.turn_index,
                    slot_name=slot_name,
                    previous_value=None,
                    new_value=new_value,
                    is_revision=False,
                )
            )
        self.collected_slots[slot_name] = new_value

    def _set_intent(self, new_intent: str, reason: str) -> None:
        if self.active_intent and self.active_intent != new_intent:
            self.intent_history.append(
                IntentShiftEvent(
                    turn_index=self.turn_index,
                    previous_intent=self.active_intent,
                    new_intent=new_intent,
                    reason=reason,
                )
            )
            self.last_intent_shift_turn = self.turn_index
        self.active_intent = new_intent

    def update_from_utterance(self, user_text: str) -> Dict[str, Any]:
        """
        Parses a user utterance to:
        1. Detect policy/tool infeasibility triggers,
        2. Detect new intents or mid-call intent changes,
        3. Extract slot values (and detect vague/ambiguous expressions),
        4. Track slot revisions without losing prior context.
        """
        self.turn_index += 1
        self.policy_violation_flag = None
        self.tool_infeasible_flag = None
        lower = user_text.lower().strip()

        # ------------------------------------------------------------------
        # 1. Extract Caller Verification / OTP / Last-4 Digits if provided
        # ------------------------------------------------------------------
        if re.search(r"\b(otp|code|pin|last 4|last four|verify|verified)\b", lower) or re.search(
            r"\b\d{4}\b", lower
        ):
            # Avoid treating years like 2026 or times like 1030 or order IDs as OTP unless verification context
            if re.search(r"\b(otp|verify|code|last 4|phone ends|ending with|9876|4321|1122|3344)\b", lower):
                self.verified_caller = True
                self._update_slot("caller_verification", "verified")
        if re.search(r"\b(refuse to verify|won't give otp|no otp|don't have otp|without verification|skip verification)\b", lower):
            self.verified_caller = False
            self.collected_slots["caller_verification"] = "refused"

        # ------------------------------------------------------------------
        # 2. Extract Domain Slots (BHK, Department, Date, Time, Order ID, etc.)
        # ------------------------------------------------------------------
        self._extract_slots_from_text(user_text, lower)

        # ------------------------------------------------------------------
        # 3. Detect Policy-Infeasible & Tool-Infeasible Requests (Section 3.2.2)
        # ------------------------------------------------------------------
        self._detect_infeasibility_flags(lower)

        # ------------------------------------------------------------------
        # 4. Detect Active Intent or Intent Drift / Goal Switch
        # ------------------------------------------------------------------
        self._detect_intent_and_drift(lower)

        return self.to_dict()

    def _extract_slots_from_text(self, raw_text: str, lower: str) -> None:
        # A. BHK Preference (Real Estate)
        bhk_match = re.search(r"\b([1-5])\s*[-]?\s*bhk\b", lower)
        if not bhk_match:
            # Check Indian script / number words for BHK
            if "3 bhk" in lower or "three bhk" in lower or "3bhk" in lower or "3 ബിഎച്ച്കെ" in lower or "3 பிஹெச்கே" in lower or "3 బిహెచ్‌కె" in lower or "3 ಬಿಎಚ್‌ಕೆ" in lower:
                self._update_slot("bhk_preference", "3 BHK")
            elif "4 bhk" in lower or "four bhk" in lower or "4bhk" in lower or "4 ബിഎച്ച്കെ" in lower or "4 பிஹெச்கே" in lower or "4 బిహెచ్‌కె" in lower or "4 ಬಿಎಚ್‌ಕೆ" in lower:
                self._update_slot("bhk_preference", "4 BHK")
            elif "1 bhk" in lower or "one bhk" in lower or "1bhk" in lower:
                self._update_slot("bhk_preference", "1 BHK")
            elif "2 bhk" in lower or "two bhk" in lower or "2bhk" in lower:
                self._update_slot("bhk_preference", "2 BHK")
            elif "penthouse" in lower:
                self._update_slot("bhk_preference", "4 BHK Penthouse")
        else:
            bhk_num = bhk_match.group(1)
            self._update_slot("bhk_preference", f"{bhk_num} BHK")

        # B. Clinic Department / Doctor Specialty
        dept_map = {
            "Cardiology": ["cardio", "heart", "कार्डियोलॉजी", "कार्डियो", "हृदय", "కార్డియాలజీ", "இதய", "കാർഡിയോളജി", "ಹೃದಯ", "dr. sharma", "dr sharma"],
            "Dental": ["dental", "dentist", "tooth", "teeth", "डेंटल", "दांत", "డెంటల్", "பல்", "ഡെന്റൽ", "ದಂತ"],
            "Orthopedics": ["ortho", "bone", "knee", "joint", "ऑर्थोपेडिक्स", "ऑर्थो", "हड्डी", "ఆర్థో", "எலும்பு", "ഓർത്തോ", "ಮೂಳೆ"],
            "General Physician": ["general physician", "general doctor", "fever", "checkup", "consultation", "जनरल फिजिशियन", "జనరల్ ఫిజీషియన్", "பொது மருத்துவர்", "ജനറൽ ഫിസിഷ്യൻ", "ಜನರಲ್ ಫಿಸಿಷಿಯನ್", "dr. nair", "dr nair"],
            "Pediatrics": ["pediatric", "child specialist", "kids doctor", "पीडियाट्रिक्स", "बच्चों के डॉक्टर"],
        }
        for dept_canonical, keywords in dept_map.items():
            if any(kw in lower for kw in keywords):
                self._update_slot("department", dept_canonical)
                break

        # C. Visit Date / Day Extraction (including Indian language day names)
        day_map = {
            "Monday": ["monday", "somwar", "सोमवार", "సోమవారం", "திங்கட்கிழமை", "திங்கள்", "തിങ്കളാഴ്ച", "തിങ്കൾ", "ಸೋಮವಾರ"],
            "Tuesday": ["tuesday", "mangalwar", "मंगलवार", "మంగళవారం", "செவ்வாய்க்கிழமை", "செவ்வாய்", "ചൊവ്വാഴ്ച", "ಮಂಗಳವಾರ"],
            "Wednesday": ["wednesday", "budhwar", "बुधवार", "బుధవారం", "புதன்கிழமை", "புதன்", "ബുധനാഴ്ച", "ಬುಧವಾರ"],
            "Thursday": ["thursday", "guruwar", "गुरुवार", "గురువారం", "வியாழக்கிழமை", "வியാழன்", "വ്യാഴാഴ്ച", "ಗುರುವಾರ"],
            "Friday": ["friday", "shukrawar", "शुक्रवार", "శుక్రవారం", "வெள்ளிக்கிழமை", "வெள்ளி", "വെള്ളിയാഴ്ച", "ಶುಕ್ರವಾರ"],
            "Saturday": ["saturday", "shaniwar", "शनिवार", "శనివారం", "சனிக்கிழமை", "சனி", "ശനിയാഴ്ച", "ശനി", "ಶನಿವಾರ"],
            "Sunday": ["sunday", "raviwar", "itwar", "रविवार", "ఆదివారం", "ஞாயிற்றுக்கிழமை", "ஞாயிறு", "ഞായറാഴ്ച", "ഞായർ", "ಭಾನುವಾರ"],
            "Tomorrow": ["tomorrow", "kal", "कल", "రేపు", "repu", "நாளை", "nalai", "നാളെ", "naale", "ನಾಳೆ", "naale"],
        }
        found_specific_day = False
        for canonical_day, variants in day_map.items():
            for v in variants:
                # Word boundary for ascii words, substring for Indic scripts
                if v.isascii():
                    if re.search(rf"\b{re.escape(v)}\b", lower):
                        self._update_slot("visit_date", canonical_day)
                        found_specific_day = True
                        break
                else:
                    if v in lower:
                        self._update_slot("visit_date", canonical_day)
                        found_specific_day = True
                        break
            if found_specific_day:
                break

        # Detect vague/ambiguous date expressions if no specific day was given
        if not found_specific_day and "visit_date" not in self.collected_slots:
            if re.search(r"\b(sometime|next week|whenever|any day|some day|later this month|soon)\b", lower):
                self.ambiguous_slots_flagged.append("visit_date")

        # D. Visit Time Extraction
        time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b", lower)
        if time_match:
            hr = int(time_match.group(1))
            mn = time_match.group(2) or "00"
            meridiem = "AM" if "a" in time_match.group(3) else "PM"
            self._update_slot("visit_time", f"{hr}:{mn} {meridiem}")
        else:
            # Check Hindi/Telugu/Tamil/Malayalam/Kannada time markers like "11 baje", "11 గంటలకు", "11 மணிக்கு", "11 മണിക്ക്", "11 ಗಂಟೆಗೆ"
            indic_time = re.search(
                r"\b(\d{1,2})(?::(\d{2}))?\s*(?:baje|बजे|ಗಂಟೆಗೆ|ಗಂಟೆ|గంటలకు|గంటలకి|மணிக்கு|மணி|മണിക്ക്|മണി|o'clock)\b",
                lower,
            )
            if indic_time:
                hr = int(indic_time.group(1))
                mn = indic_time.group(2) or "00"
                meridiem = "AM" if (hr in [8, 9, 10, 11] or "morning" in lower or "सुबह" in lower or "ఉదయం" in lower or "காலை" in lower or "രാവിലെ" in lower or "ಬೆಳಿಗ್ಗೆ" in lower) else "PM"
                if hr == 12:
                    meridiem = "PM"
                self._update_slot("visit_time", f"{hr}:{mn} {meridiem}")
            elif re.search(r"\b(sometime in the morning|any time|whenever|not sure what time)\b", lower) and "visit_time" not in self.collected_slots:
                self.ambiguous_slots_flagged.append("visit_time")

        # E. Order ID Extraction (E-Commerce COD)
        order_match = re.search(r"\b(?:cod[-#\s]*)?(\d{4,6})\b", lower)
        if order_match and ("order" in lower or "cod" in lower or self.template_domain == "ecommerce_cod" or self.active_intent in ["confirm_cod_order", "cancel_cod_order", "modify_order_address"]):
            oid_digits = order_match.group(1)
            # Do not confuse 6-digit pincode with order_id if pincode is being extracted
            if len(oid_digits) == 4:
                canonical_oid = f"COD-{oid_digits}"
                self._update_slot("order_id", canonical_oid)
                self.active_order_id = canonical_oid

        # F. Delivery Slot (E-Commerce COD)
        if re.search(r"\b(morning|10\s*am|before noon|सुबह|ఉదయం|காலை|രാവിലെ|ಬೆಳಿಗ್ಗೆ)\b", lower) and (
            self.template_domain == "ecommerce_cod" or self.active_intent == "confirm_cod_order"
        ):
            self._update_slot("delivery_slot", "Morning (10:00 AM - 1:00 PM)")
        elif re.search(r"\b(evening|afternoon|4\s*pm|after 4|शाम|సాయంత్రం|மாலை|വൈകുന്നേരം|ಸಂಜೆ)\b", lower) and (
            self.template_domain == "ecommerce_cod" or self.active_intent == "confirm_cod_order"
        ):
            self._update_slot("delivery_slot", "Evening (4:00 PM - 8:00 PM)")

        # G. Pincode & New Address (Order Address Modification)
        pin_match = re.search(r"\b([1-9]\d{5})\b", lower)
        if pin_match:
            self._update_slot("pincode", pin_match.group(1))

        addr_match = re.search(
            r"(?:address to|address is|deliver to|ship to|flat|house no|sector|plot|road|street|nagar|layout|colony|building)\s*[:,-]?\s*([a-zA-Z0-9\s,#/-]{6,60})",
            raw_text,
            re.IGNORECASE,
        )
        if addr_match and ("address" in lower or "deliver" in lower or "ship" in lower or "flat" in lower or "sector" in lower or "layout" in lower or "nagar" in lower):
            cleaned_addr = addr_match.group(0).strip().rstrip(".")
            self._update_slot("new_address", cleaned_addr)

        # H. Cancellation Reason
        if any(
            kw in lower
            for kw in [
                "ordered by mistake",
                "found cheaper",
                "delayed",
                "don't need",
                "do not need",
                "changed my mind",
                "out of station",
                "travelling",
                "wrong item",
                "not available",
                "personal emergency",
                "mistake",
            ]
        ):
            for kw in [
                "ordered by mistake",
                "found cheaper",
                "delayed",
                "don't need",
                "do not need",
                "changed my mind",
                "out of station",
                "travelling",
                "wrong item",
                "not available",
                "personal emergency",
                "mistake",
            ]:
                if kw in lower:
                    self._update_slot("cancellation_reason", kw)
                    break

        # I. Loan Amount / Budget for EMI calculation
        amt_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(cr|crore|crores|lakh|lakhs|lac|lacs)\b", lower)
        if amt_match:
            val = float(amt_match.group(1))
            unit = amt_match.group(2)
            lakhs = val * 100.0 if unit.startswith("cr") else val
            self._update_slot("loan_amount", f"{lakhs:.1f} Lakhs")

    def _detect_infeasibility_flags(self, lower: str) -> None:
        # 1. Policy-Infeasible Checks
        # a) Medical prescription / antibiotic / dosage request without doctor consultation
        if re.search(
            r"\b(prescribe|prescription|antibiotic|dosage|medicine for chest pain|strong painkiller|send prescription|write a prescription)\b",
            lower,
        ):
            self.policy_violation_flag = "medical_prescription_prohibited"

        # b) Excessive / Unauthorized Discount (>10%, e.g., 25%, 30%, 40%, 50% discount)
        disc_match = re.search(r"\b([2-9]\d)\s*%\s*(?:discount|off|reduction)\b", lower)
        if disc_match or "30 percent discount" in lower or "25 percent discount" in lower or "half price" in lower:
            self.policy_violation_flag = "excessive_discount_policy_violation"

        # c) Unverified account modification / bypassing verification
        if self.collected_slots.get("caller_verification") == "refused" and any(
            w in lower for w in ["cancel", "address", "change", "modify", "reroute"]
        ):
            self.policy_violation_flag = "unverified_caller_modification_prohibited"

        # 2. Tool-Infeasible Checks
        # a) Unavailable 1 BHK or 2 BHK inventory at Prestige Sky Meadows (only 3 BHK & 4 BHK exist)
        if self.template_domain == "real_estate" and self.collected_slots.get("bhk_preference") in ["1 BHK", "2 BHK"]:
            self.tool_infeasible_flag = "unsupported_bhk_inventory"

        # b) Clinic appointment on Sunday (Clinic operates Mon-Sat 08:00 AM - 08:30 PM)
        if self.template_domain == "clinic_healthcare" and self.collected_slots.get("visit_date") == "Sunday":
            self.tool_infeasible_flag = "clinic_closed_on_sunday"

        # c) Clinic appointment outside operating hours (e.g., 11:00 PM / 10:00 PM / 6:00 AM)
        if self.template_domain == "clinic_healthcare" and self.collected_slots.get("visit_time") in [
            "10:00 PM",
            "11:00 PM",
            "11:30 PM",
            "6:00 AM",
            "5:00 AM",
        ]:
            self.tool_infeasible_flag = "clinic_outside_operating_hours"

        # d) Cancelling or modifying an already shipped/delivered order (e.g. COD-9999 or COD-8888)
        if self.collected_slots.get("order_id") in ["COD-9999", "COD-8888"] and any(
            w in lower for w in ["cancel", "address", "modify", "change"]
        ):
            self.tool_infeasible_flag = "order_already_shipped_or_delivered"

        # e) Unserviceable pincode (e.g. 999999 or 000000)
        if self.collected_slots.get("pincode") in ["999999", "888888"]:
            self.tool_infeasible_flag = "unserviceable_delivery_pincode"

    def _detect_intent_and_drift(self, lower: str) -> None:
        # Check explicit goal switches or primary intents
        # 1. Order Cancellation vs Confirmation vs Address Change
        if any(w in lower for w in ["cancel my order", "cancel the order", "cancel order", "cancel cod", "don't want the order", "ऑर्डर कैंसिल", "ఆర్డర్ క్యాన్సిల్", "ஆர்டர் கேன்சல்", "ഓർഡർ ക്യാൻസൽ", "ಆರ್ಡರ್ ಕ್ಯಾನ್ಸಲ್"]):
            self._set_intent("cancel_cod_order", "caller_requested_order_cancellation")
            return

        if any(w in lower for w in ["change address", "change delivery address", "update address", "new address", "modify address", "different address", "पता बदलना", "అడ్రస్ మార్చాలి", "முகவரி மாற்ற", "വിലാസം മാറ്റണം", "ವಿಳಾಸ ಬದಲಿಸಿ"]):
            self._set_intent("modify_order_address", "caller_requested_address_modification")
            return

        if self.template_domain == "ecommerce_cod" and any(
            w in lower for w in ["confirm my order", "confirm order", "confirm the cod", "yes deliver", "deliver my order", "confirm delivery"]
        ):
            self._set_intent("confirm_cod_order", "caller_requested_order_confirmation")
            return

        # 2. Appointment / Site Visit Cancellation or Rescheduling
        if any(w in lower for w in ["cancel appointment", "cancel my visit", "cancel the visit", "cancel booking"]):
            self._set_intent("cancel_appointment", "caller_requested_appointment_cancellation")
            return

        if any(
            w in lower
            for w in [
                "reschedule",
                "change the date",
                "change my appointment",
                "change the time",
                "move it to",
                "shift it to",
                "instead of",
                "wait, make it",
                "actually make it",
                "change to",
            ]
        ) and self.active_appointment_id:
            # Preserve existing intent or transition to reschedule while keeping slots
            if self.template_domain == "clinic_healthcare":
                self._set_intent("book_clinic_appointment", "caller_revised_appointment_slot")
            else:
                self._set_intent("schedule_site_visit", "caller_revised_site_visit_slot")
            return

        # 3. Booking Site Visit or Clinic Appointment
        booking_keywords = [
            "book",
            "schedule",
            "appointment",
            "site visit",
            "visit",
            "consult",
            "slot",
            "बुक",
            "अपॉइंटमेंट",
            "विजिट",
            "బుక్",
            "అపాయింట్‌మెంట్",
            "విజిట్",
            "புக்",
            "அப்பாயின்ட்மென்ட்",
            "ബുക്ക്",
            "അപ്പോയിന്റ്മെന്റ്",
            "ಬುಕ್",
            "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್",
        ]
        if any(kw in lower for kw in booking_keywords):
            if self.template_domain == "clinic_healthcare":
                self._set_intent("book_clinic_appointment", "caller_requested_clinic_appointment")
            else:
                self._set_intent("schedule_site_visit", "caller_requested_site_visit")
            return

        # 4. EMI Calculation
        if any(w in lower for w in ["calculate emi", "emi calculation", "monthly emi", "how much emi", "किस्त", "ఈఎంఐ", "இஎம்ஐ", "ഇഎംഐ", "ಇಎಂಐ"]):
            if not self.active_intent:
                self._set_intent("calculate_emi", "caller_requested_emi_calculation")
            return

        # 5. Brochure / WhatsApp Collateral
        if any(w in lower for w in ["whatsapp", "brochure", "floor plan", "pdf", "details on phone", "व्हाट्सएप", "బ్రోచర్", "வாட்ஸ்அப்", "വാട്ട്സ്ആപ്പ്", "ವಾಟ್ಸಾಪ್"]):
            if not self.active_intent:
                self._set_intent("request_brochure", "caller_requested_whatsapp_collateral")
            return

    def build_clarification_question(self, language: str = "en") -> str:
        """
        Generates a concise, natural clarification question in the caller's active language
        for the missing or ambiguous slots of the active intent.
        Never guesses missing customer parameters.
        """
        lang = language if language in ["en", "hi", "te", "ta", "ml", "kn"] else "en"
        missing = self.get_missing_required_slots()
        if not missing:
            return ""

        # Ask for at most 2 missing slots at a time to keep voice turns natural and concise
        target_slots = missing[:2]
        slot_phrases = [
            SLOT_LABELS_I18N.get(s, {}).get(lang, SLOT_LABELS_I18N.get(s, {}).get("en", s))
            for s in target_slots
        ]

        # Include acknowledgment of any already-collected slots or recent intent change
        ack_prefix = self._build_context_acknowledgment(lang)

        if lang == "hi":
            joined = " और ".join(slot_phrases)
            return f"{ack_prefix}इसे आगे बढ़ाने के लिए, कृपया मुझे {joined} बताएं ताकि मैं सही जानकारी के साथ आपकी मदद कर सकूँ।"
        elif lang == "te":
            joined = " మరియు ".join(slot_phrases)
            return f"{ack_prefix}దీనిని పూర్తి చేయడానికి, దయచేసి {joined} తెలియజేస్తారా?"
        elif lang == "ta":
            joined = " மற்றும் ".join(slot_phrases)
            return f"{ack_prefix}இதை உறுதிப்படுத்த, தயவுசெய்து {joined} கூற முடியுமா?"
        elif lang == "ml":
            joined = " കൂടാതെ ".join(slot_phrases)
            return f"{ack_prefix}ഇത് പൂർത്തിയാക്കാൻ, ദయവായി {joined} ഒന്ന് വ്യക്തമാക്കാമോ?"
        elif lang == "kn":
            joined = " ಮತ್ತು ".join(slot_phrases)
            return f"{ack_prefix}ಇದನ್ನು ಖಚಿತಪಡಿಸಲು, ದಯವಿಟ್ಟು {joined} ತಿಳಿಸುತ್ತೀರಾ?"
        else:
            joined = " and ".join(slot_phrases)
            return f"{ack_prefix}To complete this accurately without guessing, could you please share {joined}?"

    def _build_context_acknowledgment(self, lang: str) -> str:
        """Acknowledges recently provided slots or intent switches before asking for remaining slots."""
        if self.last_intent_shift_turn == self.turn_index and self.intent_history:
            latest_shift = self.intent_history[-1]
            if lang == "hi":
                return "बिल्कुल, मैंने आपका अनुरोध अपडेट कर लिया है। "
            elif lang == "te":
                return "తప్పకుండా, మీ అభ్యర్థనను మార్చాను. "
            elif lang == "ta":
                return "நிச்சயமாக, உங்கள் கோரிக்கையை மாற்றிக்கொண்டேன். "
            elif lang == "ml":
                return "തീർച്ചയായും, നിങ്ങളുടെ ആവശ്യം ഞാൻ അപ്ഡേറ്റ് ചെയ്തിട്ടുണ്ട്. "
            elif lang == "kn":
                return "ಖಂಡಿತ, ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು ನಾನು ಬದಲಾಯಿಸಿದ್ದೇನೆ. "
            else:
                return f"Understood, I have switched your request from {latest_shift.previous_intent} to {latest_shift.new_intent}. "

        # Acknowledge collected slots if any exist
        known_parts = []
        for k in ["bhk_preference", "department", "visit_date", "visit_time", "order_id"]:
            if k in self.collected_slots and k not in self.ambiguous_slots_flagged:
                known_parts.append(self.collected_slots[k])
        if known_parts:
            summary_str = ", ".join(known_parts)
            if lang == "hi":
                return f"जी, मैंने {summary_str} नोट कर लिया है। "
            elif lang == "te":
                return f"సరే అండి, {summary_str} నోట్ చేసుకున్నాను. "
            elif lang == "ta":
                return f"சரி, {summary_str} குறித்துக்கொண்டேன். "
            elif lang == "ml":
                return f"ശരി, {summary_str} ഞാൻ കുറിച്ചെടുത്തിട്ടുണ്ട്. "
            elif lang == "kn":
                return f"ಸರಿ, {summary_str} ನಾನು ಗುರುತಿಸಿಕೊಂಡಿದ್ದೇನೆ. "
            else:
                return f"Got it, I have noted {summary_str}. "
        return ""
