# Conversational KYC Agent — Design Spec

- **Status:** Approved (ready for implementation planning)
- **Date:** 2026-04-24
- **Owner:** Prerak Gupta (`cosmo666`)
- **Builds on:** Swarnima Negi's internship POC (`Conversational_KYC_Internship_Report (1).docx`)
- **Repo:** `https://github.com/cosmo666/ai-kyc-agent` (private, to be created)
- **Local path:** `c:\Users\prera\dev-ai\KYC_Agentic` (clean rewrite in place)

---

## 1. Background and motivation

The existing project is a working but minimal KYC POC: React 19 + FastAPI + Ollama (`gemma3:4b-cloud`) + DeepFace + an in-memory hand-rolled "agentic" pipeline. It demonstrates the end-to-end flow but stops short of what the internship report describes as the target: a real agentic workflow, persistence, RAG-grounded answers, liveness, observability, and a clone-and-run experience.

This spec is a clean rewrite that closes those gaps. The product story stays the same — **chat with an assistant that walks an Indian user through KYC in Hindi or English** — but the implementation is rebuilt around a multi-agent LangGraph orchestrator, Postgres persistence, Qdrant-backed RAG, shadcn/ui frontend, Langfuse observability, and a fully Dockerised deployment.

The deliverable is a self-contained repo someone can clone and run end-to-end with three `ollama pull` commands and one `docker compose up`.

## 2. Goals

- **Chat-driven KYC flow** — every interaction lives in a chat surface; no separate forms, no tabs.
- **Multi-agent orchestration** — a supervisor agent dispatches to seven specialist agents, each with one job.
- **Editable extraction** — every field the OCR returns is presented as an editable input; the user confirms or corrects before the field is persisted.
- **Document intake by upload OR live camera capture** — same downstream path; camera path adds an in-browser crop step.
- **Biometric verification** — face match (selfie ↔ Aadhaar photo) AND gender estimation (selfie ↔ Aadhaar gender field), both via DeepFace.
- **Geolocation check** — IP via ipwhois.io; country must be India (hard fail otherwise); city/state matched against Aadhaar address (soft flag on mismatch).
- **Compliance Q&A via RAG** — Qdrant-backed retrieval over RBI Master Direction excerpts and a project FAQ; answers cited.
- **Full Postgres persistence** — every agent writes its own table; complete audit trail.
- **Self-hosted observability** — Langfuse traces every LLM call with per-agent spans.
- **Clone-and-run** — `git clone`, `cp .env.example .env`, `docker compose up`, open browser. Three Ollama models pulled beforehand.
- **Open source only** — no proprietary SaaS dependencies (ipwhois.io is the one external HTTP call, with a free tier that doesn't require a key).

## 3. Non-goals

- User accounts / multi-tenant auth. Each browser session is one KYC.
- Liveness detection (e.g. MediaPipe Face Mesh). Called out as future work in the report; not in this spec.
- Production-grade compliance retention (PMLA 5-year rule). The schema supports it; the deployment doesn't enforce it.
- Mobile native apps. Mobile web only.
- Internationalisation beyond Hindi + English.
- TTS for audio responses.
- An admin module / reviewer UI for `flagged` cases.

## 4. Constraints and conventions

- **All software must be open source** (or free-tier SaaS with no lock-in). One exception by user choice: ipwhois.io as the IP geolocation provider.
- **Models (all from Ollama, confirmed available):**
  - Chat / reasoning: `gemma4:31b-cloud`
  - OCR (vision): `ministral-3:8b-cloud`
  - Embeddings: `bge-m3:latest`
- **Stack:** Python 3.11+, FastAPI, LangGraph, SQLAlchemy + Alembic, Postgres 16, Qdrant, Langfuse, React 19, Vite, TypeScript, Tailwind, shadcn/ui, Docker Compose.
- **Ollama runs on the host**, not in Docker. Containers reach it at `host.docker.internal:11434`. Reason: the `:cloud` model tags route via the local Ollama daemon to Ollama Cloud servers — there is no benefit to dockerising the daemon.
- **Coding style** — plain over clever; comments explain the *why*; files under ~300 lines; no PII in logs; Aadhaar always masked (`XXXX XXXX 1234`).
- **No backwards compatibility with the old POC.** Existing `backend/` and `kyc-frontend/` source will be deleted as part of step zero.

## 5. Architecture

### 5.1 High-level component map

```text
┌─────────────────────────────┐         ┌────────────────────────────┐
│ Web (apps/web)              │         │ API (apps/api)             │
│ React 19 + Vite + TS        │ HTTP/WS │ FastAPI + LangGraph        │
│ Tailwind + shadcn/ui        │ ◄─────► │ DeepFace + Ollama client   │
│ Chat shell, editable cards, │         │ Qdrant client + RAG        │
│ camera+crop, FAQ side-pull  │         │ ipwhois.io client          │
└─────────────────────────────┘         └────────────┬───────────────┘
                                                     │
        ┌────────────────────┬───────────────────────┼──────────────────┬──────────────────┐
        ▼                    ▼                       ▼                  ▼                  ▼
┌──────────────────┐ ┌─────────────────┐ ┌──────────────────┐ ┌────────────────┐ ┌──────────────┐
│ Postgres 16      │ │ Qdrant          │ │ Ollama (host)    │ │ Langfuse       │ │ ipwhois.io   │
│ - sessions       │ │ - kyc_corpus    │ │ - gemma4:31b     │ │ (self-hosted   │ │ (external,   │
│ - messages       │ │   (bge-m3 emb,  │ │ - ministral-3:8b │ │  Docker)       │ │  free tier)  │
│ - documents      │ │    1024 dim,    │ │ - bge-m3 (emb)   │ │ traces every   │ │              │
│ - validation_…   │ │    cosine)      │ │                  │ │ LLM call       │ │              │
│ - selfies        │ │                 │ │                  │ │                │ │              │
│ - face_checks    │ │                 │ │                  │ │                │ │              │
│ - ip_checks      │ │                 │ │                  │ │                │ │              │
│ - compliance_qna │ │                 │ │                  │ │                │ │              │
│ - kyc_records    │ │                 │ │                  │ │                │ │              │
│ - lg_checkpoints │ │                 │ │                  │ │                │ │              │
└──────────────────┘ └─────────────────┘ └──────────────────┘ └────────────────┘ └──────────────┘
                                              ▲
                                              │ host.docker.internal:11434
                                              │
                                       ┌──────┴──────────────────────┐
                                       │ docker-compose: web, api,   │
                                       │ postgres, qdrant, langfuse, │
                                       │ langfuse-db                 │
                                       └─────────────────────────────┘
```

### 5.2 Repository layout

```text
ai-kyc-agent/                            (clean rewrite of c:\Users\prera\dev-ai\KYC_Agentic)
├── apps/
│   ├── api/                             # FastAPI + LangGraph
│   │   ├── app/
│   │   │   ├── main.py                  # FastAPI app, lifespan, CORS
│   │   │   ├── config.py                # pydantic-settings; reads .env
│   │   │   ├── agents/                  # ⭐ one file per specialist
│   │   │   │   ├── orchestrator.py
│   │   │   │   ├── intake.py
│   │   │   │   ├── validation.py
│   │   │   │   ├── biometric.py
│   │   │   │   ├── geolocation.py
│   │   │   │   ├── compliance.py
│   │   │   │   └── decision.py
│   │   │   ├── graph/
│   │   │   │   ├── state.py             # KYCState TypedDict
│   │   │   │   ├── builder.py           # supervisor graph wiring
│   │   │   │   └── checkpointer.py      # AsyncPostgresSaver setup
│   │   │   ├── routers/
│   │   │   │   ├── chat.py              # POST /chat (text)
│   │   │   │   ├── upload.py            # POST /upload (file → S3-ish local)
│   │   │   │   ├── capture.py           # POST /capture (cropped image blob)
│   │   │   │   └── session.py           # GET /session/:id (rehydrate)
│   │   │   ├── services/
│   │   │   │   ├── ollama_client.py
│   │   │   │   ├── deepface_runner.py
│   │   │   │   ├── ipwhois_client.py
│   │   │   │   ├── rag.py               # qdrant + retrieval
│   │   │   │   └── langfuse_client.py
│   │   │   ├── db/
│   │   │   │   ├── base.py              # SQLAlchemy declarative base
│   │   │   │   ├── session.py           # async session factory
│   │   │   │   ├── models.py            # all ORM models
│   │   │   │   └── migrations/          # alembic
│   │   │   └── schemas/                 # pydantic (request/response)
│   │   ├── scripts/
│   │   │   ├── reindex_rag.py
│   │   │   └── seed_corpus.py
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── entrypoint.sh                # runs alembic upgrade head, then uvicorn
│   └── web/                             # Vite + React + TS + shadcn/ui
│       ├── src/
│       │   ├── components/
│       │   │   ├── chat/                # ChatShell, MessageBubble, MessageList, ChatInput
│       │   │   ├── widgets/             # DocumentUploadWidget, EditableFieldCard,
│       │   │   │                        # SelfieCamera, VerdictCard
│       │   │   ├── camera/              # CameraCaptureModal, CropTool
│       │   │   ├── faq/                 # FaqDrawer
│       │   │   └── ui/                  # shadcn primitives (auto-generated)
│       │   ├── hooks/                   # useChat, useSession, useCamera
│       │   ├── api/                     # typed client (zod schemas)
│       │   ├── lib/
│       │   ├── App.tsx
│       │   └── main.tsx
│       ├── index.html
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       ├── tailwind.config.ts
│       └── Dockerfile
├── infra/
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── postgres/
│   │   └── init.sql                     # creates app + langfuse databases
│   ├── qdrant/                          # collection bootstrap (script)
│   ├── langfuse/                        # service config
│   └── rag-corpus/                      # seed PDFs + FAQ.md (RBI excerpts + project FAQ)
├── docs/
│   └── superpowers/specs/               # this file lives here
├── .claude/                             # rules + skills (already in place)
├── CLAUDE.md
├── README.md                            # rewritten for clone-and-run
├── .gitignore
└── Conversational_KYC_Internship_Report (1).docx
```

### 5.3 Data flow for one user turn

1. User sends a message (text, file upload, or camera capture) via the web app.
2. Web hits the matching API route (`/chat`, `/upload`, `/capture`), passing `session_id`.
3. API loads the LangGraph state for `session_id` from the Postgres checkpointer.
4. Orchestrator agent runs: classifies intent (`continue_flow` | `faq` | `clarify`).
5. If `faq` → Compliance agent answers, persists to `compliance_qna`, returns to orchestrator with answer.
6. If `continue_flow` → orchestrator dispatches to the specialist for the current `next_required` step. Specialist runs, persists its row(s), updates state, returns.
7. Orchestrator generates the user-facing reply (incl. any widget descriptors), appends both user and assistant messages to `messages`, checkpoints the new state.
8. API returns the new messages + widget(s) + `next_required` to the web app.
9. Web renders the new messages and the appropriate interactive widget.

## 6. Multi-agent design

### 6.1 Roster

| Agent | Model | Job | Returns |
|---|---|---|---|
| **Orchestrator** | gemma4:31b-cloud | Conversational shell, intent routing, widget instructions, language detection. | Next user-facing message + `next_required` |
| **Intake** | ministral-3:8b-cloud (vision) | OCR + structured field extraction from one document image. Aadhaar masking enforced in prompt. | `ExtractedFields` |
| **Validation** | gemma4:31b-cloud | Cross-validate Aadhaar ↔ PAN: name (Jaccard), DOB (normalised exact), doc-type sanity, OCR-confidence weighting. | `ValidationResult { score, checks[] }` |
| **Biometric** | DeepFace (no LLM) | `DeepFace.verify` for face match; `DeepFace.analyze(actions=["gender"])` for gender estimate vs Aadhaar gender field. | `BiometricResult` |
| **Geolocation** | gemma4:31b-cloud + ipwhois.io | ipwhois lookup; LLM extracts city/state from raw Aadhaar address; matches city/state. Country gate. | `IPCheckResult` |
| **Compliance (RAG)** | gemma4:31b-cloud + bge-m3 + Qdrant | Retrieval-augmented FAQ / regulatory Q&A. Triggered when intent is `faq`. | Grounded answer + sources |
| **Decision** | gemma4:31b-cloud | Synthesizes all signals; applies thresholds; produces user-facing reason, flags, recommendations. | `KYCDecision` |

### 6.2 Routing pattern

**Hybrid supervisor:** deterministic dispatch for KYC flow steps (driven by `KYCState.next_required`), LLM-driven only for the FAQ-vs-continue decision. Reasoning: a supervisor LLM could otherwise route to the Biometric agent before a selfie has been captured. Determinism is non-negotiable for compliance.

The Orchestrator is an LLM only for: (a) intent classification, (b) generating the natural-language wrapper around each specialist's output. It does *not* choose which specialist to call — that's a function of `next_required`.

### 6.3 KYC state shape

```python
# apps/api/app/graph/state.py
from typing import TypedDict, Literal, Annotated
from langgraph.graph.message import add_messages

NextRequired = Literal[
    "ask_name", "wait_for_name",
    "ask_aadhaar", "wait_for_aadhaar_image", "ocr_aadhaar", "confirm_aadhaar",
    "ask_pan", "wait_for_pan_image", "ocr_pan", "confirm_pan",
    "cross_validate",
    "ask_selfie", "wait_for_selfie",
    "biometric", "geolocation", "decide", "done",
]

Decision = Literal["pending", "approved", "flagged", "rejected"]

class KYCState(TypedDict, total=False):
    session_id: str
    user_name: str | None
    aadhaar: dict           # {file_path, extracted, confirmed, photo_path}
    pan: dict               # {file_path, extracted, confirmed}
    selfie: dict            # {file_path}
    face_check: dict
    ip_check: dict
    cross_validation: dict
    messages: Annotated[list, add_messages]
    next_required: NextRequired
    decision: Decision
    decision_reason: str
    flags: list[str]
    recommendations: list[str]
```

### 6.4 Orchestrator behaviours (the things easy to leave ambiguous)

- **Language detection.** First user turn is classified `hi` | `en` | `mixed` by the orchestrator and the choice is stored on the session row (`sessions.language`). Every subsequent assistant message is generated in that language. The user can switch by writing in the other language for two consecutive turns; the orchestrator updates the session row and continues in the new language.
- **Intent classification options.** `continue_flow` (the default — advance the graph based on `next_required`), `faq` (route to Compliance agent, return to current state), `clarify` (the user is asking *about the current step* — orchestrator answers in-place using the step's prompt context, no specialist dispatch, `next_required` unchanged).
- **Out-of-order uploads.** If a file or capture arrives for a `doc_type` that doesn't match the current `next_required`, the API returns 409 with a friendly message ("Let's finish your Aadhaar first."). The web app surfaces this as an assistant message rather than an error toast.
- **Widget message envelope.** Every widget the orchestrator wants the UI to render is appended to `messages` as a structured assistant message:

  ```json
  {
    "role": "assistant",
    "content": "Please upload your Aadhaar card.",
    "widget": {
      "type": "upload",
      "doc_type": "aadhaar",
      "accept": ["image/jpeg", "image/png", "application/pdf"]
    }
  }
  ```

  The `widget` field is optional — text-only assistant messages omit it. The four `widget.type` values match section 8.2.

### 6.5 Node graph (textual)

```text
greet → ask_name → wait_for_name → ask_aadhaar → wait_for_aadhaar_image
   → ocr_aadhaar
        ├─ confidence == "low" → ask_aadhaar (loop with "please re-upload")
        └─ ok → confirm_aadhaar → wait_for_aadhaar_confirm
   → ask_pan → wait_for_pan_image → ocr_pan
        ├─ confidence == "low" → ask_pan (loop)
        └─ ok → confirm_pan → wait_for_pan_confirm
   → cross_validate
   → ask_selfie → wait_for_selfie
   → biometric
        ├─ no face detected → ask_selfie (loop)
        └─ ok
   → geolocation
        ├─ country != IN → terminal: rejected (skip decide)
        └─ ok
   → decide → present_verdict (terminal)
```

Parallel "FAQ interrupt": every user text message hits the orchestrator's intent classifier first. If `faq`, the Compliance agent runs as a sub-graph and responds; control returns to whichever wait-state the user was in.

## 7. Persistence contract

### 7.1 Postgres tables (one-to-one with agents)

| Table | Owner agent | Write timing | Key |
|---|---|---|---|
| `sessions` | Orchestrator | `INSERT` on first message; `UPDATE status` on terminal verdict | `id (uuid, pk)` |
| `messages` | Orchestrator | `INSERT` per user turn + per assistant turn (incl. widget messages) | `(session_id, seq)` |
| `documents` | Intake | `UPSERT` on OCR completion (`extracted_json`); `UPDATE` on user confirm (`confirmed_json`) | `unique(session_id, doc_type)` |
| `validation_results` | Validation | `UPSERT` after cross-validation runs | `unique(session_id)` |
| `selfies` | Biometric | `INSERT` on selfie capture | `id` |
| `face_checks` | Biometric | `UPSERT` after `DeepFace.verify` + `DeepFace.analyze` | `unique(session_id, selfie_id)` |
| `ip_checks` | Geolocation | `UPSERT` after ipwhois.io call | `unique(session_id)` |
| `compliance_qna` | Compliance | `INSERT` per FAQ exchange (question, answer, sources) | `id` |
| `kyc_records` | Decision | `INSERT` on terminal decision | `unique(session_id)` |
| `langgraph_checkpoints*` | (LangGraph internal) | Auto-managed by `AsyncPostgresSaver` | (LG-managed) |

### 7.2 Write semantics

1. **Each agent owns its table — and only its table.** No agent writes outside its lane.
2. **Agents write in a session-scoped transaction.** Pseudocode:
   ```python
   async def run(state: KYCState, db: AsyncSession) -> KYCState:
       async with db.begin():
           result = await self._compute(state)
           await self._persist(db, state["session_id"], result)
           state[<slot>] = result
       return state
   ```
3. **Idempotent UPSERTs** (`INSERT … ON CONFLICT (…) DO UPDATE`) for any agent whose work can be retried (Intake, Validation, Biometric, Geolocation, Decision). Pure-append: `messages`, `selfies`, `compliance_qna`.
4. **`extracted_json` is immutable; `confirmed_json` is the user's edits.** When the user confirms an editable card, the orchestrator does a partial `UPDATE documents SET confirmed_json = $1, confirmed_at = now()`. Original OCR is preserved for audit.
5. **Orchestrator persists messages last** — after the dispatched agent has committed and the LangGraph checkpoint has saved. Order: agent runs → agent commits → graph checkpoints → orchestrator generates assistant reply → orchestrator inserts user + assistant messages atomically.
6. **Two storage layers, on purpose:**
   - **Domain tables** (system of record, auditable, queryable).
   - **`langgraph_checkpoints`** (resume-on-refresh; LangGraph-managed; safe to drop without losing audit history).

### 7.3 Migrations

Alembic; one initial migration creates everything above. Lives at `apps/api/app/db/migrations/`. The API's `entrypoint.sh` runs `alembic upgrade head` before `uvicorn` starts.

## 8. Frontend UX

### 8.1 Layout

Mobile-first single column up to `md`; sidebar with FAQ drawer on `lg+`. Top bar shows the agent name and a session badge. Sticky chat input at the bottom. The conversation area is the only scrollable region.

```text
┌─────────────────────────────────────┐
│ Top bar: KYC Agent · session badge  │
├─────────────────────────────────────┤
│  💬 assistant bubble                │
│  💬 assistant bubble                │
│                  user bubble 💬     │
│  ┌───────────────────────────────┐ │
│  │ Interactive widget            │ │  ← rendered inline as a message
│  └───────────────────────────────┘ │
├─────────────────────────────────────┤
│ [type to ask anything...]      [→]  │
└─────────────────────────────────────┘
                              ┌─────┐
                              │ ❓  │  ← FAQ FAB
                              └─────┘
```

### 8.2 Widget catalogue

Interactive widgets are first-class chat messages. Each carries a `widget_type` discriminator the UI uses to pick the renderer.

- **`upload`** — Dropzone + "Open camera" button. Accepts PDF/JPG/PNG. Camera click opens `CameraCaptureModal`.
- **`editable_card`** — Field list, each row is `Label` + `Input`. Bottom "Confirm" button. After confirm, collapses to read-only summary with a small "Edit" affordance.
- **`selfie_camera`** — Camera-only (no file alternative). Live `<video>`, capture button, retake. No crop step (selfie framing is enough).
- **`verdict`** — Coloured card (green/amber/red), decision, plain-language reason, expandable "Why" with every check + score, recommendations list.

### 8.3 Camera capture flow (documents)

1. User clicks "Open camera" in `upload` widget.
2. `Sheet` (shadcn) opens fullscreen with `<video>` from `getUserMedia({ video: { facingMode: "environment" } })`.
3. "Capture" draws the current frame to a `<canvas>`.
4. UI switches to `CropTool` (uses `react-easy-crop`) with corner handles, default crop = full frame.
5. "Use this" → JPEG blob is POSTed to `/capture` with `session_id` and `doc_type`.
6. "Retake" → back to step 2.
7. On API success, modal closes; downstream OCR runs as if the image was uploaded.

### 8.4 shadcn/ui primitives used

`Button`, `Card`, `Input`, `Label`, `Avatar`, `Sheet`, `Dialog`, `Toast`, `Badge`, `Progress`, `Skeleton`, `Tooltip`, `Alert`, `Separator`. Theming via shadcn tokens. Slate base, indigo accent. Light/dark toggle via `next-themes`.

### 8.5 State management

- React state local to `ChatShell` for message list and current widget.
- `useSession` hook owns the session_id (UUID stored in `sessionStorage`; reset on tab close).
- API client in `src/api/client.ts` is a thin typed wrapper over `fetch`, with zod-validated responses.
- No global store (Redux / Zustand) — the API is the source of truth and the UI re-fetches on reconnect.

## 9. Observability (Langfuse)

- Self-hosted Langfuse 2.x in compose. Separate Postgres for Langfuse so app data and trace data don't entangle.
- `langfuse-python` SDK wraps every LLM call via `@observe()` decorator and the Ollama client wrapper.
- One trace per `session_id`. Spans for: intent classification, OCR, RAG retrieval, RAG generation, geolocation reasoning, decision reasoning. Each agent invocation is a span.
- Token usage + latency + model name visible in the Langfuse UI.
- Score on completion: `decision == "approved"` → 1.0, `flagged` → 0.5, `rejected` → 0.0. For cohort analysis.
- A small banner in the API readme tells the user the Langfuse UI is at `http://localhost:3000` after compose comes up, and how to grab the public/secret keys.

## 10. Deployment

### 10.1 docker-compose.yml services

| Service | Image | Port | Notes |
|---|---|---|---|
| `web` | built from `apps/web/Dockerfile` (multi-stage: vite build → nginx serve) | 5173 | Dev: `npm run dev`. Prod: nginx static. |
| `api` | built from `apps/api/Dockerfile` (python:3.11-slim, uv) | 8000 | uvicorn with `--reload` in dev. Mounts `./uploads`. Entrypoint runs `alembic upgrade head`. |
| `postgres` | `postgres:16-alpine` | 5432 | Persistent volume. `init.sql` creates `kyc` and `langfuse` databases. |
| `qdrant` | `qdrant/qdrant:latest` | 6333 | Persistent volume. Bootstrapped on first start by `services/rag.py`. |
| `langfuse-db` | `postgres:16-alpine` | (internal) | Langfuse only. |
| `langfuse` | `langfuse/langfuse:2` | 3000 | Wired to `langfuse-db`. |

**Ollama runs on the host.** Containers reach it at `http://host.docker.internal:11434`. On Linux we add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `api` service.

### 10.2 Environment

`infra/.env.example`:

```env
# App database
POSTGRES_USER=kyc
POSTGRES_PASSWORD=change-me
POSTGRES_DB=kyc

# Ollama (host)
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Models
CHAT_MODEL=gemma4:31b-cloud
OCR_MODEL=ministral-3:8b-cloud
EMBED_MODEL=bge-m3:latest

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=kyc_corpus

# Langfuse (generated on first boot)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://langfuse:3000

# ipwhois.io — free tier works without a key
IPWHOIS_API_KEY=

# Web
VITE_API_URL=http://localhost:8000
```

### 10.3 Volumes

- `postgres_data` — app + langfuse Postgres data
- `qdrant_data` — Qdrant collections
- `uploads` — uploaded documents (bind-mounted to host `./uploads` for inspection during dev)
- `langfuse_data` — langfuse db

### 10.4 Healthchecks

`postgres`, `qdrant`, `langfuse-db`, `langfuse` get healthchecks. `api` `depends_on` them with `condition: service_healthy`. `web` depends on `api`.

## 11. Setup story (the README experience)

```bash
# Prereqs:
#   1. Docker Desktop (or Docker Engine + Compose v2 on Linux)
#   2. Ollama installed locally — https://ollama.com/download
#   3. ~16 GB free disk for Postgres + Qdrant + Langfuse data + uploads

# Pull the three Ollama models (one-time, ~few hundred MB total since :cloud tags are thin)
ollama pull gemma4:31b-cloud
ollama pull ministral-3:8b-cloud
ollama pull bge-m3:latest

# Clone and configure
git clone https://github.com/cosmo666/ai-kyc-agent.git
cd ai-kyc-agent/infra
cp .env.example .env
# (edit if you want to change model tags or Postgres password)

# Bring it up
docker compose up --build
# First boot: ~3-5 min

# Open the web app
#   http://localhost:5173
# Optional dashboards:
#   http://localhost:3000   (Langfuse — sign up locally on first visit)
#   http://localhost:6333/dashboard  (Qdrant)

# (One-time) populate the RAG corpus
docker compose exec api python -m app.scripts.reindex_rag
```

The README also has a "what to do if X breaks" section covering: Ollama not reachable from container (Linux `host-gateway` note), Postgres init race, Qdrant collection missing, ipwhois rate limit.

## 12. Open questions deferred to implementation

- **Embedding chunking strategy for the RAG corpus** — sentence-window vs. fixed-size; pick after seeing the seed corpus quality.
- **Crop tool defaults** — should we attempt server-side document edge detection so the crop is pre-set? Out of scope for v1; user crops manually.
- **Rate limiting on the FAQ endpoint** — none in v1; demo workload only.
- **Aadhaar QR code parsing** — could be a richer extraction path than OCR, but adds a dependency and out of scope for v1.

## 13. Decisions log

| # | Decision | Rationale |
|---|---|---|
| 1 | Clean rewrite in place; old code deleted | Stack changes too significantly to evolve; user picked option A explicitly |
| 2 | LangGraph supervisor with deterministic flow routing | Compliance requires deterministic step ordering; LLM only routes intent (FAQ vs continue) |
| 3 | One agent per concern (7 agents total) | Each maps to one real KYC concern; testable in isolation; per-agent Langfuse spans |
| 4 | Postgres for both app data AND LangGraph checkpoints | Single backup story; clear separation by schema |
| 5 | Ollama on the host, not in Docker | `:cloud` tags route through local daemon to Ollama Cloud — dockerising adds nothing |
| 6 | shadcn/ui + Tailwind + Vite (TypeScript) | Modern, open-source, type-safe; matches "modern clean UI" requirement |
| 7 | Self-hosted Langfuse with separate Postgres | Open source; no SaaS dep; trace data isolated from app data |
| 8 | Hard fail on `country != IN`, soft flag on city/state mismatch | User picked option C |
| 9 | ipwhois.io as IP provider | User specified |
| 10 | Each agent writes its own table; orchestrator writes `sessions` and `messages` | Clear ownership; one PR can change one agent without touching others |
| 11 | `extracted_json` immutable, `confirmed_json` mutable | Audit trail: we always know what the OCR said vs what the user changed |
| 12 | Session-only auth (no accounts) | Demo handoff; "easy clone and run" |
| 13 | Mobile-first responsive design | KYC users in India skew mobile |
| 14 | DeepFace for both face match AND gender estimation | Single library, single dependency, two analyses |
| 15 | RAG corpus seeded with RBI Master Direction excerpts + project FAQ | Meaningful out-of-the-box; user can drop more PDFs in `infra/rag-corpus/` |
| 16 | No liveness, TTS, admin module, or wider doc support in v1 | Called out in report's "future work"; out of scope here |

## 14. Future work (acknowledged, out of scope)

- MediaPipe Face Mesh liveness detection
- Admin module / reviewer UI for `flagged` cases
- TTS for audio responses
- Wider document support (passport, driver's licence, voter ID)
- Aadhaar QR parsing
- Production-grade compliance retention (PMLA 5-year rule)
- User accounts + session linking across devices
- Server-side document edge detection for auto-crop
