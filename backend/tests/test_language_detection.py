import pytest
from app.voice.language_detector import detector

def test_telugu_code_switching_detection():
    # Mix of Telugu script and English words
    text = "నాకు మీ product గురించి తెలుసుకోవాలి."
    res = detector.analyze(text, current_language="en")
    assert res["detected_language"] == "te"
    assert res["is_code_switched"] == True

def test_hindi_script_detection():
    text = "मुझे इसका price बताइए, और delivery कितने दिन में होगी?"
    res = detector.analyze(text, current_language="te")
    assert res["detected_language"] == "hi"
    assert res["is_code_switched"] == True

def test_explicit_language_switch():
    text = "Can you explain this in English?"
    res = detector.analyze(text, current_language="te")
    assert res["detected_language"] == "en"
    assert res["explicit_switch"] == True

    text_hi = "हिंदी में बताइए"
    res_hi = detector.analyze(text_hi, current_language="te")
    assert res_hi["detected_language"] == "hi"
    assert res_hi["explicit_switch"] == True

def test_human_transfer_detection():
    text1 = "I want to speak to a person."
    res1 = detector.analyze(text1, current_language="en")
    assert res1["wants_human"] == True

    text2 = "నాకు అధికారితో మాట్లాడాలి"
    res2 = detector.analyze(text2, current_language="te")
    assert res2["wants_human"] == True

def test_romanized_telugu():
    text = "sir nakku complete details kavali"
    res = detector.analyze(text, current_language="en")
    assert res["detected_language"] == "te"
    assert res["is_code_switched"] == True
