# STRATUM AI — PRODUCTION GAP ANALYSIS

**Revision:** 1.1 (replaces 1.0; 1.0 contained unverified claims and invented effort/latency figures)
**Date:** 2026-10-30

Effort estimates and latency targets are deliberately omitted until they can be measured.

## Release blockers (critical)

1. **No real authentication.** Unsigned guessable tokens, no route protection, hardcoded fallback password, unsalted SHA-256 hashing.
2. **No tenant isolation at the API layer.** Any caller can read or modify any tenant's agents, calls, leads and campaigns by ID.
3. **Unauthenticated credential-write endpoint** (`POST /api/telephony/config` writes carrier secrets to `.env`).
4. **Carrier webhooks are not signature-verified.** Verification code exists but is unused.
5. **CORS wildcard with credentials.**
6. **AI disclosure conflict.** A canned reply implies callers believe they are talking to a human.

## Major functional gaps

7. **Campaign dialer does not dial.** Needs a durable worker, concurrency limits, calling windows, retries, DNC/opt-out suppression and consent checks.
8. **No real LLM/STT configured.** The conversation path in normal use is the rule-based fallback with canned, industry-specific claims (prices, rates). This risks the agent stating unverified facts.
9. **Tools are keyword-triggered**, not chosen by a policy/LLM with schema-validated arguments.
10. **Retrieval is keyword overlap only.** No semantic search, no relevance threshold documented.
11. **No live end-to-end call has been validated** (TwiML or WebSocket) in this audit.
12. **Analytics and cost figures:** not yet checked for hardcoded or estimated values (e.g. `response_time_seconds=4.2` default).
13. **No migrations.** Schema is created with `create_all` on startup.

## Brand / IP

14. Competitor product references were in code, comments and README. **Resolved in Stage 2.** Third-party vendors that Stratum integrates with (Twilio, Exotel, Sarvam, ElevenLabs, Deepgram, Groq, OpenAI, Microsoft Edge TTS) are still named where the integration needs it.
15. Seed agent prompts reference real third-party company/brand names. These need review.

## Requires external resources

| Need | For |
|---|---|
| LLM API key (e.g. Groq/OpenAI) | Real conversation generation |
| STT key (Deepgram/Sarvam) | Real speech recognition |
| Public HTTPS endpoint | Any live carrier call |
| Upgraded carrier account | Unrestricted outbound / media streams |
| Human listeners per language | Voice and language quality sign-off |
