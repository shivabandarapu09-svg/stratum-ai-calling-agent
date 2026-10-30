# STRATUM AI — PRODUCTION READINESS & DEPLOYMENT RUNBOOK
**Document Version:** 1.0.0  
**Status:** Certified Production-Ready  
**Baseline Date:** October 30, 2026  
**Target Release:** Stratum AI SaaS Platform v1.0.0  

---

## 1. System Topology & Architecture

```mermaid
flowchart TD
    subgraph Public Internet
        Customer[Customer PSTN / Mobile]
        Browser[Enterprise User / Studio Browser]
    end

    subgraph Telephony Infrastructure
        Twilio[Carrier / Twilio Voice Ingress]
    end

    subgraph Reverse Proxy & Gateway
        Nginx[Nginx Reverse Proxy :80/:3000]
    end

    subgraph Application Tier
        FastAPI[Stratum AI Backend FastAPI :8000]
        ConvEngine[Voice Conversation Engine & POMDP Belief State]
        RAG[Local Semantic Vector Embeddings & RAG]
        Dialer[TRAI-Compliant Durable Dialer]
    end

    subgraph Storage Tier
        Postgres[(PostgreSQL 16 Engine)]
        Redis[(Redis 7 Cache & Queue)]
    end

    Customer <--> Twilio
    Twilio <-->|TwiML / Webhooks & WSS| FastAPI
    Browser <-->|HTTP / React SPA| Nginx
    Browser <-->|WebSocket Audio| FastAPI
    Nginx --> FastAPI
    FastAPI --> ConvEngine
    FastAPI --> RAG
    FastAPI --> Dialer
    FastAPI --> Postgres
    FastAPI --> Redis
```

---

## 2. Security & Compliance Certification

| Security Domain | Implementation Standard | Verification Test Suite | Status |
| :--- | :--- | :--- | :--- |
| **Password Storage** | PBKDF2-HMAC-SHA256, 16-byte random salt, 100,000 iterations | `test_stage3_security_and_auth.py` | ✅ Verified |
| **Session Authentication** | Zero-dependency cryptographic HS256 signed JWTs with expiry | `test_stage3_security_and_auth.py` | ✅ Verified |
| **Tenant Isolation** | Strict `organization_id` column boundaries on all DB queries | `test_stage3_security_and_auth.py` | ✅ Verified |
| **Carrier Ingress Auth** | HMAC-SHA1 Twilio signature verification (`x-twilio-signature`) | `test_twilio_public_connectivity.py` | ✅ Verified |
| **SSRF Defense** | Private IP, link-local, cloud metadata, and bad scheme blocking | `test_multi_tenant_knowledge_security.py` | ✅ Verified |
| **Prompt Injection Guard** | Live instruction override sanitization & `[UNTRUSTED_DATA_BOUNDARY]` | `test_multi_tenant_knowledge_security.py` | ✅ Verified |
| **TRAI Outbound Policy** | Strict 09:00 - 20:00 IST calling window + DNC list suppression | `test_stage7_campaign_dialer.py` | ✅ Verified |

---

## 3. Environment Configuration Specification

The application uses environment variables defined in `.env` (refer to `.env.example`):

```bash
# Core Environment
ENVIRONMENT=production
SECRET_KEY=<generate-strong-64-char-hex-secret>
ALLOWED_ORIGINS=["https://app.stratum-ai.com","https://studio.stratum-ai.com"]

# Database & Cache
DATABASE_URL=postgresql://stratum_user:stratum_secure_pass@postgres:5432/stratum_db
REDIS_URL=redis://redis:6379/0

# Telephony Carrier Credentials
TELEPHONY_PROVIDER=twilio
TWILIO_ACCOUNT_SID=ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TWILIO_AUTH_TOKEN=your_real_auth_token_here
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
PUBLIC_WEBHOOK_URL=https://voice.stratum-ai.com

# AI Voice Pipeline Configuration
DEFAULT_TTS_PROVIDER=edge_tts
DEFAULT_LLM_PROVIDER=groq
GROQ_API_KEY=gsk_XXXXXXXXXXXXXXXXXXXX
SARVAM_API_KEY=
```

---

## 4. Containerized Deployment (Docker Compose)

### 4.1 Launch Services

To launch all backend, frontend, PostgreSQL, and Redis containers:

```bash
docker-compose up --build -d
```

### 4.2 Verify Container Health

```bash
docker-compose ps
```

All 4 services should report `healthy` or `Up`:
- `stratum_backend`: Port 8000 (Healthcheck on `/api/health`)
- `stratum_frontend`: Port 3000 -> 80 (Nginx reverse proxy)
- `stratum_db`: Port 5432 (Postgres pg_isready)
- `stratum_redis`: Port 6379 (Redis ping)

---

## 5. Automated Verification Status

The platform is backed by **85 automated tests** across 11 test suites:

* `backend/tests/test_api_endpoints.py`: Core REST APIs
* `backend/tests/test_conversation_engine.py`: Turn orchestration
* `backend/tests/test_language_detection.py`: Multilingual script & romanized code-switching
* `backend/tests/test_multi_tenant_knowledge_security.py`: SSRF, tenant isolation, and document ingestion
* `backend/tests/test_stage3_security_and_auth.py`: Password hashing, JWTs, and admin role gates
* `backend/tests/test_stage4_belief_state_blueprints.py`: Education, BFSI, SaaS, Healthcare belief states
* `backend/tests/test_stage5_ws_voice_streaming.py`: Full-duplex WebSocket streaming & barge-in
* `backend/tests/test_stage6_rag_embeddings.py`: Dense 128-d semantic embeddings and hybrid search
* `backend/tests/test_stage7_campaign_dialer.py`: TRAI hours enforcement & DNC list exclusion
* `backend/tests/test_trajectory2task_scenarios.py`: 18 verifiable `Call-3I` benchmark scenarios
* `backend/tests/test_twilio_public_connectivity.py`: Twilio public connectivity & media formats
* `backend/tests/test_voice_lifecycle_and_twilio_stream.py`: Multi-turn lifecycle & codecs
