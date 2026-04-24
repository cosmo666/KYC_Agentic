# KYC_Agentic — Project Context for Claude

## What this project is

The **Conversational KYC Assistant with Agentic Workflow** — a working Proof of Concept that lets Indian users complete a Know Your Customer (KYC) check by **chatting with an assistant** instead of filling out a multi-step form. The assistant talks to the user in **Hindi or English**, walks them through document upload and selfie capture one step at a time, and runs the verification silently in the background through an agentic pipeline.

This is **Swarnima Negi's B.Tech internship project at Ramrao Adik Institute of Technology** (RAIT), supervised by Dr. Vishakha K. Gaikwad. The full report — `Conversational_KYC_Internship_Report (1).docx` at the project root — is the canonical source of intent, motivation, and roadmap.

## Important: report vs. code

The report describes the *intended* architecture. The repo today is a simpler MVP. When recommending changes, ground them in **what's actually in the code**, not what the report says exists. Specific divergences:

| Report claims | Code reality |
|---|---|
| LangGraph agentic workflow | Hand-rolled ordered list of pure functions over a `KYCState` dataclass — same shape, no `langgraph` dependency |
| Gemini Vision for OCR | Local Ollama (`gemma3:4b-cloud`) for both OCR and chat |
| PostgreSQL data layer | No database yet — uploads sit in `backend/uploads/` |
| RAG pipeline grounded on compliance docs | Plain Ollama chat with a KYC system prompt |
| shadcn/ui frontend | Plain Create React App + hand-CSS |
| MediaPipe liveness, gender/age, TTS, admin module | Roadmap items, not implemented |

These gaps are **intentional and acknowledged in the report's "future work" section**. The POC stops at the demonstrable end-to-end flow.

## End-to-end flow (current)

1. **Greeting / chat** — assistant introduces KYC in plain language, bilingual.
2. **Document upload** — Aadhaar then PAN, drag-and-drop or file picker.
3. **Vision OCR** — Ollama vision model extracts name, DOB, doc number, address, gender → `ExtractedData`.
4. **Selfie capture** — webcam in the browser.
5. **Face verification** — DeepFace (VGG-Face) compares selfie ↔ document photo, returns confidence.
6. **Cross-validation** — Jaccard name match + exact DOB match + doc-type check + OCR-confidence check, weighted-scored.
7. **Decision** — `approved` / `flagged` / `rejected` / `incomplete`, with flags (for reviewers) and recommendations (for the user).

## Stack

- **Frontend**: React 19 (Create React App), single-file `kyc-frontend/src/App.js`. Plain CSS. Webcam via native `getUserMedia`.
- **Backend**: Python 3.11+, FastAPI on port `9090`, Uvicorn.
- **AI**: Ollama (`gemma3:4b-cloud`) for vision OCR and chat; DeepFace for face match; Tesseract as the offline OCR fallback.
- **Storage**: filesystem (`backend/uploads/`); no DB yet.

## Repo layout

```text
KYC_Agentic/
├── backend/                            # FastAPI service
│   ├── main.py                         # App, CORS, routers, /upload-doc legacy alias
│   ├── config.py                       # .env loading
│   ├── routers/  documents.py, chat.py, face.py, validation.py
│   ├── services/ ocr_service.py, chat_service.py, face_service.py,
│   │             validation_service.py, workflow_service.py
│   ├── models/   schemas.py, chat_schemas.py
│   └── uploads/                        # File storage; gitignored
├── kyc-frontend/                       # React 19 SPA
│   └── src/App.js                      # Whole UI lives here for the POC
├── .claude/
│   ├── rules/
│   │   ├── python-fastapi-backend.md   # Backend conventions
│   │   ├── react-frontend.md           # Frontend conventions
│   │   └── agentic-workflow.md         # Workflow / decision-policy conventions
│   └── skills/kyc-domain/SKILL.md      # Indian KYC regulatory + Aadhaar/PAN domain
├── Conversational_KYC_Internship_Report (1).docx
├── CLAUDE.md                           # ← this file
└── README.md
```

## Conventions — read these before touching code

The rules in `.claude/rules/` are the working agreements. Brief pointers:

- **`python-fastapi-backend.md`** — router/service split, OCR fallback chain, lazy DeepFace import, Aadhaar masking, no DB.
- **`react-frontend.md`** — single-file SPA today; split when it crosses ~600 lines; webcam stream cleanup; `API_URL` should read from env.
- **`agentic-workflow.md`** — how to add a node, decision thresholds, validation weights, audit replay.
- **`.claude/skills/kyc-domain/SKILL.md`** — Aadhaar/PAN format rules, RBI compliance touchpoints, conversational tone rules.

## Coding style

- **Plain over clever** — the report's audience includes non-experts; the code should read the same way.
- **Comments explain *why*, not *what*** — well-named functions document themselves.
- **Files under ~300 lines**; split when they grow past that. The single-file `App.js` is a known exception flagged for splitting.
- **Never log or persist unmasked PII** — Aadhaar numbers must be masked (`XXXX XXXX 1234`) before storage or display, per UIDAI rules.
- **Never break the user's flow on a backend error** — surface a friendly message + a recovery action (retake photo, re-upload, etc.).

## Running the project

See the project root `README.md` for setup, environment variables, and the dev loop.

## Things to flag before merging

- New dependencies in `backend/requirements.txt` or `kyc-frontend/package.json` — keep the surface small.
- Anything that changes the workflow node order or decision thresholds — these encode the project's risk policy.
- Any new field in `ExtractedData` that the FE will display — verify the FE actually renders it.
- Anything that writes to disk outside `backend/uploads/`.
- Anything that touches PII handling (storage, display, logging).
