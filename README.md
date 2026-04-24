# Conversational KYC Assistant with Agentic Workflow

A guided, chat-based Know Your Customer (KYC) assistant for Indian users. Instead of a multi-step web form, users **talk to an assistant in Hindi or English** that walks them through document upload, selfie capture, and verification one step at a time. Under the hood, an agentic backend reads identity documents with a vision model, matches the selfie against the document photo, cross-validates fields, and produces a final decision.

> Internship Proof of Concept — Swarnima Negi, B.Tech Computer Engineering, Ramrao Adik Institute of Technology (RAIT), under D. Y. Patil Deemed to be University. Supervised by Dr. Vishakha K. Gaikwad. Full report: [`Conversational_KYC_Internship_Report (1).docx`](Conversational_KYC_Internship_Report%20(1).docx).

---

## Why this exists

KYC has come a long way from paper photocopies to eKYC and Video KYC, but the user experience hasn't kept up. Today's digital KYC flows are stiff multi-step forms with no real-time guidance — and abandonment is high, especially in rural / semi-urban India and among users who don't speak English comfortably.

This project replaces the form with a **conversation**. The assistant explains what's happening at every step, asks for one thing at a time, and adapts to what the user does — re-asking for a blurred document, requesting a fresh selfie if the face doesn't match, or routing borderline cases to a human reviewer.

---

## What it does (today)

- **Bilingual chat assistant** (Hindi + English) that guides the user through KYC.
- **Vision-based document OCR** for Aadhaar and PAN cards (handles stamps, logos, mixed-script text — areas where classical OCR struggles).
- **Selfie ↔ document face match** via DeepFace.
- **Cross-validation** of name and date of birth across submitted documents.
- **Agentic decision pipeline** that produces one of `approved`, `flagged` (for human review), `rejected`, or `incomplete`, with user-facing recommendations on what to do next.

## On the roadmap (per the report)

- **Admin module** for human review of `flagged` cases.
- **Liveness detection** with MediaPipe Face Mesh — to defeat printed-photo / video-replay spoofs.
- **Gender and age estimation** from the selfie, cross-checked against the DOB on the document.
- **Text-to-Speech (TTS)** for users who'd rather listen than read.
- **Retrieval-Augmented Generation (RAG)** over compliance documents so the assistant can answer KYC policy questions accurately.
- **PostgreSQL** persistence for user records, document references, and audit logs.
- **Wider document support** (passport, driving licence, voter ID).

---

## Architecture

```text
┌──────────────────┐         ┌──────────────────────┐
│  React Frontend  │  HTTPS  │   FastAPI Backend    │
│  (chat, upload,  │ ◄─────► │  /chat  /documents   │
│   webcam, view)  │         │  /verify-face        │
└──────────────────┘         │  /validate           │
                             └──────────┬───────────┘
                                        │
       ┌────────────────────────────────┼────────────────────────┐
       │                                │                        │
       ▼                                ▼                        ▼
┌───────────────┐          ┌────────────────────┐    ┌───────────────────────┐
│ Ollama Vision │          │  DeepFace          │    │ Agentic Workflow      │
│ gemma3:4b-    │          │  (VGG-Face,        │    │ classify → complete   │
│ cloud         │          │   cosine match)    │    │ → cross_validate      │
│ (OCR + chat)  │          │                    │    │ → evaluate_face       │
└──────┬────────┘          └────────────────────┘    │ → make_decision       │
       │                                              └───────────┬───────────┘
       ▼                                                          │
┌───────────────┐                                                 ▼
│  Tesseract    │                                       ┌──────────────────┐
│  (offline     │                                       │  Decision +      │
│   fallback)   │                                       │  flags +         │
└───────────────┘                                       │  recommendations │
                                                        └──────────────────┘
```

| Layer | What it does | Where in the repo |
|---|---|---|
| **Frontend** | Chat panel, drag-drop document upload, webcam selfie, verdict view | [`kyc-frontend/src/App.js`](kyc-frontend/src/App.js) |
| **API** | FastAPI on `:9090` — request validation, file handling, routing to services | [`backend/main.py`](backend/main.py), [`backend/routers/`](backend/routers/) |
| **Vision OCR** | Ollama `gemma3:4b-cloud` (primary), Tesseract regex (offline fallback) | [`backend/services/ocr_service.py`](backend/services/ocr_service.py) |
| **Chat** | Same Ollama model with a KYC-tuned system prompt | [`backend/services/chat_service.py`](backend/services/chat_service.py) |
| **Face match** | DeepFace VGG-Face, cosine distance, distance → confidence | [`backend/services/face_service.py`](backend/services/face_service.py) |
| **Cross-validation** | Jaccard name match + DOB exact match + doc-type + OCR confidence, weighted | [`backend/services/validation_service.py`](backend/services/validation_service.py) |
| **Agentic workflow** | 5-node ordered pipeline producing the final decision | [`backend/services/workflow_service.py`](backend/services/workflow_service.py) |

---

## Tech stack

- **Frontend**: React 19, Create React App, plain CSS, native `getUserMedia` for the webcam
- **Backend**: Python 3.11+, FastAPI, Uvicorn, Pydantic v2
- **AI / ML**: Ollama (local, runs `gemma3:4b-cloud`), DeepFace (VGG-Face), Tesseract OCR
- **Storage (POC)**: filesystem under `backend/uploads/` (no database yet)

---

## Getting started

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** (React 19 needs a recent Node)
- **Ollama** installed and running locally — pull the model first:
  ```bash
  ollama pull gemma3:4b-cloud
  ```
- **Tesseract OCR** (optional fallback) — Windows installer puts it at `C:\Program Files\Tesseract-OCR\tesseract.exe`, which is what `backend/config.py` expects.
- A C++ toolchain if you're installing DeepFace from scratch on Windows (TensorFlow dependency).

### Backend

```bash
cd backend
python -m venv ../venv
../venv/Scripts/activate                # Windows
# source ../venv/bin/activate           # macOS / Linux

pip install -r requirements.txt
pip install deepface ollama             # not in requirements.txt yet

cp .env.example .env                    # adjust if needed

python main.py                          # serves on http://127.0.0.1:9090
# Swagger UI:  http://127.0.0.1:9090/docs
```

### Frontend

```bash
cd kyc-frontend
npm install
npm start                               # serves on http://localhost:3000
```

> **Heads up**: `kyc-frontend/src/App.js` currently hardcodes `API_URL = "http://127.0.0.1:8888"` — the backend actually runs on `9090`. Update the constant (or wire it through `process.env.REACT_APP_API_URL`) before the frontend will talk to the backend.

### Environment variables

`backend/.env`:

```env
PORT=9090
UPLOAD_FOLDER=uploads
GEMINI_API_KEY=                         # legacy, no longer used
```

---

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/`             | Health check |
| `POST` | `/upload-doc`   | Upload a document (legacy alias kept for the React frontend) |
| `POST` | `/documents/upload` | Same as above, canonical path |
| `POST` | `/chat/`        | Chat turn — accepts message + history + optional document context |
| `POST` | `/verify-face`  | Selfie ↔ document face comparison |
| `POST` | `/validate/`    | Run the agentic workflow over uploaded documents + face result |

Full OpenAPI docs at `http://127.0.0.1:9090/docs` once the backend is running.

---

## Decision logic at a glance

| Condition | Decision | What the user sees |
|---|---|---|
| Both Aadhaar and PAN present, score ≥ 80, face match OK | `approved` | "Identity successfully verified." |
| Score 60–79, or low face confidence | `flagged` | "Application flagged for manual review (24h SLA)." |
| Critical name/DOB mismatch, or score < 60 | `rejected` | Asked to re-submit clearer photos. |
| Aadhaar or PAN missing | `incomplete` | Asked to upload the missing document. |

`face_ok = face_verified or face_confidence >= 60`. Validation weights: **Name 0.5, DOB 0.3, Doc type 0.1, OCR confidence 0.1**.

---

## Repository layout

```text
KYC_Agentic/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── routers/         documents.py, chat.py, face.py, validation.py
│   ├── services/        ocr_service.py, chat_service.py, face_service.py,
│   │                    validation_service.py, workflow_service.py
│   ├── models/          schemas.py, chat_schemas.py
│   └── uploads/         (gitignored)
├── kyc-frontend/
│   ├── src/App.js       Whole UI lives here for the POC
│   ├── src/App.css
│   └── package.json
├── .claude/             Working agreements for AI-assisted development
│   ├── rules/           python-fastapi-backend.md, react-frontend.md, agentic-workflow.md
│   └── skills/kyc-domain/SKILL.md
├── Conversational_KYC_Internship_Report (1).docx
├── CLAUDE.md
└── README.md
```

---

## Privacy and compliance notes

- **Aadhaar numbers are masked** (`XXXX XXXX 1234`) before they leave the OCR layer, per UIDAI rules. Don't unmask them anywhere downstream.
- **No PII is persisted** in this POC. Files in `backend/uploads/` are short-lived; production deployment will need RBI-compliant retention (5 years from end of relationship per PMLA, 2002).
- **The chat assistant never asks for sensitive numeric IDs** — those come from the document upload, not from the user typing.
- See [`.claude/skills/kyc-domain/SKILL.md`](.claude/skills/kyc-domain/SKILL.md) for the regulatory backdrop and the do/don't list.

---

## Testing

A formal test suite isn't in place yet. Manual checks during development cover:

- **OCR accuracy** on sample Aadhaar / PAN images (clean, blurred, rotated, mixed-script).
- **Face match** with matching, non-matching, and partially-occluded selfies.
- **Cross-validation** with deliberately mismatched names and DOBs.
- **Decision policy** at each threshold boundary.
- **End-to-end flow** through the React UI, including error paths (network down, OCR fails, no face detected).

When the test suite is added, use **pytest** for the backend (mirror `services/` and `routers/` under `backend/tests/`) and **React Testing Library** for the frontend.

---

## Contributing

Read [`CLAUDE.md`](CLAUDE.md) and the rules under [`.claude/rules/`](.claude/rules/) before making changes. Key principles:

- **Plain over clever** — the assistant has to make sense to non-developers.
- **Never log or persist unmasked PII.**
- **Surface friendly error messages** — never leave a user looking at a stack trace.
- **Don't break the workflow contract** without re-justifying the decision thresholds.
- **Keep dependencies small** — every new lib is a maintenance liability.

---

## Acknowledgements

- **Dr. Vishakha K. Gaikwad** — internship supervisor, RAIT.
- **Dr. A. V. Vidhate** — Head, Department of Computer Engineering, RAIT.
- **Dr. Mukesh D. Patil** — Principal, RAIT, D. Y. Patil Deemed to be University.
- The DeepFace, Ollama, FastAPI, and React open-source communities.

---

## References

- Lewis, P. et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* arXiv:2005.11401.
- Lugaresi, C. et al. (2019). *MediaPipe: A Framework for Building Perception Pipelines.* arXiv:1906.08172.
- Ramírez, S. (2018). *FastAPI.* https://fastapi.tiangolo.com/
- Reserve Bank of India (2016). *Master Direction on Know Your Customer (KYC) Direction, 2016.*
- Serengil, S. I. & Ozpinar, A. (2020). *LightFace: A Hybrid Deep Face Recognition Framework.* IEEE ASYU.
