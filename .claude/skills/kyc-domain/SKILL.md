---
name: kyc-domain
description: Indian KYC (Know Your Customer) domain knowledge for the Conversational KYC Assistant. Use when implementing document extraction, field validation, decision logic, regulatory compliance handling, or any UI/copy that touches Aadhaar, PAN, or related identity-verification flows.
---

# KYC Domain Knowledge

## What KYC is

**KYC = Know Your Customer.** Every regulated financial entity in India — banks, NBFCs, mutual funds, insurance companies, telecoms — must verify a customer's identity before opening an account or selling a product. The legal basis is the **Prevention of Money Laundering Act, 2002 (PMLA)**, with operational rules in the **RBI Master Direction on KYC, 2016** (and amendments).

The point of KYC is to keep fraud, money laundering, and terrorist financing out of the formal financial system. From a customer's perspective, KYC is the paperwork between them and a new account.

## How KYC has evolved

| Mode | What it looks like | Pain point |
|---|---|---|
| **Paper-based** | Walk into a branch with photocopies of Aadhaar / PAN / utility bill / passport photo. A clerk verifies originals, types fields, files documents. | Slow (days–weeks), manual, error-prone, expensive to store. |
| **eKYC** | Upload documents through a web/mobile app. Backend OCRs, matches a selfie, runs basic checks. | Multi-step forms with no guidance — high abandonment, especially for first-time users and non-English speakers. |
| **Video KYC** | A live video call with a bank agent. | Requires bandwidth, an available agent, and the user understanding the flow. |

This project targets the **eKYC** experience and replaces the form-driven UI with a guided **chat assistant** so users in rural / semi-urban India and Hindi-first speakers don't drop out mid-flow.

## Documents the assistant handles

### Aadhaar (UIDAI)

- 12-digit unique identifier, issued by the **Unique Identification Authority of India (UIDAI)**.
- Carries: **name, DOB, gender, address, photo, Aadhaar number**, and a QR code.
- Bilingual layout (English + a regional language — Hindi for north India, others vary).
- **Mask the first 8 digits** before storing or displaying (`XXXX XXXX 1234`). This is non-negotiable per UIDAI rules — `AADHAAR_PROMPT` in `apps/api/app/agents/intake.py` instructs the vision model to mask, and `mask_aadhaar()` in the same module re-applies the mask after extraction. `apps/api/app/routers/confirm.py` re-masks again on confirm in case the user un-masked during edit. Don't let an unmasked number reach Postgres or the FE.
- Common variants: original printed Aadhaar, e-Aadhaar PDF, mAadhaar QR, plastic card.

### PAN (Permanent Account Number)

- 10-character alphanumeric ID issued by the **Income Tax Department**.
- Format: **5 letters + 4 digits + 1 letter** (regex `[A-Z]{5}[0-9]{4}[A-Z]`).
  - 4th letter encodes entity type (`P` = individual, `C` = company, `H` = HUF, etc. — assistant assumes `P`).
- Carries: **name, father's name, DOB, PAN number, photo**.
- Single language (English).
- The PAN photograph is often older / lower quality than a recent selfie — face-match thresholds need to tolerate this.

### Other identity documents (roadmap)

The report mentions support for additional documents (passport, driver's licence, voter ID) is on the roadmap. They are not yet implemented. When added:

- **Passport**: machine-readable zone (MRZ) is reliable; the photo page is the input.
- **Driver's Licence**: state-issued, format varies — vision-based extraction is required, regex won't work.
- **Voter ID (EPIC)**: text quality is poor on older cards; expect lower OCR confidence.

## Cross-document validation rules

When a user submits both Aadhaar and PAN, the assistant cross-validates:

| Field | Rule | Weight in score |
|---|---|---|
| **Full name** | Jaccard similarity ≥ 0.75 → pass; 0.50–0.75 → warn (spelling variant); < 0.50 → fail | 0.5 |
| **Date of birth** | Exact match after normalising to `DD/MM/YYYY` | 0.3 |
| **Document types** | Both correctly classified (Aadhaar + PAN) | 0.1 |
| **OCR confidence** | Average of per-document confidence (`high`=1.0, `medium`=0.6, `low`=0.2) | 0.1 |

Realistic edge cases the validator must handle:

- **Initials vs full names**: Aadhaar shows `Rajesh Kumar Sharma`, PAN shows `R K Sharma` — Jaccard catches the partial overlap.
- **Honorifics**: `Smt. Geeta Devi` vs `Geeta Devi` — `normalize_name` in `apps/api/app/agents/validation.py` strips Indian titles (`mr`, `mrs`, `ms`, `miss`, `dr`, `shri`, `smt`, `km`, `kumari`, plus Devanagari `श्री`, `श्रीमती`, `श्रीमान`, `कुमारी`, `कुमार`).
- **Hindi vs English transliteration**: Aadhaar in both scripts; OCR returns the English line. Mismatched transliterations (`Krishan` vs `Krishna`) typically trigger a `warn`.
- **DOB formats**: Aadhaar shows `DD/MM/YYYY`; PAN sometimes shows `DD-MM-YYYY`. `normalize_dob` accepts both plus `YYYY-MM-DD` and `DD MM YYYY`.

## Face verification

- **Selfie ↔ document photo** comparison via DeepFace VGG-Face, cosine distance, default threshold ~0.40.
- Confidence is derived as `(1 - distance / threshold) * 100`, clamped 0–100.
- **Confidence bands** the UI surfaces:
  - ≥ 80 → "Strong match", proceed
  - 60–79 → "Likely match", proceed with caution (counts as `face_ok` in the workflow)
  - < 60 → "Weak match", manual review
- Failure modes the assistant must handle gracefully:
  - **No face detected** in the selfie (user too far / off-angle) — ask for a retake, don't 500.
  - **No face detected on the document** (photo region too small / low resolution) — common with very old PAN cards; ask for a clearer document image.
  - **Two faces in the selfie** — currently DeepFace picks the largest; consider rejecting in future.

## Liveness (planned, not implemented)

Today, a printed photograph or a short video clip can pass the face match. The report identifies this as a real risk and proposes **MediaPipe Face Mesh** for liveness:

- Track facial landmarks across frames during selfie capture.
- Require natural micro-movements (blinks, head tilt) that are hard to fake with a static photo.
- Fail liveness → force `rejected`, not `flagged`. (This is stricter than face mismatch on purpose.)

## Decision policy

Every KYC case ends in one of three decisions in the current code (`incomplete` was a fourth value in the previous MVP and is no longer emitted — incomplete cases keep the user on the relevant `wait_for_*` step instead of terminating).

| Decision | Meaning | What happens next |
|---|---|---|
| **`approved`** | Score ≥ 80 AND face_ok | Account opens / product activates |
| **`flagged`** | Borderline — score 60–79, or score 40–59 with no critical fails | Goes to a human KYC officer |
| **`rejected`** | Country gate failed, critical name/DOB mismatch, no face detected, or score below the borderline band | User asked to re-submit / contact support |

The full gate order is encoded in `apps/api/app/agents/decision.py:compute_decision`. The **country gate is applied first** — a non-IN IP rejects the case before the score-band logic runs (this can also be pre-set from `geolocation.py` so the user gets the country-rejection reason rather than a generic threshold message).

**Why this matters**: a `flagged` case is *not a denial* — it's a routing decision. The UI copy should make this clear. A `rejected` case might still be recoverable with a clearer photo, so the recommendations should explain that.

## RBI compliance touchpoints

If you change anything that touches PII storage, retention, or display, check against:

- **RBI Master Direction on KYC, 2016** (and amendments) — defines acceptable KYC modes, periodic re-KYC requirements, OVD (Officially Valid Document) list.
- **PMLA, 2002** — record retention (5 years from end of relationship).
- **UIDAI rules** — Aadhaar masking is mandatory for storage and display.
- **DPDP Act, 2023** — purpose limitation, consent, breach notification.

The current POC does not implement record retention or audit logging at the depth a real deployment needs — both are roadmap items.

## Conversational design rules

The assistant's tone (per `_REPLY_PROMPT` and `_INTENT_PROMPT` in `apps/api/app/agents/orchestrator.py`):

- **Bilingual by default** — Hindi or English, decided by the user's first message.
- **One thing at a time** — never ask for two pieces of information in one prompt.
- **Plain language** — no banking jargon ("OVD", "video PD") unless the user asks.
- **Never ask for sensitive info in chat** — Aadhaar number, PAN number, full address. These come from the document upload, not from the user typing them.
- **Redirect off-topic** politely but firmly — the assistant is not a general chatbot.
- **Keep responses ≤ 3 sentences** unless explaining something complex.

## Error messages users actually see

The system surfaces user-friendly messages, not technical errors. Examples already in the codebase:

- `"❌ Faces do not match (52% confidence). Please try again with a clearer photo."`
- `"Could not detect a face in one or both images. Please upload a clearer photo."`
- `"⚠️ Low face-match confidence (55%)"` (flag, not a hard fail)
- `"Please re-upload your Aadhaar card"` (incomplete)

When adding new error states, **always pair the technical reason (logged) with a user action (shown)** — never leave the user staring at a stack trace.

## Glossary

| Term | Meaning |
|---|---|
| **OVD** | Officially Valid Document — the RBI-approved list (Aadhaar, PAN, passport, driving licence, voter ID, NREGA card) |
| **Re-KYC** | Periodic re-verification — RBI requires every 2/8/10 years depending on risk category |
| **CKYC** | Central KYC Records Registry — a shared registry to avoid repeat KYC across institutions |
| **Video KYC / VCIP** | Video-based Customer Identification Process — RBI-permitted live video verification |
| **PEP** | Politically Exposed Person — flagged for enhanced due diligence |
| **STR / SAR** | Suspicious Transaction Report / Suspicious Activity Report — filed with FIU-IND when fraud is suspected |
