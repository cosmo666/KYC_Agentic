# KYC_Agentic — Project Context for Claude

## What this project is

The **Conversational KYC Agent** — a chat-first Indian KYC (Know Your Customer) flow built as a **LangGraph multi-agent pipeline**. The user chats in Hindi or English, uploads an Aadhaar then a PAN card, takes a selfie, and gets a verdict (`approved` / `flagged` / `rejected`). Every step writes to its own Postgres table; LLM calls are observable in self-hosted Langfuse; compliance Q&A is grounded in a Qdrant RAG corpus.

Originally **Swarnima Negi's B.Tech internship project at Ramrao Adik Institute of Technology** (RAIT), supervised by Dr. Vishakha K. Gaikwad. The internship report — `Conversational_KYC_Internship_Report (1).docx` at the repo root — captures the original intent, but **the report describes the prior MVP**, not the current architecture. Treat the report as historical context; treat the spec at `docs/superpowers/specs/2026-04-24-conversational-kyc-agent-design.md` as the canonical design.

## Current status (v0.1.0, tagged 2026-04-25)

The full implementation plan in `docs/superpowers/plans/2026-04-24-kyc-agent-implementation-plan.md` is executed end-to-end. 6 services run via docker compose; 34 backend pytests pass; the chat → upload → confirm → selfie → verdict path is verified on the live stack.

**Two known divergences from the plan** (see git history of v0.1.0):

1. The "fresh-clone simulation" (`docker compose down -v` + rebuild) was skipped to preserve user test data. The clone-and-run path therefore has positive-signal evidence (image builds, services come up) but no end-to-end "destroy-and-rebuild" proof.
2. The web container was built but not `docker compose up`-ed — port 5173 was held by a Vite dev server. Validated standalone on 5174 instead.

## Stack (actual)

| Layer | Tech |
|---|---|
| Backend | Python 3.11, FastAPI, LangGraph (`langgraph >= 0.2.50`), LangGraph `AsyncPostgresSaver` for checkpointing, SQLAlchemy 2 async + Alembic |
| Datastores | Postgres 16 (domain tables + LangGraph checkpoints), Qdrant (RAG vectors), separate Langfuse Postgres |
| AI | Ollama on the host: chat = `gemma3:27b-cloud`, OCR (vision) = `ministral-3:14b-cloud`, embeddings = `bge-m3:latest`. Real values come from `infra/.env` via docker-compose; `apps/api/app/config.py` carries the same IDs as code defaults. Don't change pinned model IDs without coordination — see memory `feedback_model_changes`. |
| Face match | DeepFace VGG-Face (cosine), gender via DeepFace.analyze; lazy-imported to avoid TF startup cost |
| Geolocation | ipwho.is via `ipwhois_client.py` |
| Observability | Self-hosted Langfuse 2.x |
| Frontend | Vite 5 + React 19 + TypeScript 5 + Tailwind 3 + shadcn/ui primitives + Radix Dialog/Tooltip + react-easy-crop + zod |
| Storage | Postgres for everything domain-level; uploads on a Docker volume (`/data/uploads/<session_id>/<doc>.<ext>`) |
| Infra | Docker Compose with 6 services: `postgres`, `qdrant`, `langfuse-db`, `langfuse`, `api`, `web` |

## Repo layout

```text
KYC_Agentic/
├── apps/
│   ├── api/                          # FastAPI + LangGraph backend
│   │   ├── Dockerfile, entrypoint.sh, pyproject.toml
│   │   ├── app/
│   │   │   ├── main.py               # App factory, CORS, /health, router registration
│   │   │   ├── config.py             # pydantic-settings; .env-driven
│   │   │   ├── agents/               # 7 specialist agents (see below)
│   │   │   ├── graph/                # KYCState, builder, AsyncPostgresSaver checkpointer
│   │   │   ├── routers/              # /chat, /upload, /confirm, /capture, /session
│   │   │   ├── services/             # ollama_client, deepface_runner, ipwhois_client, rag, langfuse_client
│   │   │   ├── db/                   # SQLAlchemy models + Alembic migrations
│   │   │   ├── schemas/chat.py       # Pydantic chat I/O + Widget envelope
│   │   │   └── scripts/              # reindex_rag.py
│   │   └── tests/                    # pytest (parsers, validation math, decision thresholds, mocks)
│   └── web/                          # Vite + React 19 + TS + Tailwind + shadcn
│       ├── Dockerfile, nginx.conf
│       └── src/
│           ├── App.tsx               # ChatShell + FaqDrawer
│           ├── api/                  # client.ts, schemas.ts (zod-validated)
│           ├── components/
│           │   ├── chat/             # ChatShell, MessageList, ChatInput, MessageBubble
│           │   ├── widgets/          # DocumentUpload, EditableFieldCard, SelfieCamera, VerdictCard
│           │   ├── camera/           # CameraCaptureModal (react-easy-crop)
│           │   ├── faq/              # FaqDrawer + FAB
│           │   └── ui/               # shadcn primitives
│           └── hooks/useSession.ts   # sessionStorage-backed session id
├── infra/
│   ├── docker-compose.yml            # 6 services
│   ├── postgres/init.sql
│   └── rag-corpus/                   # markdown seed corpus for the FAQ agent
├── docs/superpowers/
│   ├── specs/2026-04-24-conversational-kyc-agent-design.md  # canonical design
│   └── plans/2026-04-24-kyc-agent-implementation-plan.md    # 16-phase build plan
├── .claude/
│   ├── rules/                        # Conventions for backend, frontend, agentic workflow
│   └── skills/kyc-domain/SKILL.md    # Indian KYC domain knowledge
├── Conversational_KYC_Internship_Report (1).docx  # Historical context
├── CLAUDE.md                         # ← this file
└── README.md                         # Clone-and-run guide
```

## End-to-end flow

1. **Chat opens** — `ChatShell` mounts; if a `sessionId` is in sessionStorage, `getSession` rehydrates the message thread from `/session/{id}`.
2. **Greeting** — orchestrator detects language from the first turn; assistant introduces itself and asks for the user's name.
3. **Aadhaar upload** — file picker or in-browser camera (`CameraCaptureModal` with crop). `POST /upload` saves the file, the LangGraph runs `intake_aadhaar` (Ollama vision OCR via `ministral-3:8b-cloud`).
4. **Aadhaar confirm** — `EditableFieldCard` widget shows extracted fields; user confirms or edits. `POST /confirm` saves `confirmed_json` to the `documents` row.
5. **PAN upload + confirm** — same pattern.
6. **Selfie** — `SelfieCamera` widget captures via `getUserMedia`. `POST /capture` saves the file, the graph runs `biometric` (DeepFace VGG-Face cosine + gender analysis).
7. **Geolocation** — `geolocation` agent calls ipwho.is on the client IP, classifies city/state against the Aadhaar address. **Country gate** — non-IN IP → `rejected`.
8. **Decision** — `decision` agent applies thresholds, persists to `kyc_records`, returns the `verdict` widget.

The user can **tap the ❓ FAB** at any time. That fires the `compliance` agent (RAG over Qdrant with bge-m3 embeddings); answer + sources are persisted to `compliance_qna`.

## The seven agents

All in `apps/api/app/agents/`. Each is a pure async function over the `KYCState` TypedDict; nodes return **delta dicts**, not the whole state, so the `add_messages` reducer doesn't double-count.

| Agent | File | Responsibility |
|---|---|---|
| Orchestrator | `orchestrator.py` | Language detection (`en`/`hi`/`mixed`), 2-turn streak switching, intent classification (`continue_flow`/`faq`/`clarify`), reply generation, `widget_for(next_required, state)` mapping |
| Intake | `intake.py` | Vision OCR via Ollama; Aadhaar masking; confidence heuristic (`high`/`medium`/`low`); writes `documents` |
| Validation | `validation.py` | Cross-doc Jaccard name match, exact DOB match, doc-type sanity, OCR-confidence; weighted score 0-100; writes `validation_results` |
| Biometric | `biometric.py` | DeepFace.verify selfie ↔ Aadhaar photo; DeepFace.analyze for gender; writes `selfies` + `face_checks` |
| Geolocation | `geolocation.py` | ipwho.is lookup; LLM-extracted city/state from Aadhaar address; **country gate**; writes `ip_checks` |
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
