"""
Twilio Webhook Security & Request Signature Verification
=========================================================
Implements Twilio signature verification using the official Twilio SDK RequestValidator:
https://www.twilio.com/docs/usage/security#validating-requests

Features:
- Official Twilio RequestValidator with constant-time HMAC-SHA1 verification.
- Full support for multi-param forms, repeated keys, and GET/POST payloads.
- Multi-scheme URL normalization for reverse proxies and SSL tunnels.
- PII and credential redaction for diagnostic logging.
"""

import hmac
import hashlib
import base64
import logging
from typing import Dict, Any, Tuple, Optional, Union
from fastapi import Request
from app.config import settings

logger = logging.getLogger("stratum.telephony.security")

try:
    from twilio.request_validator import RequestValidator
except ImportError:
    RequestValidator = None


class TwilioParamDict(dict):
    """
    Dictionary adapter supporting .getlist() and .getall() for Twilio RequestValidator,
    ensuring multiple values for repeated parameter keys are handled per Twilio specs.
    """
    def getlist(self, key: str):
        val = self.get(key)
        if isinstance(val, (list, tuple)):
            return [str(v) for v in val]
        return [str(val)] if val is not None else []

    def getall(self, key: str):
        return self.getlist(key)


def compute_twilio_signature(url: str, params: Optional[Dict[str, Any]], auth_token: str) -> str:
    """
    Computes the expected Twilio X-Twilio-Signature for a request.
    Uses official Twilio RequestValidator where available.
    """
    if not auth_token:
        return ""

    param_adapter = TwilioParamDict(params or {})

    if RequestValidator is not None:
        validator = RequestValidator(auth_token)
        return validator.compute_signature(url, param_adapter)

    # Pure Python fallback matching Twilio's standard
    data_to_sign = url
    if param_adapter:
        for key in sorted(set(param_adapter.keys())):
            values = param_adapter.getlist(key)
            for item in sorted(set(values)):
                data_to_sign += f"{key}{item}"

    digest = hmac.new(
        auth_token.encode("utf-8"),
        data_to_sign.encode("utf-8"),
        hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def validate_twilio_signature(
    url: str,
    params: Optional[Dict[str, Any]],
    signature: str,
    auth_token: str
) -> bool:
    """
    Validates that an incoming request signature matches the expected Twilio signature.
    Uses constant-time comparison via Twilio RequestValidator.
    """
    if not signature or not auth_token:
        return False

    param_adapter = TwilioParamDict(params or {})

    if RequestValidator is not None:
        try:
            validator = RequestValidator(auth_token)
            return validator.validate(url, param_adapter, signature)
        except Exception as e:
            logger.debug(f"RequestValidator exception: {e}")

    # Fallback with constant-time compare_digest
    expected = compute_twilio_signature(url=url, params=param_adapter, auth_token=auth_token)
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


async def extract_twilio_request_params(request: Request) -> TwilioParamDict:
    """
    Extracts parameters sent by Twilio in either form-data or JSON body.
    For GET requests, parameters are empty because query parameters are already part of the URL.
    For POST requests, extracts application/x-www-form-urlencoded or multipart/form-data.
    FastAPI / Starlette safely caches request.form() internally so repeated calls are instantaneous.
    Supports single values and repeated keys according to Twilio RequestValidator specs.
    """
    params = TwilioParamDict()
    if request is None:
        return params

    # Twilio signs the URL itself for GET requests; body params only apply to POST/PUT/PATCH
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "").lower()
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                form = await request.form()
                for k in form.keys():
                    vals = form.getlist(k)
                    if len(vals) > 1:
                        params[k] = [str(v) for v in vals]
                    elif len(vals) == 1:
                        params[k] = str(vals[0])
            except Exception as e:
                logger.debug(f"Error parsing form data: {e}")
        elif "application/json" in content_type:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    params.update({k: str(v) for k, v in body.items()})
            except Exception as e:
                logger.debug(f"Error parsing JSON body: {e}")
    return params


async def verify_twilio_webhook_request(
    request: Request,
    body_params: Optional[Dict[str, Any]] = None,
    enforce_signature: bool = True
) -> Tuple[bool, str]:
    """
    Verifies the integrity of an incoming Twilio webhook with multi-scheme tunnel support.
    Uses official Twilio RequestValidator with constant-time HMAC calculation.
    Returns (is_valid, reason).
    """
    auth_token = settings.TWILIO_AUTH_TOKEN
    signature = request.headers.get("x-twilio-signature", "").strip()
    is_production = getattr(settings, "APP_ENV", "development") == "production"

    if not signature:
        if is_production or enforce_signature:
            return False, "Missing X-Twilio-Signature header"
        logger.debug("Twilio webhook received without X-Twilio-Signature header (permissive dev mode)")
        return True, "No signature header provided (permissive mode)"

    if not auth_token:
        if is_production:
            return False, "Twilio Auth Token not configured in production"
        return True, "Twilio Auth Token not configured, skipping validation"

    if body_params is None:
        params = await extract_twilio_request_params(request)
    else:
        params = TwilioParamDict(body_params)

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

    # Add port-stripped variants (e.g. :443, :8000, :80)
    for u in list(candidate_urls):
        for port_str in (":443/", ":8000/", ":80/"):
            if port_str in u:
                stripped = u.replace(port_str, "/")
                if stripped not in candidate_urls:
                    candidate_urls.append(stripped)

    for candidate in candidate_urls:
        if validate_twilio_signature(url=candidate, params=params, signature=signature, auth_token=auth_token):
            return True, f"Signature verified successfully against {candidate}"

    logger.warning(
        f"Twilio signature validation failed. Evaluated {len(candidate_urls)} candidate URLs for signature. "
        f"Param keys count: {len(params)}"
    )
    return False, f"Twilio signature verification failed for {canonical_url}"
