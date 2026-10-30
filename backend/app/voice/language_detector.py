import re
from typing import Tuple, Dict, Any, Optional

class IndianLanguageDetector:
    """
    High-accuracy language detection and code-switching analyzer for Indian languages.
    Supports native Unicode script analysis, transliterated phonetic keywords,
    and explicit conversational language switch requests.
    """

    # Unicode ranges for major Indian scripts
    SCRIPT_RANGES = {
        "te": (0x0C00, 0x0C7F),  # Telugu
        "hi": (0x0900, 0x097F),  # Devanagari (Hindi, Marathi)
        "ta": (0x0B80, 0x0BFF),  # Tamil
        "kn": (0x0C80, 0x0CFF),  # Kannada
        "ml": (0x0D00, 0x0D7F),  # Malayalam
        "bn": (0x0980, 0x09FF),  # Bengali / Assamese
        "gu": (0x0A80, 0x0AFF),  # Gujarati
        "pa": (0x0A00, 0x0A7F),  # Gurmukhi (Punjabi)
        "or": (0x0B00, 0x0B7F),  # Odia
    }

    # Transliterated and romanized markers
    ROMAN_MARKERS = {
        "te": [
            "kavali", "cheppandi", "telugulo", "matladandi", "enti", "emiti", "ela", "entha",
            "undi", "chesara", "chudandi", "bagundi", "ledu", "avutunda", "gurinchi",
            "dhanyavadalu", "avunu", "kadu", "meeru", "naku", "manaki", "repu"
        ],
        "hi": [
            "batayein", "batao", "kariye", "kitna", "kya", "chahiye",
            "karein", "kaise", "hoga", "shukriya", "dhanyawad", "namaste", "mujhe",
            "humko", "bolo", "achha", "theek", "nahi", "haan", "aap", "kijiye"
        ],
        "ta": [
            "sollunga", "tamilil", "pesunga", "theriyum", "illai", "aam", "vanakkam",
            "ennaku", "venum", "nandri", "eppadi", "evvalavu", "irukku", "pannunga"
        ],
        "kn": [
            "heli", "kannadadalli", "mathadi", "maathadi", "beku", "illa", "houdu", "namaskara",
            "nanage", "hege", "eshtu", "maadi", "idhe"
        ],
        "ml": [
            "parayu", "parayamo", "malayalathil", "samsarikku", "samsarikkanam", "venam",
            "venda", "athe", "alla", "nanni", "engane", "ethra", "enikku", "ningal", "undo"
        ]
    }

    # Explicit phrases requesting language switch
    EXPLICIT_SWITCH_PATTERNS = [
        (re.compile(r"(తెలుగులో|telugu\s*lo|speak\s*in\s*telugu|in\s*telugu|switch\s*to\s*telugu)", re.IGNORECASE), "te"),
        (re.compile(r"(हिंदी\s*में|hindi\s*me|hindi\s*mein|speak\s*in\s*hindi|in\s*hindi|switch\s*to\s*hindi)", re.IGNORECASE), "hi"),
        (re.compile(r"(english\s*me|in\s*english|speak\s*in\s*english|switch\s*to\s*english|tell\s*me\s*in\s*english)", re.IGNORECASE), "en"),
        (re.compile(r"(தமிழ்|தமிழில்|tamil\s*il|tamil\s*la|speak\s*in\s*tamil|in\s*tamil|switch\s*to\s*tamil)", re.IGNORECASE), "ta"),
        (re.compile(r"(ಕನ್ನಡ|ಕನ್ನಡದಲ್ಲಿ|kannada\s*dalli|speak\s*in\s*kannada|in\s*kannada|switch\s*to\s*kannada)", re.IGNORECASE), "kn"),
        (re.compile(r"(മലയാളം|മലയാളത്തിൽ|malayalathil|malayalam\s*lo|speak\s*in\s*malayalam|in\s*malayalam|switch\s*to\s*malayalam)", re.IGNORECASE), "ml")
    ]

    # Escalation / Human Transfer keywords
    HUMAN_TRANSFER_PATTERNS = [
        re.compile(r"\b(human|person|agent|executive|officer|representative|manager|manishi|adhikari)\b", re.IGNORECASE),
        re.compile(r"(speak\s*to\s*someone|talk\s*to\s*a\s*person|connect\s*me\s*to|transfer\s*call|escalate)", re.IGNORECASE),
        re.compile(r"(మనిషితో\s*మాట్లాడాలి|అధికారితో\s*మాట్లాడాలి|వ్యక్తితో\s*మాట్లాడాలి)", re.IGNORECASE),
        re.compile(r"(अधिकारी\s*से\s*बात|इंसान\s*से\s*बात|कस्टमर\s*केयर\s*से\s*बात|मैनेजर\s*से\s*बात)", re.IGNORECASE),
        re.compile(r"(மனிதரிடம்\s*பேச|மேலாளரிடம்\s*பேச|அதிகாரியிடம்\s*பேச)", re.IGNORECASE),
        re.compile(r"(മനുഷ്യനോട്\s*സംസാരിക്കണം|മാനേജരുമായി\s*സംസാരിക്കണം|ഉദ്യോഗസ്ഥനുമായി)", re.IGNORECASE),
        re.compile(r"(ಮನುಷ್ಯರೊಂದಿಗೆ\s*ಮಾತನಾಡಬೇಕು|ಮ್ಯಾನೇಜರ್\s*ಜೊತೆ\s*ಮಾತನಾಡಬೇಕು|ಅಧಿಕಾರಿಯೊಂದಿಗೆ)", re.IGNORECASE)
    ]

    @classmethod
    def detect_explicit_switch(cls, text: str) -> Optional[str]:
        """Check if customer explicitly asks to change language."""
        for pattern, lang in cls.EXPLICIT_SWITCH_PATTERNS:
            if pattern.search(text):
                return lang
        return None

    @classmethod
    def detect_human_handoff(cls, text: str) -> bool:
        """Check if customer is requesting human transfer."""
        for pattern in cls.HUMAN_TRANSFER_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @classmethod
    def analyze(cls, text: str, current_language: str = "te") -> Dict[str, Any]:
        """
        Analyze utterance for language, code-switching, script metrics, and transfer intent.
        Returns: {
            "detected_language": str,
            "is_code_switched": bool,
            "explicit_switch": bool,
            "wants_human": bool,
            "confidence": float
        }
        """
        clean_text = text.strip()
        if not clean_text:
            return {
                "detected_language": current_language,
                "is_code_switched": False,
                "explicit_switch": False,
                "wants_human": False,
                "confidence": 1.0
            }

        wants_human = cls.detect_human_handoff(clean_text)

        # 1. Check explicit command (e.g. "Can you explain in English?", "తెలుగులో చెప్పండి")
        explicit_target = cls.detect_explicit_switch(clean_text)
        if explicit_target:
            return {
                "detected_language": explicit_target,
                "is_code_switched": True,
                "explicit_switch": True,
                "wants_human": wants_human,
                "confidence": 0.99
            }

        # 2. Count Unicode script characters
        script_counts = {lang: 0 for lang in cls.SCRIPT_RANGES}
        latin_count = 0
        total_chars = 0

        for char in clean_text:
            cp = ord(char)
            total_chars += 1
            matched = False
            for lang, (start, end) in cls.SCRIPT_RANGES.items():
                if start <= cp <= end:
                    script_counts[lang] += 1
                    matched = True
                    break
            if not matched and (('a' <= char <= 'z') or ('A' <= char <= 'Z')):
                latin_count += 1

        # Check native script dominance
        max_script_lang, max_script_count = max(script_counts.items(), key=lambda x: x[1])
        if max_script_count > 0:
            is_code_switched = (latin_count > 0 and max_script_count > 0)
            confidence = max_script_count / max(total_chars, 1)
            return {
                "detected_language": max_script_lang,
                "is_code_switched": is_code_switched,
                "explicit_switch": False,
                "wants_human": wants_human,
                "confidence": min(confidence + 0.3, 0.98)
            }

        # 3. If written in Latin script (e.g., English or Romanized Telugu/Hindi)
        words = [w.lower() for w in re.findall(r"\b\w+\b", clean_text)]
        marker_scores = {lang: 0 for lang in cls.ROMAN_MARKERS}
        for word in words:
            for lang, markers in cls.ROMAN_MARKERS.items():
                if word in markers:
                    marker_scores[lang] += 1

        best_roman_lang, best_roman_score = max(marker_scores.items(), key=lambda x: x[1])
        if best_roman_score > 0:
            # Contains transliterated words mixed with English
            return {
                "detected_language": best_roman_lang,
                "is_code_switched": True,
                "explicit_switch": False,
                "wants_human": wants_human,
                "confidence": 0.85
            }

        # 4. English detection or maintain context language
        # If text is in Latin script with no Indic transliteration markers, it is English
        if latin_count >= 2:
            return {
                "detected_language": "en",
                "is_code_switched": False,
                "explicit_switch": False,
                "wants_human": wants_human,
                "confidence": 0.95
            }

        return {
            "detected_language": current_language,
            "is_code_switched": False,
            "explicit_switch": False,
            "wants_human": wants_human,
            "confidence": 0.70
        }

detector = IndianLanguageDetector()
