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
from fastapi import Request
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


async def extract_twilio_request_params(request: Request) -> Dict[str, Any]:
    """
    Extracts all parameters sent by Twilio in either form-data, query parameters, or JSON.
    FastAPI / Starlette safely caches request.form() internally so repeated calls are instantaneous.
    """
    params: Dict[str, Any] = {}
    if request is None:
        return params

    # Query parameters
    if hasattr(request, "query_params") and request.query_params:
        params.update(dict(request.query_params))

    # POST body parameters
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "").lower()
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                form = await request.form()
                params.update({k: str(v) for k, v in form.items()})
            except Exception:
                pass
        elif "application/json" in content_type:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    params.update({k: str(v) for k, v in body.items()})
            except Exception:
                pass
    return params


async def verify_twilio_webhook_request(
    request: Request,
    body_params: Optional[Dict[str, Any]] = None,
    enforce_signature: bool = False
) -> Tuple[bool, str]:
    """
    Verifies the integrity of an incoming Twilio webhook with multi-scheme tunnel support.
    Automatically extracts POST form parameters so HMAC calculations always match Twilio's standard.
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
        # Cannot verify without Twilio Auth Token configured
        return True, "Twilio Auth Token not configured, skipping validation"

    if body_params is None:
        params = await extract_twilio_request_params(request)
    else:
        params = body_params

    canonical_url = get_effective_twilio_request_url(request)

    # Candidate URLs to test against Twilio signature: accounts for reverse proxies, SSL offloading, and ports
    candidate_urls = [canonical_url]
    direct_url = str(request.url)
    if direct_url not in candidate_urls:
        candidate_urls.append(direct_url)

    # Add https / http scheme variants
    for u in list(candidate_urls):
        if u.startswith("http://"):
            https_u = "https://" + u[7:]
            if https_u not in candidate_urls:
                candidate_urls.append(https_u)
        elif u.startswith("https://"):
            http_u = "http://" + u[8:]
            if http_u not in candidate_urls:
                candidate_urls.append(http_u)

    # Add port-stripped variants (e.g. :443 or :8000)
    for u in list(candidate_urls):
        if ":443/" in u:
            stripped = u.replace(":443/", "/")
            if stripped not in candidate_urls:
                candidate_urls.append(stripped)
        if ":8000/" in u:
            stripped = u.replace(":8000/", "/")
            if stripped not in candidate_urls:
                candidate_urls.append(stripped)

    for candidate in candidate_urls:
        if validate_twilio_signature(url=candidate, params=params, signature=signature, auth_token=auth_token):
            return True, f"Signature verified successfully against {candidate}"

    logger.warning(
        f"Twilio signature validation failed. Checked {len(candidate_urls)} candidate URLs for signature '{signature[:8]}...'. "
        f"Param keys: {list(params.keys())}"
    )
    return False, f"Twilio signature verification failed for {canonical_url}"
