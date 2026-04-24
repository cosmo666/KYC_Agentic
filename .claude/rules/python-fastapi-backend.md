# Python / FastAPI Backend Conventions

## Stack

- **Python 3.11+** with **FastAPI** for the HTTP layer (chosen over Flask for async, type-driven validation, and built-in OpenAPI docs)
- **Uvicorn** as the ASGI server, run on port `9090` (see `config.py`)
- **Ollama** for local model inference — both the **vision OCR** model (`gemma3:4b-cloud`) and the **chat** model use the same Ollama runtime
- **DeepFace** (lazy-imported) for selfie ↔ document face verification (VGG-Face, cosine distance)
- **Tesseract** as an offline fallback for OCR when Ollama is unreachable
- **Pydantic v2** models for request/response schemas
- **python-dotenv** for `.env` loading

## Project structure

```text
backend/
├── main.py                   # FastAPI app, CORS, router registration, /upload-doc legacy alias
├── config.py                 # Reads .env: OLLAMA model, UPLOAD_FOLDER, PORT, TESSERACT_CMD
├── requirements.txt
├── routers/
│   ├── documents.py          # POST /documents/upload — file upload + OCR
│   ├── chat.py               # POST /chat/        — Ollama chat with KYC system prompt
│   ├── face.py               # POST /verify-face  — DeepFace selfie vs document
│   └── validation.py         # POST /validate/    — runs the agentic workflow
├── services/
│   ├── ocr_service.py        # Ollama vision primary, Tesseract fallback
│   ├── chat_service.py       # System prompt + Ollama chat call
│   ├── face_service.py       # DeepFace.verify wrapper, distance → confidence
│   ├── validation_service.py # Cross-document field comparison + weighted scoring
│   └── workflow_service.py   # Agentic pipeline (5 nodes over a KYCState dataclass)
├── models/
│   ├── schemas.py            # ExtractedData, UploadResponse
│   └── chat_schemas.py       # ChatMessage, ChatRequest, ChatResponse
└── uploads/                  # Saved files; ignored by git
```

## Routing

- **One router per resource** in `routers/`, mounted in `main.py` with `app.include_router(...)`.
- **Prefix the router**, not each path: `APIRouter(prefix="/documents", tags=["Documents"])`.
- Keep the legacy `POST /upload-doc` (root-level) alive as a thin wrapper around `routers.documents.upload_document` — the React frontend depends on it. Don't break it without updating `kyc-frontend/src/App.js` in the same change.

## Service layer

- **All AI / business logic lives in `services/`**; routers should be thin (validate input, call a service, return a Pydantic model).
- **No router calls another router.** If two routers need the same logic, extract it into a service function.
- **Lazy-import heavy ML deps** (`from deepface import DeepFace` *inside* the function) — DeepFace pulls TensorFlow at import time and would crash startup if a model is missing.

## OCR pattern (`ocr_service.py`)

1. Try Ollama vision (`gemma3:4b-cloud`) with the strict JSON-only prompt in `EXTRACTION_PROMPT`.
2. Strip markdown fences (` ```json … ``` `) before `json.loads` — the model occasionally wraps output even when told not to.
3. On any exception, fall back to Tesseract + regex (`extract_with_tesseract`).
4. Always return `(ExtractedData, engine_used)` so the caller can surface which engine ran.
5. **Mask the first 8 digits of Aadhaar** (`XXXX XXXX 1234`) before returning — done in the prompt and reinforced in the Tesseract path.

## Face verification pattern (`face_service.py`)

- `DeepFace.verify(...)` with `model_name="VGG-Face"`, `detector_backend="opencv"`, `distance_metric="cosine"`, `enforce_detection=False`.
- Convert distance → confidence: `confidence = max(0, min(100, (1 - distance / threshold) * 100))`.
- Catch `ValueError` separately to return a friendly `faces_detected=False` payload when no face is found, instead of a 500.
- The router (`routers/face.py`) is responsible for **cleaning up temp selfie/document files** in a `finally` block.

## Agentic workflow pattern (`workflow_service.py`)

- The pipeline is a **plain ordered list** of pure functions, not real LangGraph (despite the comments and the report). Each node is `(state: KYCState) -> KYCState` and mutates the dataclass in place.
- Order matters: `classify → completeness → cross_validate → evaluate_face → make_decision`.
- **Add new nodes** by appending to `WORKFLOW_GRAPH` — never call nodes directly from outside.
- Decision thresholds (in `node_make_decision`):
  - Critical name/DOB mismatch → `rejected`
  - Score ≥ 80 **and** face OK → `approved`
  - Score 60–79 (or 40+ without critical fails) → `flagged`
  - Otherwise → `rejected`
- Use `kyc_state_to_dict(state)` to serialise — it flattens `ValidationCheck`s and rounds scores. Don't return raw `KYCState` from a route.

## Validation pattern (`validation_service.py`)

- **Weighted scoring**: Name 0.5, DOB 0.3, DocType 0.1, OCRConf 0.1 — these weights are tuned together; if you change one, re-justify the others.
- **Name match is Jaccard token similarity** with normalisation (lowercased, common Indian titles stripped). Don't add a heavyweight fuzzy lib without reason.
- **DOB normalisation** accepts `DD/MM/YYYY`, `DD-MM-YYYY`, and `YYYY-MM-DD` and emits `DD/MM/YYYY`.
- A `skip` status (e.g. field missing on one doc) gets a neutral 0.5 score so a missing field doesn't sink an otherwise-good case.

## Config

- `config.py` reads from `.env`. Keys currently used: `GEMINI_API_KEY` (legacy, no longer wired up), `UPLOAD_FOLDER`, `PORT`. `TESSERACT_CMD` is hardcoded for Windows — **add an env override** before deploying anywhere else.
- **Never commit `.env`**; `.env.example` is the contract.
- Don't read environment variables outside `config.py` — keep all config lookups in one place.

## CORS

- The CORS allowlist in `main.py` covers `http://localhost:3000` and `:3001` for the React dev server. **If you change the FE port, update both ends.**
- Production deployment will need a stricter allowlist driven from config — flag it before shipping.

## File handling

- **Uploads use `uuid.uuid4().hex`** for filenames to avoid collisions; preserve the original extension.
- **Validate extension** against `ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "pdf"}` before saving.
- **Clean up temp files in a `finally`** for any endpoint that writes scratch files (face verification does this).
- Persistent uploads currently live in `backend/uploads/` — **there is no database yet**. If you add Postgres (per the report's roadmap), introduce a thin DAO layer in `services/`, don't sprinkle SQL through routers.

## Logging

- Print statements are used today (`print("[OCR] Ollama failed: …")`) — acceptable for the POC. **If you add structured logging**, use `logging.getLogger(__name__)` and a single config block in `main.py`. Don't introduce Loguru / Structlog without discussing.

## Testing

- No test suite exists yet. When adding tests, use **pytest** (mirror the `services/` and `routers/` layout under `backend/tests/`).
- For HTTP-boundary tests, use `fastapi.testclient.TestClient(app)` from `main.py`.
- For the Ollama / DeepFace boundary, **mock** — don't make tests depend on a running Ollama or downloaded VGG-Face weights.

## Anti-patterns to avoid

- ❌ Eager import of `deepface` at module load — crashes startup if TensorFlow / model files are missing.
- ❌ Calling Ollama directly from a router — go through `services/`.
- ❌ Removing the `/upload-doc` root alias without updating `kyc-frontend/src/App.js`.
- ❌ Loosening the `EXTRACTION_PROMPT` JSON contract without updating `ExtractedData`.
- ❌ Reading `os.getenv` outside `config.py`.
- ❌ Persisting Aadhaar numbers unmasked anywhere — RBI rules require masking.
- ❌ Logging selfie/document file contents or extracted PII in plain text.
- ❌ Adding a real `langgraph` dependency without first confirming the team wants the pipeline rewritten — today's "agentic workflow" is a hand-rolled list of functions and works fine for the POC scope.
