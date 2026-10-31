"""
Stratum AI Telephony Structured Observability & Correlation Logger
==================================================================
Provides structured, correlated, and privacy-safe logging across every stage
of the telephony lifecycle (PSTN dial, answer, TwiML, speech, AI turn, status, summary).
Complies with SOC-2, GDPR, and TRAI PII protection standards.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.telephony.twilio_security import redact_telephony_payload

logger = logging.getLogger("stratum.telephony.lifecycle")


def sanitize_text_for_logging(text: Optional[str], max_len: int = 120) -> str:
    """
    Sanitizes user utterances or prompts to prevent log injection
    and PII leakage while preserving diagnostic value.
    """
    if not text:
        return ""
    # Strip control characters, newlines, and ANSI escape codes
    clean = re.sub(r"[\r\n\t\x00-\x1f\x7f-\x9f]", " ", str(text)).strip()
    # Mask Indian phone numbers or 10-12 digit sequences
    clean = re.sub(r"(\+?\d{2,3})?\s*(\d{2,3})\d{4,6}(\d{2})", r"\1***\3", clean)
    if len(clean) > max_len:
        clean = clean[:max_len] + f"... [len={len(text)}]"
    return clean


def log_telephony_event(
    event_type: str,
    call_id: str,
    provider: str = "twilio",
    component: str = "telephony.gateway",
    level: str = "info",
    call_sid: Optional[str] = None,
    tenant_id: Optional[str] = None,
    outcome: str = "success",
    duration_ms: Optional[float] = None,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
):
    """
    Emits a structured JSON log entry for telephony events correlated by call_id.
    Redacts all secrets, tokens, customer phone numbers, and full transcripts automatically.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    raw_details = details or {}
    clean_details = redact_telephony_payload(raw_details)

    # Sanitize user speech/transcripts if passed in details
    for transcript_key in ["speech_result", "ai_text", "user_text", "transcript", "prompt"]:
        if transcript_key in clean_details and clean_details[transcript_key]:
            clean_details[f"{transcript_key}_sanitized"] = sanitize_text_for_logging(clean_details[transcript_key])
            clean_details[f"{transcript_key}_chars"] = len(str(clean_details[transcript_key]))
            clean_details.pop(transcript_key, None)

    # Mask tenant ID for safe internal identification
    safe_tenant = f"{tenant_id[:8]}***" if tenant_id and len(tenant_id) > 8 else (tenant_id or "default")

    record: Dict[str, Any] = {
        "timestamp": now_iso,
        "event_name": event_type,
        "call_id": call_id,
        "call_sid": call_sid or clean_details.get("CallSid"),
        "tenant_id": safe_tenant,
        "provider": provider,
        "component": component,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "error_code": error_code,
        "details": clean_details,
    }
    if error:
        record["error"] = sanitize_text_for_logging(error, max_len=200)

    # Serialize to compact, safe JSON string
    log_line = json.dumps(record, default=str)
    prefix = f"[TELEPHONY] [{event_type.upper()}] [call_id={call_id}]"

    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(f"{prefix} {log_line}")
