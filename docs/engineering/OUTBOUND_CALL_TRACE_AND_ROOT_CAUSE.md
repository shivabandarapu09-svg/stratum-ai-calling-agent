# STRATUM AI — OUTBOUND CALL TRACE AND ROOT CAUSE ANALYSIS

## Executive Summary
This document records the end-to-end trace of an outbound telephone call in Stratum AI, identifies the exact failure points responsible for the *"check the URL / server cannot be reached"* audio prompt and immediate disconnection, and details the engineering repairs required.

---

## 1. End-to-End Outbound Call Architecture

```
[ User Action: Dial PSTN in UI ]
               │
               ▼
1. Frontend API Call: POST /api/calls/initiate
   - File: frontend/src/pages/LiveCallSimulator.tsx (handleStartCall)
   - Function: initiateOutboundCall() in frontend/src/api.ts
               │
               ▼
2. Backend Endpoint: POST /api/calls/initiate
   - File: backend/app/api/calls.py
   - Function: initiate_call()
   - Resolves PUBLIC_BASE_URL (from settings or .env)
   - Constructs Voice Webhook URL:
     https://<tunnel-domain>/api/telephony/twilio/twiml/{call_id}
               │
               ▼
3. Carrier Dispatch: Twilio REST API
   - File: backend/app/telephony/twilio_provider.py
   - Function: TwilioProvider.initiate_call()
   - Endpoint: POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Calls.json
   - Parameters Sent:
     • To: Customer phone number (E.164)
     • From: Twilio trial caller ID
     • Url: https://<tunnel-domain>/api/telephony/twilio/twiml/{call_id}
     • StatusCallback: https://<tunnel-domain>/api/telephony/twilio/status/{call_id}
     *(Note: StatusCallbackMethod is intentionally omitted)*
               │
               ▼
4. Twilio Cloud dials Recipient PSTN Device
   - Phone rings and recipient answers.
   - For Twilio Free Trial accounts: Twilio plays trial preamble:
     "You have a trial account. Press any key to execute your code."
               │
               ▼
5. Webhook Execution by Twilio Cloud:
   - Twilio cloud makes HTTP POST request to:
     https://<tunnel-domain>/api/telephony/twilio/twiml/{call_id}
   - Headers: X-Twilio-Signature, Content-Type: application/x-www-form-urlencoded
   - Form Body: CallSid, AccountSid, From, To, CallStatus, Direction, ApiVersion
               │
               ▼
       [ FAILURE OCCURS HERE ]
```

---

## 2. Confirmed Root Causes

### Root Cause 1: Dead Placeholder Public URL in Environment Configuration
- **Evidence:** `backend/.env` and `.env` contain:
  ```env
  PUBLIC_WEBHOOK_URL=https://your-domain.ngrok-free.app
  PUBLIC_BASE_URL=https://your-domain.ngrok-free.app
  ```
- **Mechanism:** Twilio cloud executes an HTTP POST to `https://your-domain.ngrok-free.app/api/telephony/twilio/twiml/{call_id}`. Because `your-domain.ngrok-free.app` is an unregistered/dead domain, DNS resolution fails or returns an HTTP connection timeout.
- **Twilio Carrier Response:** When Twilio cannot fetch the voice URL, Twilio plays error prompt:
  *"An application error has occurred. Please check the URL or check the Twilio debugger."*
  Twilio logs **Error 11200 / 11206 (HTTP retrieval failure)** in the Twilio Console debugger and disconnects the call immediately.
- **Local Impact:** Because Twilio never reached `localhost:8000`, no webhook arrived, no speech turn was recorded, the call remained in `ringing` status or hung up with 0 duration, and the dashboard showed no conversational progress.

### Root Cause 2: Flawed Carrier Signature Verification in `twilio_twiml_endpoint`
- **Evidence:** In `backend/app/api/telephony.py` lines 312-317:
  ```python
  if request is not None and request.headers.get("x-twilio-signature") and settings.TWILIO_AUTH_TOKEN:
      valid, reason = await verify_twilio_webhook_request(request, enforce_signature=True)
      if not valid:
          raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Carrier signature rejected: {reason}")
  ```
- **Mechanism:** Twilio signs its webhook POST requests by hashing the canonical URL concatenated with all sorted POST form parameters (`CallSid`, `From`, `To`, `CallStatus`, etc.) using HMAC-SHA1 with the Twilio Auth Token.
  However, `twilio_twiml_endpoint` did not read `request.form()` and passed `body_params=None` to `verify_twilio_webhook_request`.
- **Result:** Stratum computed HMAC over the URL with **empty parameters `{}`**, whereas Twilio computed HMAC over the URL with **all form parameters**. The signatures never matched. Stratum responded with **HTTP 403 Forbidden**. Twilio treats HTTP 403 as an application error, plays *"check the URL"*, and hangs up.

### Root Cause 3: Inadequate Pre-Flight Validation Before PSTN Dialing
- **Evidence:** Prior to initiation, if a user triggered a call while `PUBLIC_BASE_URL` was set to a placeholder, the system either:
  1. Failed silently into `TRIAL_DEMO_VOICE_URL` (`demo.twilio.com/docs/voice.xml`), bypassing the Stratum conversational AI engine entirely, or
  2. Allowed the dial to proceed with `your-domain.ngrok-free.app`, burning Twilio balance on guaranteed-to-fail calls.

---

## 3. Discovered System Configuration
| Property | Configured Value | Status / Note |
|---|---|---|
| **Backend Framework** | FastAPI (uvicorn) | Port 8000 (PID 4344) |
| **Frontend Framework** | React 18 + Vite | Port 3000 (proxies `/api` to 8000) |
| **Twilio Account SID** | `AC4094...ecc1` | Configured |
| **Twilio Phone Number** | `+17372212163` | Configured |
| **Public Base URL** | `https://your-domain.ngrok-free.app` | **DEFECT:** Dummy placeholder |
| **StatusCallbackMethod**| *Omitted* | **PRESERVED:** Do not reintroduce |
| **Twilio Account Type** | Free Trial | Requires Verified Caller IDs for `To` |

---

## 4. Remediation Plan

1. **Purge Placeholder Domains:** Clean `.env` files and enforce strict pre-flight blocking on any dial attempt when `PUBLIC_BASE_URL` is empty, not HTTPS, or contains placeholder patterns (`your-domain`, `example.com`, `localhost`).
2. **Fix Webhook Signature Verification:** Ensure `verify_twilio_webhook_request` automatically parses and includes form parameters from POST requests during HMAC calculation.
3. **Multi-Turn TwiML Voice Engine:** Validate `/api/telephony/twilio/twiml/{call_id}`, `/api/telephony/twilio/gather/{call_id}`, and `/api/telephony/twilio/reprompt/{call_id}` to ensure standard XML headers (`application/xml`), valid `<Gather>` actions, barge-in support, and automatic reprompts.
4. **Structured Correlation Logging:** Add correlated `call_id` logging across the entire call lifecycle with secret/PII redaction.
5. **UI Visibility & Diagnostics:** Provide explicit tunnel status in the Live Voice Studio and Settings so users are guided to start their tunnel (`ngrok http 8000`) before dialing.
