"""
Twilio Webhook Security & Request Signature Verification
=========================================================
Implements Twilio HMAC-SHA1 signature verification according to official specs:
https://www.twilio.com/docs/usage/security#validating-requests

Features:
- Pure Python HMAC-SHA1 calculation matching Twilio's standard.
- Robust URL reconstruction matching public reverse-proxy / tunnel domains.
- Parameter sorting and string-to-sign generation.
- Sensitive credential and PII redaction for safe logging.
"""

import hmac
import hashlib
import base64
import logging
from typing import Dict, Any, Tuple, Optional
from fastapi import HTTPException, Request, status
from app.config import settings

logger = logging.getLogger("stratum.telephony.security")


def compute_twilio_signature(url: str, params: Dict[str, Any], auth_token: str) -> str:
    """
    Computes the expected Twilio X-Twilio-Signature for a request.
    1. Sorts all POST parameters alphabetically by parameter name.
    2. Appends each parameter key and its value to the URL string.
    3. Signs the result using HMAC-SHA1 with the Twilio Auth Token.
    4. Returns the base64-encoded digest.
    """
    if not auth_token:
        return ""

    # Twilio signature appends sorted key-value pairs without delimiters
    data_to_sign = url
    if params:
        for key in sorted(params.keys()):
            val = params[key]
            if val is not None:
                data_to_sign += f"{key}{val}"

    digest = hmac.new(
        auth_token.encode("utf-8"),
        data_to_sign.encode("utf-8"),
        hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def validate_twilio_signature(
    url: str,
    params: Dict[str, Any],
    signature: str,
    auth_token: str
) -> bool:
    """
    Validates that an incoming request signature matches the expected Twilio signature.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not signature or not auth_token:
        return False

    expected = compute_twilio_signature(url=url, params=params, auth_token=auth_token)
    return hmac.compare_digest(expected, signature)


def get_effective_twilio_request_url(request: Request) -> str:
    """
    Determines the canonical public URL that Twilio called, accounting for
    configured PUBLIC_BASE_URL, SSL termination proxies, and port forwarding.
    """
    # If a public base URL is explicitly configured, use it to ensure domain/scheme match
    public_base = settings.get_public_base_url()
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    if public_base:
        return f"{public_base}/{path.lstrip('/')}"

    # Otherwise reconstruct from headers
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    scheme = "https" if forwarded_proto == "https" or "https" in str(request.url) else "http"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
    return f"{scheme}://{host}/{path.lstrip('/')}"


def redact_telephony_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a sanitized copy of telephony payload data suitable for debug logs
    without leaking Auth Tokens, SIDs, passwords, or full customer phone numbers.
    """
    redacted = {}
    sensitive_keys = {"auth_token", "token", "secret", "password", "key", "api_key", "authorization"}
    
    for k, v in payload.items():
        k_lower = str(k).lower()
        if any(sk in k_lower for sk in sensitive_keys):
            redacted[k] = "[REDACTED_SECRET]"
        elif k_lower in ("from", "to", "caller", "called", "customer_phone", "phone"):
            val_str = str(v)
            if len(val_str) > 5:
                redacted[k] = f"{val_str[:3]}***{val_str[-2:]}"
            else:
                redacted[k] = "***"
        else:
            redacted[k] = v
    return redacted


async def verify_twilio_webhook_request(
    request: Request,
    body_params: Optional[Dict[str, Any]] = None,
    enforce_signature: bool = False
) -> Tuple[bool, str]:
    """
    Verifies the integrity of an incoming Twilio webhook.
    Returns (is_valid, reason).
    """
    auth_token = settings.TWILIO_AUTH_TOKEN
    signature = request.headers.get("x-twilio-signature", "").strip()

    if not signature:
        if enforce_signature:
            return False, "Missing X-Twilio-Signature header"
        # In non-enforced development mode, warn but allow
        logger.debug("Twilio webhook received without X-Twilio-Signature header (permissive dev mode)")
        return True, "No signature header provided (permissive mode)"

    if not auth_token:
        if enforce_signature:
            return False, "Twilio Auth Token not configured; cannot verify webhook signature"
        # Cannot verify without Twilio Auth Token configured (permissive dev mode only)
        return True, "Twilio Auth Token not configured, skipping validation"

    canonical_url = get_effective_twilio_request_url(request)
    params = body_params or {}

    is_valid = validate_twilio_signature(
        url=canonical_url,
        params=params,
        signature=signature,
        auth_token=auth_token
    )

    if not is_valid:
        # Also try request.url directly in case Twilio reached it without proxy rewrite
        direct_url = str(request.url)
        if direct_url != canonical_url:
            is_valid = validate_twilio_signature(
                url=direct_url,
                params=params,
                signature=signature,
                auth_token=auth_token
            )

    if not is_valid:
        logger.warning(
            f"Twilio signature validation failed for URL: {canonical_url} (params count: {len(params)})"
        )
        return False, f"Twilio signature verification failed for {canonical_url}"

    return True, "Signature verified successfully"


async def require_twilio_signature(request: Request) -> None:
    """
    FastAPI dependency for Twilio-facing webhooks (`dependencies=[Depends(require_twilio_signature)]`).
    Rejects requests without a valid `X-Twilio-Signature` unless ENFORCE_TWILIO_SIGNATURES is disabled.
    """
    if not settings.ENFORCE_TWILIO_SIGNATURES:
        return

    params: Dict[str, Any] = {}
    if request.method == "POST":
        content_type = request.headers.get("content-type", "").lower()
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            params = {k: v for k, v in form.items()}

    ok, reason = await verify_twilio_webhook_request(request, params, enforce_signature=True)
    if not ok:
        logger.warning("Rejected Twilio webhook %s %s: %s", request.method, request.url.path, reason)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")
