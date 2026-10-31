"""
Stratum AI Telephony Structured Observability & Correlation Logger
==================================================================
Provides structured, correlated, and privacy-safe logging across every stage
of the telephony lifecycle (PSTN dial, answer, TwiML, speech, AI turn, status, summary).
Automatically redacts sensitive credentials and customer PII.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.telephony.twilio_security import redact_telephony_payload

logger = logging.getLogger("stratum.telephony.lifecycle")


def log_telephony_event(
    event_type: str,
    call_id: str,
    provider: str = "twilio",
    level: str = "info",
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
):
    """
    Emits a structured JSON log entry for telephony events correlated by call_id.
    Redacts all secrets, tokens, and customer phone numbers automatically.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    clean_details = redact_telephony_payload(details or {})

    record = {
        "timestamp": now_iso,
        "event": event_type,
        "call_id": call_id,
        "provider": provider,
        "details": clean_details,
    }
    if error:
        record["error"] = error

    msg = f"[TELEPHONY] [{event_type.upper()}] [call_id={call_id}] {json.dumps(record, default=str)}"

    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(msg)
