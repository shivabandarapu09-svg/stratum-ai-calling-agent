# Stratum AI — Hyper-Realistic Multilingual AI Calling Agent Platform

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-cyan.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue.svg)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-3.4-indigo.svg)](https://tailwindcss.com)

**Stratum AI** (`stratum`) is a multilingual AI calling platform for configuring, testing and operating AI voice agents for business workflows.

> Capability statements below describe what the code is designed to do. See `docs/engineering/EXISTING_FEATURE_AUDIT.md` for what has actually been verified.

---

## 🌟 Stratum AI Architecture Layers

| Architectural Layer | Stratum AI Implementation |
|---|---|
| **Acoustic Realism** | Browser soundscape playback, conversational fillers, and barge-in handling. |
| **Indic Language Handling** | Hinglish, Tenglish, Tanglish and Indian English code-switching detection with configurable speech rate and pitch. |
| **Voice Pipeline & Tool Use** | Mid-call tool execution through the Stratum tool runtime (appointments, CRM updates, follow-ups, human handoff). |
| **Conversational Stage Framework** | Five-stage conversation state machine (**1. Hook & Rapport → 2. Need Discovery → 3. Grounded Value Pitch → 4. Objection Resolution → 5. Action & Commitment**). |
| **India Telephony & Compliance** | Exotel and Twilio carrier adapters, configurable TRAI 9 AM – 8 PM calling windows, and lead-source webhooks. |
| **Speed-to-Lead & BANT** | Webhook-triggered lead calling, BANT qualification tracking, and 6 industry agent templates. |

---

## 🚀 6 Pre-Trained Stratum AI Employees

1. **Aarav — Luxury Real Estate Advisor (`real_estate`)**
   - Speaks warm, colloquial Hinglish/English to qualify homebuyers for 3 & 4 BHK residences (₹2.15 Cr+).
   - Handles pricing objections with Financial District rental yields (7–8%), dispatches floor plans on WhatsApp mid-call, and books weekend VIP site visits.
2. **Priya — Healthcare & Clinic Patient Coordinator (`clinic_healthcare`)**
   - Empathetic 24/7 patient triage, specialist doctor selection (Cardiology, Ortho, Pediatrics), and zero-wait WhatsApp clinic token passes.
3. **Rohan — EdTech & Executive Admissions Mentor (`education_admissions`)**
   - Screens working professionals for IIT-partnered GenAI programs, calculates ₹50,000 early-bird scholarships + no-cost EMI, and schedules faculty evaluation calls.
4. **Neha — E-Commerce COD & RTO Reducer (`ecommerce_cod`)**
   - Verifies Cash on Delivery orders, confirms delivery pin codes, and pitches flat ₹150 instant UPI prepaid discounts on WhatsApp.
5. **Kavya — Stratum B2B Speed-to-Lead SDR (`b2b_saas_sdr`)**
   - Dials inbound marketing & sales leaders in under 5 seconds, discovers monthly call volume and CRM stack, and locks live 20-minute architecture demos.
6. **Kabir — BFSI & FinTech Credit Advisor (`bfsi_fintech`)**
   - Qualifies pre-approved ₹25L working capital and credit lines at 10.75% p.a. and dispatches zero-foreclosure digital sanction letters.

---

## 🛠️ Quickstart: Running Stratum AI Locally

### 1. Start the FastAPI Backend Server
```powershell
.\backend\venv\Scripts\activate
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
- API Documentation (Swagger): `http://127.0.0.1:8000/docs`
- Health Endpoint: `http://127.0.0.1:8000/api/health`

### 2. Start the React Frontend Studio
```powershell
npm.cmd --prefix frontend run dev
```
Open **`http://localhost:3000`** in your browser.

### 3. Run Automated Test Suite
```powershell
$env:PYTHONPATH="backend"
.\backend\venv\Scripts\python.exe -m pytest backend/tests -v
```
