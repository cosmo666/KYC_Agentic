# KYC_Agentic — Project Context for Claude

## What this project is

The **Conversational KYC Agent** — a chat-first Indian KYC (Know Your Customer) flow built as a **LangGraph multi-agent pipeline**. The user chats in Hindi or English, uploads an Aadhaar then a PAN card, takes a selfie, and gets a verdict (`approved` / `flagged` / `rejected`). Every step writes to its own Postgres table; LLM calls are observable in self-hosted Langfuse; compliance Q&A is grounded in a Qdrant RAG corpus.

Originally **Swarnima Negi's B.Tech internship project at Ramrao Adik Institute of Technology** (RAIT), supervised by Dr. Vishakha K. Gaikwad. The internship report — `Conversational_KYC_Internship_Report (1).docx` at the repo root — captures the original intent, but **the report describes the prior MVP**, not the current architecture. Treat the report as historical context; the actual code is the source of truth.

## Current status

End-to-end pipeline shipped: 6 services run via docker compose; backend pytests pass; the chat → contact form → upload (image / PDF) → confirm → selfie → verdict path is verified on the live stack with face-crop, gender match, and IP geolocation rendered on the verdict card.

## Stack (actual)

| Layer | Tech |
|---|---|
| Backend | Python 3.11, FastAPI, LangGraph (`langgraph >= 0.2.50`), LangGraph `AsyncPostgresSaver` for checkpointing, SQLAlchemy 2 async + Alembic |
| Datastores | Postgres 16 (domain tables + LangGraph checkpoints), Qdrant (RAG vectors), separate Langfuse Postgres |
| AI | Ollama on the host: chat = `gemma3:27b-cloud`, OCR (vision) = `ministral-3:14b-cloud`, embeddings = `bge-m3:latest`. Real values come from `infra/.env` via docker-compose; `apps/api/app/config.py` carries the same IDs as code defaults. Don't change pinned model IDs without coordination — see memory `feedback_model_changes`. |
| Face match | DeepFace VGG-Face (cosine), gender via DeepFace.analyze; lazy-imported to avoid TF startup cost |
| Geolocation | ipinfo.io (primary) → ipwho.is (fallback) via `ipwhois_client.py`; FE auto-discovers public IP and sends `X-Real-IP` header |
| Observability | Self-hosted Langfuse 2.x |
| Frontend | Vite 5 + React 19 + TypeScript 5 + Tailwind 3 + shadcn/ui primitives + Radix Dialog/Tooltip + react-easy-crop + zod |
| Storage | Postgres for everything domain-level; uploads on a Docker volume (`/data/uploads/<session_id>/<doc>.<ext>`) |
| Infra | Docker Compose with 6 services: `postgres`, `qdrant`, `langfuse-db`, `langfuse`, `api`, `web` |

## Repo layout

```text
KYC_Agentic/
├── apps/
│   ├── api/                              # FastAPI + LangGraph backend
│   │   ├── Dockerfile, entrypoint.sh, pyproject.toml
│   │   ├── app/
│   │   │   ├── main.py                   # App factory, lifespan (DeepFace warmup), CORS, /health, /debug/whoami
│   │   │   ├── config.py                 # pydantic-settings; .env-driven
│   │   │   ├── utils.py                  # get_client_ip() — prefers X-Real-IP header
│   │   │   ├── agents/                   # 7 specialists: orchestrator, intake, validation,
│   │   │   │                             #                biometric, geolocation, compliance, decision
│   │   │   ├── graph/                    # state.py, builder.py, checkpointer.py
│   │   │   ├── routers/                  # /chat, /upload, /confirm, /capture, /session/*, /uploads/*
│   │   │   ├── services/                 # ollama_client, deepface_runner, ipwhois_client, rag, langfuse_client
│   │   │   ├── db/                       # base, session, models (9 tables), migrations/ (Alembic)
│   │   │   ├── schemas/chat.py           # Pydantic chat I/O + Widget envelope + ContactRequest
│   │   │   └── scripts/reindex_rag.py
│   │   └── tests/                        # pytest (parsers, validation math, decision thresholds, mocks)
│   └── web/                              # Vite 5 + React 19 + TS + Tailwind + shadcn
│       ├── Dockerfile, nginx.conf, package.json
│       └── src/
│           ├── App.tsx                   # ChatShell + FaqDrawer + theme bootstrap
│           ├── api/                      # client.ts (auto-injects X-Real-IP), schemas.ts (zod)
│           ├── components/
│           │   ├── chat/                 # ChatShell, MessageList, MessageBubble, ChatInput
│           │   ├── widgets/              # ContactFormWidget, DocumentUploadWidget, EditableFieldCard,
│           │   │                         #   SelfieCamera, VerdictCard, MapPreview (react-leaflet)
│           │   ├── camera/               # CameraCaptureModal (react-easy-crop)
│           │   ├── faq/                  # FaqDrawer + FAB
│           │   └── ui/                   # shadcn primitives
│           ├── hooks/                    # useSession (cross-component sync), useClientIP (ipify discovery)
│           └── lib/utils.ts              # cn() helper
├── infra/
│   ├── docker-compose.yml                # 6 services + parameterised WEB_PORT
│   ├── .env.example                      # template — real .env is gitignored
│   ├── postgres/init.sql
│   └── rag-corpus/                       # RBI excerpts + project FAQ for the compliance agent
├── docker-compose.yml                    # Root shim → infra/docker-compose.yml (so commands work from repo root)
├── .claude/
│   ├── rules/                            # Conventions for backend, frontend, agentic workflow
│   └── skills/kyc-domain/SKILL.md        # Indian KYC domain knowledge
├── Conversational_KYC_Internship_Report (1).docx  # Historical context
├── CLAUDE.md                             # ← this file
└── README.md                             # Clone-and-run guide
```

## End-to-end flow

The flow is **agent-initiated** — the FE calls `POST /session/init` on first load, so the user lands on the assistant's greeting + contact form, not an empty chat.

1. **Bootstrap** — `App.tsx` mounts; `useClientIP()` resolves the user's public IP via `api.ipify.org` (CORS-friendly, no key) and caches it for the `X-Real-IP` header on every backend call. `ChatShell` calls `/session/init` (or `/session/{id}` if sessionStorage has a prior id).
2. **Contact form** — first agent message + a `contact_form` widget (email + mobile). User submits via `POST /session/contact`; backend validates (10-digit Indian mobile, email regex), advances state to `wait_for_name`, persists email + mobile to `sessions`.
3. **Name** — orchestrator asks for full name; user types it in chat; `n_capture_name` extracts it.
4. **Aadhaar upload** — `DocumentUploadWidget` accepts JPG / PNG / **PDF**. `POST /upload` saves the file. If PDF, `intake.py` renders the first page to PNG via `pymupdf` first. Then the LangGraph runs `intake_aadhaar`: Ollama vision OCR via `ministral-3:14b-cloud`, server-side Aadhaar number masking, and `extract_largest_face` crops the holder's photo region with DeepFace for later biometric comparison.
5. **Aadhaar confirm** — `EditableFieldCard` widget shows extracted fields (Aadhaar number is locked + re-masked on submit). `POST /confirm` saves `confirmed_json` to the `documents` row.
6. **PAN upload + confirm** — same pattern (no face crop — PAN photos are too low-res).
7. **Selfie** — `SelfieCamera` widget captures via `getUserMedia` with an oval face guide. `POST /capture` saves the file; the graph runs `biometric` (`DeepFace.verify` selfie ↔ cropped Aadhaar photo + `DeepFace.analyze` gender) → `geolocation` (ipinfo.io primary, ipwho.is fallback; uses the `X-Real-IP` value via `get_client_ip()`) → `decide`.
8. **Verdict** — `VerdictCard` shows the decision badge, both face photos side-by-side with an animated scan visual + confidence bar, gender match row, and an OpenStreetMap preview (`MapPreview` via react-leaflet) at the resolved lat/lon.

The user can **tap the ❓ FAB** at any time. The orchestrator's intent classifier flags compliance questions as `faq`; the `compliance` agent runs RAG over Qdrant (bge-m3 embeddings) and the answer + cited sources land in `compliance_qna`.

## The seven agents

All in `apps/api/app/agents/`. Each is a pure async function over the `KYCState` TypedDict; nodes return **delta dicts**, not the whole state, so the `add_messages` reducer doesn't double-count.

| Agent | File | Responsibility |
|---|---|---|
| Orchestrator | `orchestrator.py` | Language detection (`en`/`hi`/`mixed`), 2-turn streak switching, intent classification (`continue_flow`/`faq`/`clarify`), reply generation, `widget_for(next_required, state)` mapping |
| Intake | `intake.py` | PDF render (pymupdf, first page → PNG); vision OCR via Ollama; server-side Aadhaar masking; Aadhaar face crop via `DeepFace.extract_faces`; confidence heuristic; writes `documents` |
| Validation | `validation.py` | Cross-doc Jaccard name match, exact DOB match, doc-type sanity, OCR-confidence; weighted score 0-100; writes `validation_results` |
| Biometric | `biometric.py` | DeepFace.verify selfie ↔ Aadhaar photo; DeepFace.analyze for gender; writes `selfies` + `face_checks` |
| Geolocation | `geolocation.py` | IP lookup via `ipwhois_client` (ipinfo.io → ipwho.is fallback); LLM-extracted city/state from Aadhaar address; **country gate**; writes `ip_checks` |
| Compliance | `compliance.py` | RAG retrieve from Qdrant + Ollama answer with cited sources; writes `compliance_qna` |
| Decision | `decision.py` | Pure threshold logic; writes `kyc_records`; marks session `completed` |

## Conventions — read these before touching code

The rules in `.claude/rules/` are the working agreements for this repo, kept in sync with the actual code:

- **`python-fastapi-backend.md`** — router/agent split, LangGraph node pattern, async sessions, pg_insert with on_conflict_do_update, lazy DeepFace, Aadhaar masking, env wiring.
- **`react-frontend.md`** — Vite + React 19 + TS, zod-validated API client, shadcn primitives in `components/ui/`, Tailwind only, sessionStorage rehydration, camera lifecycle.
- **`agentic-workflow.md`** — how the LangGraph is wired, conditional entry on `next_required`, wait-states, decision thresholds, validation weights, audit replay via the checkpoint.
- **`.claude/skills/kyc-domain/SKILL.md`** — Aadhaar/PAN format rules, RBI compliance touchpoints, conversational tone rules.

## Coding style

- **Plain over clever** — most readers (including the original author) are early-career; the code should read top-to-bottom without surprise.
- **Comments explain *why*, not *what*** — most functions don't need comments at all.
- **Files under ~300 lines** — split when they grow past that. The single-router files in `routers/` repeat some boilerplate around graph hydration / message persistence; that duplication is intentional for now.
- **Never log or persist unmasked PII** — Aadhaar numbers must be masked (`XXXX XXXX 1234`) before storage or display, per UIDAI rules. The mask is enforced in `intake.py` (`mask_aadhaar`) and re-applied in `confirm.py` if the user tried to un-mask during edit.
- **Never break the user's flow on a backend error** — surface a friendly message and a recovery action (retake photo, re-upload, etc.).
- **Never silently swap pinned model IDs** — see memory `feedback_model_changes`. If a model needs to change, raise it explicitly first.

## Running the project

See [`README.md`](README.md) for clone-and-run, environment variables, and the dev loop.

## Things to flag before merging

- New dependencies in `apps/api/pyproject.toml` or `apps/web/package.json` — keep the surface small; every dep is a build/audit cost.
- Any change to `WORKFLOW_GRAPH` node order, the `NextRequired` literal set, or decision thresholds — these encode the project's risk policy and are referenced from the plan and spec.
- New fields in the `Widget` schema — must land simultaneously in `apps/api/app/schemas/chat.py` and `apps/web/src/api/schemas.ts`, plus the relevant widget component.
- Any new `documents` field that the FE will render — verify the `EditableFieldCard` actually shows it.
- Anything that writes to disk outside `/data/uploads/<session_id>/`.
- Anything that touches PII handling (storage, display, logging).
- Migration changes — Alembic migrations live under `apps/api/app/db/migrations/`. Don't edit a shipped migration; add a new one.
