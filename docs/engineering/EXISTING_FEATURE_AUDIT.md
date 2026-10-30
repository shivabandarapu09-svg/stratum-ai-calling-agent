# STRATUM AI — EXISTING FEATURE AUDIT

**Revision:** 1.1 (corrects revision 1.0, which overstated verification status)
**Date:** 2026-10-30

## Classification

| Status | Meaning |
|---|---|
| Verified (automated) | Covered by a passing automated test that checks behaviour or state. |
| Code present, unverified | Code exists and compiles; no test or live run confirms it works. |
| Partial | Works on some paths; key behaviour missing. |
| Broken / unsafe | Wrong behaviour, or a security defect. |
| Missing | Required, not implemented. |
| Blocked | Needs external credentials, carrier access or a public URL. |

**Evidence available:** 71/71 backend tests pass (`PYTHONPATH=backend backend\venv\Scripts\pytest backend\tests`). Frontend `tsc && vite build` succeeds. **No live phone call, real STT provider, real LLM provider or human listening test has been run during this audit.** A successful build is not evidence a screen works.

## Backend

| Area | Path | Status | Evidence / notes |
|---|---|---|---|
| Authentication | `api/auth.py` | **Broken / unsafe** | Token is `token-{user.id}` (guessable, not signed). No route validates it. `/auth/me` returns the first user in the DB. Hardcoded `admin123` fallback login. Passwords hashed with unsalted SHA-256 (`database.py`). |
| Tenant isolation on API routes | `api/*.py` | **Broken / unsafe** | Routes query by ID without an `organization_id` filter (e.g. `agents.py:146`, `calls.py:203`). Several fall back to `db.query(Organization).first()`. Isolation is only enforced inside the voice session and RAG search. |
| Telephony credential config | `api/telephony.py` `/config` | **Broken / unsafe** | Unauthenticated endpoint writes Twilio/Exotel credentials into `.env` files and silently swallows write errors. |
| Twilio webhook signature verification | `telephony/twilio_security.py` | **Partial** | Functions are unit-tested, but **no API route calls them**. Webhooks currently accept unsigned requests. |
| CORS | `main.py` | **Broken / unsafe** | `allow_origins=["*"]` with `allow_credentials=True`. |
| Outbound call creation (Twilio) | `telephony/twilio_provider.py` | Code present; the user reported one trial call was accepted | Provider acceptance does not prove the conversation path works. |
| TwiML turn-by-turn conversation | `api/telephony.py` | Verified (automated, mocked) / Blocked (live) | Tests generate and parse TwiML. Not run against a live call in this audit. |
| WebSocket media stream | `api/ws_voice.py` | Code present, unverified | mu-law ↔ PCM conversion is tested; no live stream test. |
| Exotel | `telephony/exotel_provider.py` | Code present, unverified | No credentials. |
| Belief state / slot tracking | `voice/belief_state.py` | Verified (automated) | Rule-based extraction for fixed domain templates. Tests use English utterances; multilingual tests only check that a clarification string longer than 15 characters exists. |
| Tool runtime | `voice/tool_runtime.py` | Verified (automated) for listed tools | Tools: order status, COD confirm/cancel, address change, slot check, book/reschedule/cancel appointment, EMI calculation, WhatsApp dispatch. Idempotency key = SHA-256 of args. Tools are triggered by keyword rules, not LLM function calling. WhatsApp dispatch: not verified that a message is actually sent. |
| Call-3I scenario suite | `voice/call_3i_benchmark.py` | Verified (automated) | 18 scripted scenarios run against the rule-based engine. |
| Fallback conversation engine | `ai/llm_providers.py` `DynamicConversationalEngine` | Partial | Hardcoded canned replies per industry, containing fixed prices and claims. Used whenever no LLM key is configured. One canned reply says callers "think they're speaking with a top human SDR". That conflicts with the AI-disclosure requirement. |
| Real LLM providers | `ai/llm_providers.py` | Blocked | No API keys configured in `.env`. |
| STT | `ai/stt_providers.py` | Blocked | Default is `mock`; no keys. |
| TTS | `ai/tts_providers.py` | Code present, unverified | Edge-TTS needs network access. Audio quality has not been assessed by listeners. |
| Language detection | `voice/language_detector.py` | Verified (automated, small set) | 5 tests. |
| Knowledge ingestion | `knowledge/ingestion_pipeline.py` | Verified (automated) | SSRF blocking and prompt-injection sanitising are tested. |
| Retrieval | `knowledge/rag_engine.py` | Partial | Token-overlap similarity only. No embeddings, no BM25. Tenant-scoped. |
| Campaign dialer | `api/campaigns.py` | **Missing** | `start` only sets `status="running"`. No calls are placed, no worker, no retries, no DNC check. |
| Speed-to-lead | `api/leads.py` | Partial | `/simulate` endpoint; `response_time_seconds` defaults to a fixed `4.2`. |
| Seed data | `database.py` | Demo data | Seeds organisation, admin user and 6 agents. Real-looking brand names (e.g. real estate developers) appear in seed prompts. Review for IP and accuracy. |

## Frontend

The pages compile. **Each page's controls have not yet been traced to backend behaviour**, so none is marked verified. Known from the backend audit above:

- *Campaigns & Dialer*: the "start" control cannot dial, because the backend does not dial.
- *Login / tenant context*: no real session, because the backend auth is not real.
- *Analytics*: still to be checked for hardcoded or derived numbers (Stage 1b).

## Legacy artefacts

- Three legacy SQLite files in the repo root (all `*.db` other than `stratum.db`) are old local databases. They are git-ignored and contain old branding. Do not delete them without approval.
