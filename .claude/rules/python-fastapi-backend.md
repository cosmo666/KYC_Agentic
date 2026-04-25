# Python / FastAPI Backend Conventions

## Stack

- **Python 3.11–3.12** (`requires-python = ">=3.11,<3.13"`), managed with **uv** (`uv sync`, `uv run`).
- **FastAPI** + **Uvicorn** on port `8000` (the container exposes `8000:8000` per `infra/docker-compose.yml`).
- **LangGraph 0.2.x** for the multi-agent state machine, with **`AsyncPostgresSaver`** (`langgraph-checkpoint-postgres`) persisting graph state to the same Postgres that holds the domain tables.
- **SQLAlchemy 2 async** + **asyncpg** for the application driver, **psycopg** sync for Alembic.
- **Pydantic v2** + **pydantic-settings** for config and request/response validation.
- **Ollama** on the host for all LLM calls (chat + vision OCR + embeddings) — the container reaches it via `host.docker.internal` (mapped to `host-gateway` on Linux via `extra_hosts`).
- **DeepFace** (lazy-imported, runs in `asyncio.to_thread`) for face verification + gender analysis.
- **Qdrant** for the RAG vector store; `bge-m3:latest` produces 1024-dim embeddings.
- **Langfuse 2.x** (self-hosted) for tracing; client wired in `services/langfuse_client.py`. `@observe()` decoration on each agent is a deferred follow-up — the client is ready, the calls are not yet wrapped.

## Project structure

```text
apps/api/
├── Dockerfile                         # uv-based; copies app/ + tests/, runs entrypoint.sh
├── entrypoint.sh                      # alembic upgrade head → uvicorn
├── pyproject.toml                     # deps + ruff + pytest config
├── app/
│   ├── main.py                        # App factory, lifespan (httpx + OllamaClient on app.state),
│   │                                  # CORS, /health, router registration
│   ├── config.py                      # Settings (pydantic-settings, env-driven)
│   ├── agents/
│   │   ├── orchestrator.py            # Language detection, intent, reply gen, widget mapping
│   │   ├── intake.py                  # Vision OCR + Aadhaar masking + confidence heuristic
│   │   ├── validation.py              # Cross-doc Jaccard + DOB + weighted score
│   │   ├── biometric.py               # DeepFace verify + gender
│   │   ├── geolocation.py             # ipwho.is + country gate + LLM city/state extraction
│   │   ├── compliance.py              # RAG FAQ
│   │   └── decision.py                # Threshold logic + final write
│   ├── graph/
│   │   ├── state.py                   # KYCState (TypedDict), NextRequired Literal, Decision Literal
│   │   ├── builder.py                 # n_* node wrappers + conditional entry/edges
│   │   └── checkpointer.py            # AsyncPostgresSaver context manager (open_checkpointer)
│   ├── routers/
│   │   ├── chat.py                    # POST /chat
│   │   ├── upload.py                  # POST /upload (multipart)
│   │   ├── confirm.py                 # POST /confirm (JSON)
│   │   ├── capture.py                 # POST /capture (multipart, supports selfie + camera-captured docs)
│   │   └── session.py                 # GET /session/{id} for refresh-rehydration
│   ├── services/
│   │   ├── ollama_client.py           # Async chat + vision_extract + embed
│   │   ├── deepface_runner.py         # verify_faces + analyze_gender (lazy DeepFace)
│   │   ├── ipwhois_client.py          # ipwho.is wrapper
│   │   ├── rag.py                     # Qdrant + Ollama embed + retrieve
│   │   └── langfuse_client.py         # Self-hosted Langfuse wiring
│   ├── db/
│   │   ├── base.py, session.py        # Engine, SessionLocal, get_db
│   │   ├── models.py                  # 9 tables (sessions, messages, documents, validation_results,
│   │   │                              #           selfies, face_checks, ip_checks, compliance_qna, kyc_records)
│   │   └── migrations/                # Alembic
│   ├── schemas/chat.py                # ChatRequest/Response, ChatMessage, Widget
│   └── scripts/reindex_rag.py         # CLI: re-embed infra/rag-corpus into Qdrant
└── tests/                             # pytest-asyncio mode=auto
    ├── test_health.py, test_config.py
    ├── agents/                        # parser, validation math, decision threshold tests
    ├── graph/                         # builder smoke test
    └── services/                      # ollama + ipwhois mocks
```

## Routing

- **One router per domain action** in `routers/`, each mounted in `main.py` with `app.include_router(...)`.
- **Prefix the router**, not each path: `APIRouter(prefix="/chat", tags=["chat"])` — the route handler is `@router.post("")`.
- The 5 domain routes are: `POST /chat`, `POST /upload`, `POST /confirm`, `POST /capture`, `GET /session/{session_id}`.
- All four mutating routes return the same `ChatResponse` shape — that's what lets the FE treat any agent turn the same way.
- **Routes are intentionally fat for now.** Each one (`chat`, `upload`, `confirm`, `capture`) repeats the pattern of: open checkpointer → compile graph → snapshot state → guard `next_required` → invoke graph → `aupdate_state` with the assistant message → persist a row to `messages`. This duplication is acceptable until the pattern is proven; pulling a helper out prematurely will make the LangGraph integration harder to read.

## Agent / graph pattern

- **Agents are pure async functions** that take `(state: KYCState, db: AsyncSession, ...)` and return a **delta dict**, never the full state. The `add_messages` reducer on `KYCState.messages` would otherwise double-count anything the node didn't explicitly touch.
- **Nodes in `graph/builder.py`** are thin wrappers that build per-invocation `httpx.AsyncClient` + `OllamaClient` + `SessionLocal`. They wrap the agent function and forward the delta. This is per-invocation construction by design — not a hot-path optimisation, just a shape that makes per-step DB transactions explicit.
- **Checkpointer is opened per request** via `async with open_checkpointer() as saver`. `AsyncPostgresSaver.from_conn_string` runs `setup()` (creates checkpoint tables; idempotent). Don't keep a global saver — it would couple lifespan to a specific event loop.
- **Routing is conditional on `state.next_required`** — see `_route_from_current` and `set_conditional_entry_point`. Wait states (`wait_for_*`, `done`) hand control back to the API caller (`return END`); the rest map 1:1 to nodes. Adding a new agent step means: (a) add a literal to `NextRequired` in `state.py`, (b) add a node wrapper in `builder.py`, (c) extend `_route_from_current` and the `add_conditional_edges` mapping for every node.

## OCR pattern (`agents/intake.py` + `services/ollama_client.py`)

1. `OllamaClient.vision_extract(prompt, image_path)` base64-encodes the image and posts to `/api/chat` with `format: "json"` and `temperature: 0.0`.
2. `parse_vision_output` tries `json.loads` first, falls back to `strip_json_fence` for ` ```json ... ``` ` wrappers.
3. `pick_ocr_confidence` produces `high` / `medium` / `low` based on which required fields are present.
4. `mask_aadhaar` enforces the `XXXX XXXX 1234` format on any 12-digit number — re-applied in `confirm.py` if the user un-masked during edit.
5. **No Tesseract fallback** in the new architecture (the previous MVP had one). If Ollama is unreachable the request fails with a 5xx; the orchestrator-level recovery is a future task.

## Face verification pattern (`agents/biometric.py` + `services/deepface_runner.py`)

- `verify_faces(selfie_path, reference_path)` calls `DeepFace.verify(model_name="VGG-Face", detector_backend="opencv", distance_metric="cosine", enforce_detection=False)`.
- Confidence: `(1 - distance / threshold) * 100`, clamped 0–100; threshold defaults to 0.4.
- `ValueError` from "Face could not be detected" → `{"verified": False, "faces_detected": False, ...}`. The agent uses `faces_detected: False` to push the user back to `wait_for_selfie` (don't terminate the flow on a missed face).
- DeepFace is **CPU-bound and synchronous** — always wrap in `asyncio.to_thread(...)` from the agent.
- DeepFace is **lazy-imported** inside the function body — TensorFlow at import time would crash startup if a weight file is missing.
- Reference face = Aadhaar `photo_path` if cropped, else the full Aadhaar image. Cropping is not yet implemented; the full image is always used today.

## Validation pattern (`agents/validation.py`)

- **Weighted scoring**: `name_match 0.5`, `dob_match 0.3`, `doc_type_sanity 0.1`, `ocr_confidence 0.1`. These weights are tuned together — re-justify all four if you change one.
- **Name match** is **Jaccard token similarity** after `normalize_name` (lowercase, strip Indian honorifics: `mr`, `mrs`, `ms`, `miss`, `dr`, `shri`, `smt`, `km`, `kumari`, plus Devanagari `श्री`, `श्रीमती`, `श्रीमान`, `कुमारी`, `कुमार`).
  - Status thresholds: `pass` ≥ 0.75, `warn` ≥ 0.5, `fail` < 0.5. **Note:** these differ from earlier values in the spec — the code is the source of truth.
- **DOB match** is exact after `normalize_dob` accepts `DD/MM/YYYY`, `DD-MM-YYYY`, `YYYY-MM-DD`, `DD MM YYYY` and emits `DD/MM/YYYY`.
- A `skip` status (field missing on one side) gets a neutral 0.5 score so a missing field doesn't sink an otherwise-clean case.
- Critical fails on `name_match` or `dob_match` are appended to `state.flags` as `{check}_critical_fail` — these are read by the decision agent.

## Decision pattern (`agents/decision.py`)

`compute_decision(state)` is **pure and deterministic**. The order of gates matters:

1. **Country gate** — `ip_check.country_ok == False` → `rejected` with `ip_country_not_india` flag (also short-circuits from inside `geolocation.py` before reaching `decide`).
2. **Critical mismatch** — `name_match_critical_fail` or `dob_match_critical_fail` → `rejected`.
3. **No face detected** — `face_check.faces_detected == False` → `rejected` (note: the biometric agent normally pushes the user back to `wait_for_selfie` instead, so this branch fires only if biometric was bypassed somehow).
4. **Approved** — `score ≥ 80` AND (`face_check.verified` OR `face_check.confidence ≥ 60`).
5. **Flagged** — `score ≥ 60`, OR `score ≥ 40` with no critical fails.
6. Else → `rejected`.

The geolocation agent **may pre-set `decision = "rejected"`** when the country gate trips. `run_decision` respects that pre-set and skips its own `compute_decision` call. Both paths persist to `kyc_records` and mark the session `completed`.

## Persistence (`db/models.py`)

9 tables. Every domain table has a `session_id` FK with `ON DELETE CASCADE`. Most domain tables have a `UNIQUE (session_id)` (or `(session_id, doc_type)`) constraint so agents can use `pg_insert(...).on_conflict_do_update(...)` for idempotent re-runs.

| Table | Written by | Notes |
|---|---|---|
| `sessions` | `chat.py` (creation), `decision.py` (`completed`) | language tracked here too |
| `messages` | All four mutating routers | `seq` is the integer order; `(session_id, seq)` is unique |
| `documents` | `intake.py` | `extracted_json` then later `confirmed_json` via `confirm.py` |
| `validation_results` | `validation.py` | `overall_score` 0..100, `checks` JSONB array |
| `selfies` | `biometric.py` | one row per selfie capture |
| `face_checks` | `biometric.py` | `(session_id, selfie_id)` unique |
| `ip_checks` | `geolocation.py` | one per session, includes raw ipwho.is response |
| `compliance_qna` | `compliance.py` | one row per FAQ question; sources in JSONB |
| `kyc_records` | `decision.py` | the final verdict |

## Config

- `app/config.py` is a pydantic-settings class. **All env reads happen here** — never `os.getenv` outside this file.
- Defaults exist for everything model-related but are **only fallbacks**. Real values are passed through docker-compose from `infra/.env`.
- **Active models (`infra/.env` + `apps/api/app/config.py` defaults, kept in sync):**
  - `CHAT_MODEL=gemma3:27b-cloud` — chat + reply generation; vision-capable (Gemma 3 supports images)
  - `OCR_MODEL=ministral-3:14b-cloud` — multimodal vision OCR (upgraded from the 8b after it confused the holder's name with the father's name on real Aadhaar samples)
  - `EMBED_MODEL=bge-m3:latest` — 1024-dim embeddings for RAG
  - **Don't swap pinned model IDs silently** — see the user's standing memory `feedback_model_changes`. Raise a discussion before changing any of the three.
- The DSN comes in two flavours: async (`db_url`, asyncpg) for the app, sync (`db_url_sync`, psycopg) for Alembic.

## CORS

- The CORS allowlist in `main.py` is `http://localhost:5173` and `http://127.0.0.1:5173`. **If you change the FE port, update both ends.**
- Production deployment will need a stricter allowlist driven from config — flag it before shipping.

## File handling

- Uploads land at `/data/uploads/<session_id>/<doc_type>.<ext>` (Docker volume `uploads`).
- Allowed MIME types: `image/jpeg`, `image/png`, `image/webp`, `application/pdf` for `/upload`; `image/jpeg`, `image/png`, `image/webp` for `/capture` (no PDF for camera shots).
- The router checks `next_required` before saving — wrong step → `409 Conflict`. Don't bypass this check.
- File size limits aren't enforced today; FastAPI's default is fine for the POC but a real deployment needs a `max_upload_size` and probably a virus scan.

## Logging + observability

- Print statements are still used in a few spots — acceptable for the POC. If you add structured logging, use `logging.getLogger(__name__)` and a single config block in `main.py`.
- **Langfuse is wired but unused** in agent code. Adding `@observe()` decoration on each agent function is the natural next step; the client is already on `services/langfuse_client.py`.
- Don't log selfie / document file contents or extracted PII in plain text. Aadhaar numbers are masked at the OCR boundary; keep them masked.

## Testing

- `pytest` with `asyncio_mode = "auto"` (set in `pyproject.toml`). Run inside the API container: `docker compose exec api uv run pytest -v`.
- Test layout mirrors source: `tests/agents/`, `tests/graph/`, `tests/services/`.
- Existing tests cover **pure logic** — parser output, validation math, decision thresholds, orchestrator heuristics, ipwhois client mocks. No live Ollama, no real DeepFace, no real Postgres.
- For HTTP-boundary tests, use `fastapi.testclient.TestClient` from `app.main:app`. There aren't any today; if you add some, mock the LangGraph layer rather than spin up a real Postgres in CI.

## Anti-patterns to avoid

- ❌ Eager `from deepface import DeepFace` at module level — TensorFlow at import time crashes startup.
- ❌ Calling Ollama, DeepFace, or ipwho.is from a router — go through `services/` and (for stateful flows) through an agent.
- ❌ Returning the full state from a node — return only the delta.
- ❌ Reading `os.getenv` outside `config.py`.
- ❌ Persisting Aadhaar numbers unmasked anywhere — the mask is enforced on extract and re-applied on confirm.
- ❌ Changing `WORKFLOW_GRAPH` node order or `_route_from_current` mapping without updating the matching `add_conditional_edges` block on every node.
- ❌ Editing a shipped Alembic migration — add a new one.
- ❌ Silently swapping the chat / OCR / embed model ID in `config.py` defaults — see `feedback_model_changes`.
- ❌ Dropping the `next_required` guard in a router — it's the only thing keeping the FE from sending the same request twice and corrupting state.
