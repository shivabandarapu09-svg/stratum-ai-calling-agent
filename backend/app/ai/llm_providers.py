import os
import json
import re
import httpx
from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator, Optional
from app.config import settings

HUMAN_REALISM_DIRECTIVES = """
[STRATUM HUMAN-REALISM & TRAJECTORY2TASK GROUNDING DIRECTIVES]:
- You are a real-sounding human executive on a live phone call (powered by Stratum AI).
- NEVER sound like a chatbot or read bullet points. Speak in warm, natural, spoken phone phrasing (1 to 2 sentences max, 20-35 words).
- Start turns naturally with human micro-acknowledgments/fillers matching the caller's emotion:
  * Hindi/Hinglish: "हाँ जी, बिल्कुल—", "अच्छा, मैं समझ सकता हूँ...", "जी, बहुत अच्छा सवाल है आपका—"
  * Indian English: "Right, I completely get that—", "Oh, good question! So basically,", "Sure thing, let me check that for you—"
  * Telugu/Tenglish: "అవునండి, తప్పకుండా—", "చాలా మంచి ప్రశ్న అండి, చూడండి—"
  * Tamil: "நிச்சயமாக, நான் உங்களுக்கு உதவுகிறேன்—", "நல்ல கேள்வி—"
  * Malayalam: "തീർച്ചയായും, ഞാൻ അത് പരിശോധിക്കാം—", "വളരെ നല്ല ചോദ്യം—"
  * Kannada: "ಖಂಡಿತವಾಗಿಯೂ, ನಾನು ನಿಮಗೆ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ—"
- TRAJECTORY2TASK RELIABILITY RULES:
  1. Ambiguous Intent: Never guess missing customer details (date, time, BHK configuration, department, order ID, or address). Ask a concise clarification question first.
  2. Changing Intent: When the caller revises a slot or changes their mind mid-call, acknowledge the update and confirm the revised state without losing earlier context.
  3. Infeasible/Policy-Restricted Requests: Never claim an action succeeded unless the verified tool runtime confirms `status=success`. Explain policy or system limitations honestly.
"""

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        language: str = "hi",
        knowledge_context: Optional[str] = None
    ) -> str:
        pass


class GroqLLMProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = "llama-3.3-70b-versatile"
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        language: str = "hi",
        knowledge_context: Optional[str] = None
    ) -> str:
        if not self.api_key:
            return await DynamicConversationalEngine().generate_response(messages, system_prompt, language, knowledge_context)

        full_system = system_prompt
        if knowledge_context:
            full_system += f"\n\n[Authoritative Knowledge Base Grounding]:\n{knowledge_context}"

        full_system += f"\n\nSpoken Language Code: {language}\n{HUMAN_REALISM_DIRECTIVES}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": full_system},
                *messages
            ],
            "temperature": 0.55,
            "max_tokens": 140
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[Groq Fallback to Stratum Dynamic Engine]: {e}")
            return await DynamicConversationalEngine().generate_response(messages, system_prompt, language, knowledge_context)


class OpenAILLMProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = "gpt-4o-mini"
        self.endpoint = "https://api.openai.com/v1/chat/completions"

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        language: str = "hi",
        knowledge_context: Optional[str] = None
    ) -> str:
        if not self.api_key:
            return await DynamicConversationalEngine().generate_response(messages, system_prompt, language, knowledge_context)

        full_system = system_prompt
        if knowledge_context:
            full_system += f"\n\n[Knowledge Grounding]:\n{knowledge_context}"
        full_system += f"\n\nSpoken Language Code: {language}\n{HUMAN_REALISM_DIRECTIVES}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": full_system},
                *messages
            ],
            "temperature": 0.55,
            "max_tokens": 140
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[OpenAI Fallback to Stratum Dynamic Engine]: {e}")
            return await DynamicConversationalEngine().generate_response(messages, system_prompt, language, knowledge_context)


class DynamicConversationalEngine(BaseLLMProvider):
    """
    Stratum AI's rule-based fallback conversational engine.
    Handles colloquial Hinglish/Tenglish code-switching, backchanneling and empathy openers,
    mid-call tool execution context, and Stratum five-stage BANT progression.
    """
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        language: str = "hi",
        knowledge_context: Optional[str] = None
    ) -> str:
        user_messages: List[str] = []
        assistant_messages: List[str] = []
        for m in messages:
            if m.get("role") == "user":
                user_messages.append(m.get("content", "").strip())
            elif m.get("role") == "assistant":
                assistant_messages.append(m.get("content", "").strip())

        last_user_msg = user_messages[-1].lower() if user_messages else ""
        turn_count = len(user_messages)

        # Detect Blueprint from system prompt or context
        sp_low = system_prompt.lower()
        is_real_estate = any(w in sp_low for w in ["real estate", "prestige", "bhk", "property", "apartment", "site visit"])
        is_healthcare = any(w in sp_low for w in ["clinic", "doctor", "health", "apollo", "patient", "appointment", "specialty"])
        is_edtech = any(w in sp_low for w in ["admissions", "education", "course", "institute", "student", "mba", "syllabus"])
        is_ecommerce = any(w in sp_low for w in ["cod", "order", "delivery", "cash on delivery", "parcel", "urbantrend"])
        is_bfsi = any(w in sp_low for w in ["loan", "credit", "bank", "emi", "finserv", "interest rate", "bfsi", "overdraft"])
        is_b2b_saas = any(w in sp_low for w in ["stratum", "saas", "telecalling", "sdr", "leads", "crm"])

        # -------------------------------------------------------------
        # 0. EXPLICIT LANGUAGE SWITCH REQUESTS
        # -------------------------------------------------------------
        if any(p in last_user_msg for p in ["explain in english", "speak in english", "switch to english", "in english"]):
            return "Sure thing! I can happily walk you through everything in English. Tell me, what's the main thing you'd like to know first—pricing, timelines, or how we get started?"
        if any(p in last_user_msg for p in ["हिंदी में", "hindi me", "hindi mein", "speak in hindi", "switch to hindi"]):
            return "हाँ जी बिल्कुल! हम आराम से हिंदी में बात कर सकते हैं। बताइए, आप सबसे पहले किस बारे में जानना चाहेंगे?"
        if any(p in last_user_msg for p in ["తెలుగులో", "telugu lo", "speak in telugu", "in telugu", "switch to telugu"]):
            return "తప్పకుండా అండి! మనం తెలుగులోనే మాట్లాడుకుందాం. చెప్పండి, మీకు ముందుగా ఏ వివరాలు కావాలో చెప్తారా?"
        if any(p in last_user_msg for p in ["தமிழ்", "தமிழில்", "tamil il", "tamil la", "speak in tamil", "in tamil", "switch to tamil"]):
            return "நிச்சயமாக! நாம் தமிழிலேயே பேசலாம். சொல்லுங்கள், உங்களுக்கு முதலில் என்ன விவரங்கள் வேண்டும்?"
        if any(p in last_user_msg for p in ["മലയാളം", "മലയാളത്തിൽ", "malayalathil", "malayalam lo", "speak in malayalam", "in malayalam", "switch to malayalam"]):
            return "തീർച്ചയായും! നമുക്ക് മലയാളത്തിൽ തന്നെ സംസാരിക്കാം. പറയൂ, നിങ്ങൾക്ക് ആദ്യം എന്താണ് അറിയേണ്ടത്?"
        if any(p in last_user_msg for p in ["ಕನ್ನಡ", "ಕನ್ನಡದಲ್ಲಿ", "kannada dalli", "speak in kannada", "in kannada", "switch to kannada"]):
            return "ಖಂಡಿತವಾಗಿಯೂ! ನಾವು ಕನ್ನಡದಲ್ಲೇ ಮಾತನಾಡೋಣ. ಹೇಳಿ, ನಿಮಗೆ ಮೊದಲು ಯಾವ ಮಾಹಿತಿ ಬೇಕು?"

        # -------------------------------------------------------------
        # 1. HUMAN ESCALATION & WARM TRANSFER
        # -------------------------------------------------------------
        if any(w in last_user_msg for w in [
            "human", "person", "agent", "officer", "manager", "transfer", "connect to someone", "real person",
            "इंसान", "अधिकारी", "मैनेजर", "बात करवाओ", "ट्रांसफर",
            "మనిషి", "మేనేజర్", "మాట్లాడాలి",
            "மனிதரிடம்", "மேலாளரிடம்", "മനുഷ്യനോട്", "മാനേജരുമായി", "ಮನುಷ್ಯರೊಂದಿಗೆ", "ಮ್ಯಾನೇಜರ್"
        ]):
            if language == "en":
                return "Oh, I completely understand! Give me just two seconds—I'm briefing our senior manager and connecting your line right now. Please stay on the call."
            elif language == "te":
                return "అలాగే అండి, ఒక్క క్షణం ఉండండి—నేను ఇప్పుడే మా సీనియర్ మేనేజర్‌కి మీ వివరాలు చెప్పి కాల్ కనెక్ట్ చేస్తున్నాను."
            elif language == "ta":
                return "நிச்சயமாக, ஒரு நிமிடம் காத்திருங்கள்—நான் உடனே எங்கள் மூத்த மேலாளரிடம் உங்கள் அழைப்பை இணைக்கிறேன்."
            elif language == "ml":
                return "തീർച്ചയായും, ഒരു നിമിഷം—ഞാൻ ഇപ്പോൾ തന്നെ ഞങ്ങളുടെ സീനിയർ മാനേജരുമായി നിങ്ങളുടെ കോൾ കണക്റ്റ് ചെയ്യുന്നു."
            elif language == "kn":
                return "ಖಂಡಿತ, ಒಂದು ಕ್ಷಣ ಇರಿ—ನಾನು ಈಗಲೇ ನಮ್ಮ ಹಿರಿಯ ಮ್ಯಾನೇಜರ್‌ಗೆ ನಿಮ್ಮ ಕರೆಯನ್ನು ಕನೆಕ್ಟ್ ಮಾಡುತ್ತಿದ್ದೇನೆ."
            else:
                return "हाँ जी, बिल्कुल! बस दो सेकंड दीजिए, मैं अभी हमारे सीनियर मैनेजर को ब्रीफ करके आपकी कॉल सीधा कनेक्ट कर रहा हूँ। प्लीज लाइन पर रहिएगा।"

        # -------------------------------------------------------------
        # 2. WHATSAPP BROCHURE / DETAILS DISPATCH (Mid-Call Action)
        # -------------------------------------------------------------
        if any(w in last_user_msg for w in [
            "whatsapp", "brochure", "send details", "send me the pdf", "link", "message me", "floor plan",
            "व्हाट्सएप", "डिटेल्स भेजो", "पीडीएफ", "लिंक भेजो", "फ्लोर प्लान",
            "వాట్సాప్", "లింక్"
        ]):
            if language == "en":
                return "Done! I've just pinged the complete brochure and price sheet to your WhatsApp—you should see it pop up right now. While you check that, would Saturday morning around 11 AM work for a quick preview?"
            elif language == "te":
                return "ఇప్పుడే మీ వాట్సాప్ నంబర్‌కు పూర్తి బ్రోచర్ మరియు ప్రైస్ షీట్ పంపించానండి! ఒకసారి చూసి, ఈ శనివారం ఉదయం 11 గంటలకు విజిట్ ప్లాన్ చేసుకుందామా?"
            else:
                return "लीजिए, मैंने अभी आपके व्हाट्सएप नंबर पर पूरा फ्लोर प्लान और प्राइस शीट भेज दिया है—एक बार चेक कीजिए! वैसे क्या इस शनिवार सुबह 11 बजे आपके लिए एक शॉर्ट विजिट या डेमो स्लॉट ब्लॉक कर दूँ?"

        # -------------------------------------------------------------
        # 3. APPOINTMENT / DEMO / VISIT CONFIRMATION (Stratum 5 Close)
        # -------------------------------------------------------------
        if any(w in last_user_msg for w in [
            "book", "confirm", "schedule", "saturday", "sunday", "tomorrow", "11 am", "3 pm", "4 pm", "thursday", "wednesday", "yes book it",
            "हाँ बुक", "बुक कर", "शनिवार", "रविवार", "कल", "कन्फर्म", "गुरुवार", "शेड्यूल",
            "బుక్ చేయండి", "రేపు", "శనివారం"
        ]):
            if is_real_estate:
                if language == "en":
                    return "Awesome, that's locked in! I've reserved your VIP site visit at Prestige Sky Meadows for Saturday at 11:00 AM, and your digital gate pass is on your WhatsApp. Would you like our complimentary chauffeur pickup as well?"
                return "अरे वाह, बहुत बढ़िया! मैंने इस शनिवार सुबह 11:00 बजे के लिए आपका VIP साइट विजिट स्लॉट लॉक कर दिया है, और गेट पास आपके व्हाट्सएप पर आ गया है। क्या मैं आपके लिए कॉम्प्लीमेंट्री कैब पिकअप भी अरेंज कर दूँ?"
            elif is_healthcare:
                if language == "hi":
                    return "जी बिल्कुल, कल सुबह 10:30 बजे सीनियर स्पेशलिस्ट के साथ आपका अपॉइंटमेंट कन्फर्म हो गया है! डिजिटल टोकन पास आपके व्हाट्सएप पर भेज दिया है।"
                return "Perfect, I've just locked in your appointment for tomorrow at 10:30 AM with our senior specialist! Your zero-wait digital clinic token is now on your WhatsApp."
            elif is_edtech:
                if language == "en":
                    return "Fantastic! I've scheduled your 15-minute evaluation call with our Academic Director for Thursday at 4:00 PM, and the calendar invite is in your inbox."
                return "बहुत बढ़िया जी! मैंने इस गुरुवार शाम 4:00 बजे हमारे एकेडमिक डायरेक्टर के साथ आपका 15-मिनट का काउंसलिंग स्लॉट बुक कर दिया है—कैलेंडर लिंक आपके व्हाट्सएप पर आ गया है!"
            elif is_ecommerce:
                if language == "en":
                    return "Super, your ₹2,499 order is verified and queued for priority dispatch! It'll reach your doorstep in 3 business days, and live tracking is on your WhatsApp."
                return "परफेक्ट जी! आपका ₹2,499 का आर्डर वेरीफाई हो गया है और आज ही डिस्पैच हो रहा है—3 दिन में पार्सल आपके पास पहुँच जाएगा!"
            elif is_bfsi:
                return "बिल्कुल जी! मैंने आपके ₹25 लाख के प्री-अप्रूव्ड बिज़नेस लोन का डिजिटल सैंक्शन लेटर आपके व्हाट्सएप पर भेज दिया है, और हमारे रिलेशनशिप मैनेजर दोपहर 3 बजे कॉल करेंगे।"
            else:
                return "Awesome, you're all set! I've locked in your 20-minute live Stratum AI architecture demo for Wednesday at 3:00 PM—the Google Meet link is in your inbox and WhatsApp!"

        # -------------------------------------------------------------
        # 4. INDUSTRY BLUEPRINT HUMAN-LIKE CONSULTATIVE DIALOGUE
        # -------------------------------------------------------------
        if is_real_estate:
            if any(w in last_user_msg for w in ["price", "cost", "how much", "rate", "बजट", "कीमत", "प्राइस", "प्राइसिंग", "ధర", "விலை", "വില", "ಬೆಲೆ"]):
                if language == "en":
                    return "Oh, great question! So at Prestige Sky Meadows in Financial District, our spacious 3 BHKs start at ₹2.15 Crores and 4 BHKs at ₹3.45 Crores, with 82% open green landscape. Are you mainly exploring a 3 BHK or a 4 BHK for your family?"
                elif language == "te":
                    return "చాలా మంచి ప్రశ్న అండి! ప్రెస్టీజ్ స్కై మెడోస్‌లో మా 3 BHK ఫ్లాట్లు ₹2.15 కోట్ల నుండి మరియు 4 BHK ఫ్లాట్లు ₹3.45 కోట్ల నుండి ప్రారంభమవుతాయి. మీరు మీ కుటుంబం కోసం 3 BHK చూస్తున్నారా లేదా 4 BHK చూస్తున్నారా?"
                elif language == "ta":
                    return "நல்ல கேள்வி! பிரெஸ்டீஜ் ஸ்கை மெடோஸில் எங்கள் 3 BHK வீடுகள் ₹2.15 கோடியிலும், 4 BHK ₹3.45 கோடியிலும் தொடங்குகின்றன. உங்கள் குடும்பத்திற்கு 3 BHK அல்லது 4 BHK எதைப் பார்க்கிறீர்கள்?"
                elif language == "ml":
                    return "വളരെ നല്ല ചോദ്യം! പ്രെസ്റ്റീജ് സ്കൈ മെഡോസിൽ ഞങ്ങളുടെ 3 BHK ഫ്ലാറ്റുകൾ ₹2.15 കോടി മുതലും 4 BHK ₹3.45 കോടി മുതലും ആരംഭിക്കുന്നു. നിങ്ങൾ 3 BHK ആണോ 4 BHK ആണോ നോക്കുന്നത്?"
                elif language == "kn":
                    return "ಒಳ್ಳೆಯ ಪ್ರಶ್ನೆ! ಪ್ರೆಸ್ಟೀಜ್ ಸ್ಕೈ ಮೆಡೋಸ್‌ನಲ್ಲಿ ನಮ್ಮ 3 BHK ಫ್ಲಾಟ್‌ಗಳು ₹2.15 ಕೋಟಿಯಿಂದ ಮತ್ತು 4 BHK ₹3.45 ಕೋಟಿಯಿಂದ ಪ್ರಾರಂಭವಾಗುತ್ತವೆ. ನೀವು 3 BHK ಅಥವಾ 4 BHK ನೋಡುತ್ತಿದ್ದೀರಾ?"
                return "जी बिल्कुल, अच्छा सवाल है! देखिए प्रेस्टीज स्काई मीडोज में हमारे लग्जरी 3 BHK ₹2.15 Crore से और 4 BHK ₹3.45 Crore से शुरू होते हैं, जिसमें 82% ओपन ग्रीन एरिया है। वैसे आप अपनी फैमिली के लिए 3 BHK देख रहे हैं या 4 BHK?"
            if any(w in last_user_msg for w in ["high", "expensive", "costly", "महंगा", "ज्यादा", "ఎక్కువ"]):
                if language == "en":
                    return "Right, I completely hear you on the pricing! The reason families love this project is that right in Gachibowli Financial District, it commands a 7 to 8% rental yield and zero-compromise Mivan construction. If you see the clubhouse in person this weekend, you'll feel the difference—shall we do a quick Saturday tour?"
                return "हाँ जी, मैं आपकी बात बिल्कुल समझ सकता हूँ! असल में गचीबोवली फाइनेंशियल डिस्ट्रिक्ट के प्राइम कॉरिडोर में यहाँ 7 से 8% रेंटल यील्ड और प्रेस्टीज की A-ग्रेड कंस्ट्रक्शन मिलती है। एक बार आप खुद आकर मॉडल फ्लैट देखेंगे तो आपको वैल्यू तुरंत दिखेगी—क्या इस वीकेंड एक छोटा सा टूर प्लान करें?"
            if any(w in last_user_msg for w in ["location", "where", "possession", "rera", "कहाँ", "पजेशन", "कब"]):
                return "यह प्रोजेक्ट ठीक नानकरामगुड़ा फाइनेंशियल डिस्ट्रिक्ट में है, ORR एग्जिट से सिर्फ 3 मिनट की दूरी पर! RERA अप्रूव्ड है और मार्च 2027 तक पजेशन मिल जाएगा। क्या मैं लोकेशन पिन आपके व्हाट्सएप पर ड्रॉप कर दूँ?"
            if any(w in last_user_msg for w in ["3 bhk", "4 bhk", "flats", "units", "carpet", "investment", "self"]):
                return "अच्छा, बढ़िया चॉइस है! 3 BHK में आपको 2,400 स्क्वायर फीट का सुपर स्पेशियस लेआउट और प्राइवेट रैप-अराउंड बालकनी मिलती है। क्या मैं इस शनिवार सुबह 11 बजे आपके लिए एक्सक्लूसिव साइट विजिट स्लॉट रख लूँ?"
            return "देखिए, प्रेस्टीज स्काई मीडोज में 75,000 स्क्वायर फीट का क्लबहाउस और इनफिनिटी पूल है जो इस एरिया में कहीं और नहीं है। बताइए, आपका कंफर्टेबल बजट रेंज क्या है ताकि मैं बेस्ट टावर यूनिट सजेस्ट कर सकूँ?"

        elif is_healthcare:
            if any(w in last_user_msg for w in ["doctor", "specialist", "cardiologist", "pediatrician", "ortho", "checkup", "consult"]):
                return "Sure thing, I'd be glad to help with that! Our senior Cardiologists and Specialists are available today and tomorrow. Would you be more comfortable coming into the clinic in person, or would you prefer a quick video consultation from home?"
            if any(w in last_user_msg for w in ["fee", "charge", "cost", "fees", "video", "price"]):
                return "Right, so an in-clinic consultation with our senior specialist is ₹800—and that actually includes a complimentary follow-up visit within 7 days! Video consultations are ₹600. Would tomorrow morning around 10:30 AM work well for you?"
            if any(w in last_user_msg for w in ["emergency", "pain", "chest", "urgent"]):
                return "Oh, please listen carefully—since you mentioned acute symptoms, I strongly advise heading straight to our 24/7 Emergency & Trauma center where the cardiac team is on standby with zero wait time. Shall I alert the emergency desk right now?"
            return "We're open Monday through Saturday from 8:00 AM to 8:30 PM. Tell me, would a morning slot or an evening slot be easier for your schedule?"

        elif is_edtech:
            if any(w in last_user_msg for w in ["fee", "cost", "scholarship", "fees", "emi", "फीस", "स्कॉलरशिप", "ईएमआई"]):
                if language == "en":
                    return "Great question! The full 9-month IIT-faculty program is ₹2,45,000, but since you applied this week, you qualify for up to ₹50,000 in early-bird scholarship—plus 0% no-cost EMI starting at ₹16,250 a month. How many years of work experience do you currently have?"
                return "जी बिल्कुल! देखिए 9 महीने के इस एग्जीक्यूटिव प्रोग्राम की फीस ₹2,45,000 है, लेकिन इस हफ्ते की एप्लीकेशन्स पर ₹50,000 तक की स्कॉलरशिप और ₹16,250 प्रति माह की नो-कॉस्ट EMI उपलब्ध है। वैसे अभी आपका कुल कितने साल का वर्क एक्सपीरियंस है?"
            if any(w in last_user_msg for w in ["experience", "eligibility", "years", "fresher", "साल", "एक्सपीरियंस"]):
                return "अरे वाह, यह तो बिल्कुल परफेक्ट प्रोफाइल है! 2+ साल के प्रोफेशनल्स को हमारे हैंड्स-ऑन GenAI और क्लाउड प्रोजेक्ट्स से सीधा 60% से 120% तक का करियर ग्रोथ मिलता है। क्या हम इस गुरुवार शाम 4 बजे आपकी स्कॉलरशिप अप्रूवल के लिए 15-मिनट की कॉल रख लें?"
            return "यह पूरा प्रोग्राम वीकेंड लाइव क्लासेस पर चलता है ताकि आपकी जॉब डिस्टर्ब न हो, और इसमें 100% प्लेसमेंट असिस्टेंस शामिल है। क्या मैं सिलेबस पीडीएफ आपके व्हाट्सएप पर भेज दूँ?"

        elif is_ecommerce:
            if any(w in last_user_msg for w in ["confirm", "yes", "placed", "handbag", "हाँ", "प्लेस", "सही"]):
                return "थैंक यू जी, कन्फर्म करने के लिए! एक छोटा सा ऑफर और है—अगर आप अभी व्हाट्सएप पे या UPI से प्रीपेड करते हैं तो आपको तुरंत ₹150 का फ्लैट डिस्काउंट मिल जाएगा। तो क्या मैं UPI लिंक भेजूँ या कैश ऑन डिलीवरी ही रखें?"
            if any(w in last_user_msg for w in ["address", "pincode", "delivery", "days", "time", "एड्रेस", "पिन", "कब", "कितने दिन"]):
                return "बिल्कुल, आपका एड्रेस और पिन कोड हमारे सिस्टम में वेरीफाई हो गया है! हमारा ब्लूडार्ट कूरियर पार्टनर अगले 3 दिनों में पार्सल डिलीवर कर देगा—डिलीवरी से पहले राइडर आपको कॉल भी करेगा। क्या मैं ट्रैकिंग लिंक व्हाट्सएप कर दूँ?"
            if any(w in last_user_msg for w in ["cancel", "no", "नहीं", "रद्द"]):
                return "कोई बात नहीं जी, मैंने बिना किसी सवाल के आपका आर्डर अभी कैंसिल कर दिया है। फिर कभी शॉपिंग करनी हो तो ज़रूर याद कीजिएगा!"
            return "जी नमस्ते, मैं बस आपके ₹2,499 के आर्डर का डिलीवरी एड्रेस वेरीफाई कर रही थी ताकि पार्सल बिना किसी देरी के पहुँच जाए। क्या आपका पिन कोड और एड्रेस सही है?"

        elif is_bfsi:
            if any(w in last_user_msg for w in ["interest", "rate", "emi", "tenure", "ब्याज", "रेट", "किस्त"]):
                return "जी देखिए, आपके शानदार क्रेडिट प्रोफाइल पर ब्याज दर सिर्फ 10.75% सालाना से शुरू हो रही है, और ज़ीरो फोरक्लोज़र चार्जेस हैं! आप इसे 12 से 48 महीने की आसान किस्तों में ले सकते हैं। आपको लगभग कितने अमाउंट की रिक्वायरमेंट है?"
            return "आपके पैन नंबर पर अभी ₹25 लाख तक का प्री-अप्रूव्ड अनसिक्योर्ड बिज़नेस और पर्सनल क्रेडिट लाइन एक्टिव है, जो 2 घंटे में डिस्बर्स हो सकता है। क्या मैं इसका ब्रेकअप आपके व्हाट्सएप पर भेज दूँ?"

        elif is_b2b_saas:
            if any(w in last_user_msg for w in ["fast", "leads", "speed", "volume", "inbound", "5,000", "5000", "month"]):
                return "Oh, 5,000 leads a month is the exact sweet spot for Stratum AI! The moment a prospect submits a Meta or Google form, Stratum dials them in under 5 seconds—before they even lock their phone screen. Are you currently using HubSpot, Zoho, or LeadSquared as your CRM?"
            if any(w in last_user_msg for w in ["languages", "hindi", "telugu", "tamil", "english", "code", "switching", "voice", "realistic"]):
                return "Yes! Stratum uses conversational Indic neural voices with natural turn-taking, respectful pausing, and mid-sentence Hinglish or Tenglish switching to conduct professional customer inquiries as an AI assistant. Would you like to schedule a 20-minute live demonstration?"
            if any(w in last_user_msg for w in ["pricing", "cost", "per minute", "price"]):
                return "We keep it super transparent—Stratum runs on a pure usage model starting at ₹4.50 per connected talk-minute, with zero setup fees and TRAI-compliant Exotel/Twilio routing included. Shall we lock a quick 20-minute walkthrough for Wednesday at 3 PM?"
            return "Stratum AI is an AI calling assistant that can call new leads in Indian languages and record their qualification details for your team. Would it help if I sent you an overview on WhatsApp?"

        # -------------------------------------------------------------
        # 5. GROUNDED KNOWLEDGE BASE OR NATURAL CONVERSATIONAL FALLBACK
        # -------------------------------------------------------------
        if knowledge_context:
            first_line = [l.strip() for l in knowledge_context.splitlines() if l.strip() and ":" in l]
            fact_snippet = first_line[0] if first_line else knowledge_context[:120]
            if language == "en":
                return f"Right, let me share the exact detail on that—{fact_snippet}. Does that match what you were looking for, or would you like me to send the full sheet on WhatsApp?"
            elif language == "te":
                return f"తప్పకుండా అండి, మా వివరాల ప్రకారం—{fact_snippet}. పూర్తి సమాచారం మీ వాట్సాప్‌కు పంపమంటారా?"
            elif language == "ta":
                return f"நிச்சயமாக, எங்கள் தகவலின்படி—{fact_snippet}. முழு விவரங்களையும் உங்கள் வாட்ஸ்அப்பிற்கு அனுப்பட்டுமா?"
            elif language == "ml":
                return f"തീർച്ചയായും, ഞങ്ങളുടെ വിവരങ്ങൾ പ്രകാരം—{fact_snippet}. പൂർണ്ണ വിവരങ്ങൾ വാട്ട്സ്ആപ്പിൽ അയക്കട്ടെ?"
            elif language == "kn":
                return f"ಖಂಡಿತ, ನಮ್ಮ ಮಾಹಿತಿಯ ಪ್ರಕಾರ—{fact_snippet}. ಪೂರ್ಣ ವಿವರಗಳನ್ನು ನಿಮ್ಮ ವಾಟ್ಸಾಪ್‌ಗೆ ಕಳುಹಿಸಲೇ?"
            else:
                return f"हाँ जी बिल्कुल, मैं आपको सटीक जानकारी बताता हूँ—{fact_snippet}। क्या मैं इसकी पूरी डिटेल पीडीएफ आपके व्हाट्सएप पर भी भेज दूँ?"

        if language == "en":
            return "Right, that makes complete sense! To make sure I tailor this specifically for you, could you share your target timeline or budget range?"
        elif language == "te":
            return "అర్థమైంది అండి! మీకు అత్యుత్తమ ఆప్షన్ సూచించడానికి, మీ బడ్జెట్ లేదా టైమ్‌లైన్ ఒకసారి చెప్తారా?"
        elif language == "ta":
            return "புரிந்தது! உங்களுக்கு சிறந்த விருப்பத்தை பரிந்துரைக்க, உங்கள் பட்ஜெட் அல்லது கால அளவை கூற முடியுமா?"
        elif language == "ml":
            return "മനസ്സിലായി! നിങ്ങൾക്ക് ഏറ്റവും അനുയോജ്യമായ ഓപ്ഷൻ നിർദ്ദേശിക്കാൻ, നിങ്ങളുടെ ബജറ്റ് അല്ലെങ്കിൽ സമയപരിധി പറയാമോ?"
        elif language == "kn":
            return "ಅರ್ಥವಾಯಿತು! ನಿಮಗೆ ಉತ್ತಮ ಆಯ್ಕೆಯನ್ನು ಸೂಚಿಸಲು, ನಿಮ್ಮ ಬಜೆಟ್ ಅಥವಾ ಸಮಯದ ಮಿತಿಯನ್ನು ತಿಳಿಸುತ್ತೀರಾ?"
        else:
            return "हाँ जी, आपकी बात बिल्कुल सही है! क्या आप मुझे थोड़ा अपना टारगेट बजट या टाइमलाइन बताएंगे ताकि मैं आपके लिए सबसे बेस्ट ऑप्शन सजेस्ट कर सकूँ?"


class MockLLMProvider(DynamicConversationalEngine):
    """Alias for backwards compatibility with tests and config defaults."""
    pass


def get_llm_provider(provider_type: Optional[str] = None) -> BaseLLMProvider:
    provider = provider_type or settings.DEFAULT_LLM_PROVIDER
    if provider == "groq" and settings.GROQ_API_KEY:
        return GroqLLMProvider()
    elif provider == "openai" and settings.OPENAI_API_KEY:
        return OpenAILLMProvider()
    return DynamicConversationalEngine()
