# Conversational KYC Agent

A chat-first KYC (Know Your Customer) flow for Indian users, built as a multi-agent LangGraph pipeline. The agent greets the user, captures email + mobile, walks them through Aadhaar and PAN upload (image **or PDF**), takes a selfie, runs face + gender + IP geolocation checks, and returns a verdict — all observable end-to-end. Supports English, Hindi, and Hinglish.

## What you get

- **Clone and run** — one `docker compose up`.
- **Seven specialist agents** — orchestrator, intake (vision OCR + face crop), validation, biometric (DeepFace face + gender), geolocation, compliance (RAG), decision.
- **Mobile-first chat UI** — React 19 + TypeScript + Tailwind + shadcn/ui. Camera capture with crop. Side-by-side face match visual. OpenStreetMap location preview.
- **Postgres audit** — every agent writes its own table; LangGraph checkpoints persisted via `AsyncPostgresSaver`.
- **RAG-grounded compliance Q&A** — Qdrant + bge-m3 embeddings. FAQ drawer with cited sources.
- **Self-hosted Langfuse** — every LLM call traced; per-agent spans (decoration is incremental).

## Setup

This is a one-time setup. Most of it is downloading. Total time is ~10-20 minutes depending on your internet speed.

### Step 1 — Install Docker

Docker runs the database, the API, the web app, and the supporting services in containers so you don't have to install them by hand.

| Your OS | What to install |
|---|---|
| **Windows** | [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) — needs WSL2 enabled (the installer will guide you) |


After install, open a terminal and confirm:

```bash
docker --version          # should print "Docker version 24.x" or newer
docker compose version    # should print "Docker Compose version v2.x" or newer
```

If `docker compose` says "command not found" but `docker-compose` works, you're on Compose v1 — please upgrade. This project uses Compose v2 syntax.

### Step 2 — Install Ollama

Ollama runs the LLMs (chat, OCR, embeddings) **on your machine**, not in Docker. The API container talks to it via `host.docker.internal`.

1. Download from [ollama.com/download](https://ollama.com/download) — there's an installer for macOS, Windows, and Linux.
2. After install, Ollama runs as a background service. Confirm:

   ```bash
   ollama --version          # prints the version
   curl http://localhost:11434/api/tags    # returns JSON; if it errors, start Ollama
   ```

3. Pull the three models the agents need. Each is downloaded once and cached locally. Total download ≈ 2-3 GB:

   ```bash
   ollama pull gemma3:27b-cloud       # chat + reply generation; vision-capable
   ollama pull ministral-3:14b-cloud  # OCR / vision extraction (multimodal)
   ollama pull bge-m3:latest          # 1024-dim embeddings for RAG
   ```

   The `*-cloud` suffix means Ollama serves these from their cloud — you don't need a beefy GPU locally. `bge-m3:latest` runs locally (small, fast).

### Step 3 — Clone the repo

```bash
git clone https://github.com/cosmo666/ai-kyc-agent.git
cd ai-kyc-agent
```

If you don't have Git installed, get it from [git-scm.com/downloads](https://git-scm.com/downloads). Or download the zip from GitHub and unzip it into a folder.

### Step 4 — Create your local `.env`

The repo ships an example env file. Copy it and edit if you want different secrets:

```bash
cp infra/.env.example infra/.env
```

Edit `infra/.env` in any text editor. The defaults work out of the box for local dev. Things you may want to change:

- `POSTGRES_PASSWORD` — change the placeholder if you'll expose Postgres beyond your machine
- `WEB_PORT` — defaults to `5173`. If something else is already on that port (e.g. you already run `npm run dev` for another project), set this to e.g. `5174`
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` — leave blank for now; you'll fill them in later (see [Connecting to Langfuse](#connecting-to-langfuse))

### Step 5 — Start everything

From the repo root:

```bash
docker compose up --build
```

(There's a root-level `docker-compose.yml` shim, so you can also run this from `infra/`. Both work.)

What happens on first boot:

1. **Image builds** (~3-5 min) — Docker compiles the API image (Python + TensorFlow + DeepFace + etc.) and the web image (Vite build + nginx).
2. **Migrations run** automatically when the API container starts (Alembic creates 9 tables).
3. **DeepFace warmup** (~60 s, **only the first time**) — downloads VGG-Face + gender weights (~1.1 GB) into a persistent Docker volume. Future boots reuse the cache and warm in ~5 s.
4. **Six containers come up**: postgres, qdrant, langfuse-db, langfuse, api, web.

You'll know it's ready when the api logs show `[lifespan] DeepFace ready` and `Uvicorn running on http://0.0.0.0:8000`.

### Step 6 — Open the app

Once everything's up, visit:

| What | Where | Why |
|---|---|---|
| **Web app** | <http://localhost:5173> *(or your `WEB_PORT`)* | The chat UI — start here |
| **API docs** | <http://localhost:8000/docs> | Auto-generated Swagger UI for every endpoint |
| **Diagnostic** | <http://localhost:8000/debug/whoami> | Returns the IP the backend resolved for you — useful when geolocation looks wrong |
| **Health** | <http://localhost:8000/health> | Should return `{"status":"ok","ollama":"reachable"}` |
| **Langfuse UI** | <http://localhost:3000> | LLM trace explorer (see [Connecting to Langfuse](#connecting-to-langfuse)) |
| **Qdrant dashboard** | <http://localhost:6333/dashboard> | Inspect the RAG vector collection |

### Step 7 — Seed the RAG corpus (one-time)

The compliance FAQ uses a Qdrant vector store. Seed it with the included corpus (RBI KYC excerpts + project FAQ):

```bash
docker compose exec api uv run python -m app.scripts.reindex_rag
```

You only need to re-run this if you add or edit files in `infra/rag-corpus/`.

### Common gotchas during setup

- **`Cannot connect to the Docker daemon`** — Docker Desktop isn't running. Start it from your Applications / Start Menu.
- **`Bind for 0.0.0.0:5173 failed: port is already allocated`** — port 5173 is in use. Set `WEB_PORT=5174` (or any free port) in `infra/.env` and try again.
- **`http://host.docker.internal:11434 connection refused` from the api container** — Ollama isn't running on the host. Start it (it usually runs as a tray app / system service after install).
- **First selfie capture is slow** — only the very first one. DeepFace downloads VGG-Face weights on demand. Subsequent calls are seconds.
- **You're behind a strict corporate proxy / VPN** — Docker may need proxy config. See Docker Desktop → Settings → Resources → Proxies.

### After setup: every-day commands

```bash
docker compose up -d         # start in the background
docker compose ps            # see which containers are up
docker compose logs -f api   # tail the api logs (Ctrl+C to stop)
docker compose stop          # stop everything; data persists
docker compose down          # stop + remove containers; data persists
docker compose down -v       # stop + remove containers + WIPE the database (use with care)
```

## Connecting to Langfuse

Self-hosted Langfuse stores its own users in a separate Postgres (`langfuse-db`) — they have nothing to do with the `kyc` user that owns the application database. Multi-user is supported, with caveats.

### First-time setup (operator)

1. Open <http://localhost:3000>.
2. **Sign up** with any email + password. Nothing is sent anywhere — credentials are hashed and stored locally in `langfuse-db`.
3. Create an **Organization**, then a **Project** inside it (e.g. `kyc-agent`).
4. Go to **Project Settings → API Keys → Create new API keys**.
5. Copy the **Public Key** (`pk-lf-...`) and **Secret Key** (`sk-lf-...`) into `infra/.env`:

   ```env
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   ```

6. Restart the api so it picks up the keys:

   ```bash
   docker compose restart api
   ```

After this, every Ollama call from the agents emits a trace visible in the Langfuse UI under your project.

### Letting other people connect later

By default the compose config does **not** disable signup, so anyone with network access to `http://localhost:3000` can create their own account.

- A brand-new account starts empty — no organization, no project, no traces.
- To share **your** project with someone, log in as the first user, open your organization → **Members → Invite** by email. They'll join your org when they sign up with that address.
- The `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` in `infra/.env` are project-scoped — anyone with those values can write traces to that project, regardless of whether they have a Langfuse UI account.

### Locking signup down (optional)

If the host is reachable from a network you don't trust, prevent new accounts from being created:

```yaml
# infra/docker-compose.yml — under services.langfuse.environment
AUTH_DISABLE_SIGNUP: "true"
```

Then `docker compose up -d langfuse`. Existing accounts and pending invites still work; only fresh signups are blocked.

### Resetting Langfuse (development only)

```bash
docker compose down langfuse langfuse-db
docker volume rm ai-kyc-agent_langfuse_data
docker compose up -d langfuse
```

This wipes accounts, projects, traces — everything. Useful when iterating locally; **never** run this against a real deployment.

## One-time: seed the RAG corpus

```bash
docker compose exec api uv run python -m app.scripts.reindex_rag
```

Drops `infra/rag-corpus/` (RBI Master Direction excerpts + project FAQ) into Qdrant with bge-m3 embeddings. Re-run any time you add or edit corpus files.

## Smoke test the flow

The flow is **agent-initiated** — you don't have to type "hi" first. The greeting + a contact form appear automatically.

1. Open <http://localhost:5173>.
2. The agent's first message asks for your email + mobile via an inline form. Submit.
3. Give your name when asked.
4. Upload your Aadhaar (JPG / PNG / **PDF** — first page is auto-rendered to PNG before OCR). Review extracted fields. Confirm.
5. Upload your PAN. Confirm.
6. Take a selfie. The biometric agent crops the photo region from your Aadhaar and compares to your selfie via DeepFace VGG-Face.
7. The verdict card shows:
   - **Face match** with both photos side-by-side and an animated scan visual + confidence bar
   - **Gender match** comparing OCR'd gender vs DeepFace prediction
   - **Location** with an OpenStreetMap pin at the resolved coordinates
   - Decision (approved / flagged / rejected) with reason and next steps
8. Tap the ❓ FAB any time to ask a compliance question — answers are RAG-grounded with source citations.

## Architecture

### Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, LangGraph 0.2.x, `AsyncPostgresSaver` |
| Datastores | Postgres 16 (domain + checkpoints), Qdrant (RAG), separate Langfuse Postgres |
| AI | Ollama on host: chat = `gemma3:27b-cloud`, OCR = `ministral-3:14b-cloud`, embeddings = `bge-m3:latest` |
| Vision | DeepFace 0.0.99 (VGG-Face) + Pillow + pymupdf for PDF rendering |
| Geolocation | ipinfo.io (primary) → ipwho.is (fallback); FE provides public IP via `X-Real-IP` header |
| Frontend | Vite 5 + React 19 + TypeScript + Tailwind + shadcn/ui + react-leaflet (OSM map) |
| Observability | Self-hosted Langfuse 2.x |
| Infra | Docker Compose with 6 services: postgres, qdrant, langfuse-db, langfuse, api, web |

### Project layout

```text
apps/
  api/                                  # FastAPI + LangGraph backend
    app/
      main.py                           # App, lifespan (DeepFace warmup), CORS, /health, /debug/whoami
      config.py                         # pydantic-settings, .env-driven
      utils.py                          # get_client_ip() — prefers X-Real-IP header
      agents/
        orchestrator.py                 # Language detection, intent, reply gen, widget envelopes
        intake.py                       # Vision OCR + Aadhaar masking + PDF render + face crop
        validation.py                   # Cross-doc Jaccard + DOB + weighted score
        biometric.py                    # DeepFace verify + gender
        geolocation.py                  # ipinfo / ipwho fallback + city/state extraction
        compliance.py                   # RAG FAQ
        decision.py                     # Threshold logic + final write
      graph/
        state.py                        # KYCState (TypedDict), NextRequired Literal
        builder.py                      # Node wrappers + conditional entry/edges
        checkpointer.py                 # AsyncPostgresSaver context manager
      routers/
        chat.py                         # POST /chat
        upload.py                       # POST /upload (multipart, accepts JPG/PNG/PDF)
        confirm.py                      # POST /confirm
        capture.py                      # POST /capture
        session.py                      # POST /session/init, POST /session/contact, GET /session/{id}
        files.py                        # GET /uploads/{session_id}/{filename} for verdict images
      services/
        ollama_client.py                # Async chat + vision_extract + embed (json strict=False)
        deepface_runner.py              # verify_faces, analyze_gender, extract_largest_face, warm
        ipwhois_client.py               # ipinfo.io primary + ipwho.is fallback
        rag.py                          # Qdrant + bge-m3 retrieve
        langfuse_client.py
      db/
        base.py, session.py
        models.py                       # 9 tables (sessions, messages, documents, validation_results,
                                        #           selfies, face_checks, ip_checks, compliance_qna, kyc_records)
        migrations/                     # Alembic — runs on container start
      schemas/chat.py                   # ChatRequest/Response, Widget envelope, ContactRequest
      scripts/reindex_rag.py
    tests/                              # pytest (parsers, validation math, decision thresholds, mocks)
  web/                                  # Vite + React 19 + TS + Tailwind + shadcn
    src/
      App.tsx                           # ChatShell + FaqDrawer + theme bootstrap
      api/
        client.ts                       # fetch wrappers; auto-injects X-Real-IP header
        schemas.ts                      # zod-validated response shapes
      components/
        chat/
          ChatShell.tsx                 # Header (brand mark, session pill, IP badge, theme toggle, restart)
          MessageList.tsx               # Bubble + widget switch + typing indicator
          MessageBubble.tsx
          ChatInput.tsx                 # Auto-grow textarea, Enter-to-send
        widgets/
          ContactFormWidget.tsx         # Email + mobile, +91 prefix, validation
          DocumentUploadWidget.tsx      # Drop zone + camera, PDF accepted
          EditableFieldCard.tsx         # Confirm OCR'd fields (locked Aadhaar number)
          SelfieCamera.tsx              # Oval face guide + verifying overlay
          VerdictCard.tsx               # Face match (with photos + scan), Gender, Location (with map)
          MapPreview.tsx                # OpenStreetMap via react-leaflet
        camera/CameraCaptureModal.tsx   # react-easy-crop modal for ID photo capture
        faq/FaqDrawer.tsx               # Slide-out drawer + suggested questions
        ui/                             # shadcn primitives (button, card, input, dialog, …)
      hooks/
        useSession.ts                   # sessionStorage-backed; cross-component sync via custom event
        useClientIP.ts                  # Resolves public IP via api.ipify.org → icanhazip fallback
      lib/utils.ts                      # cn() helper (clsx + tailwind-merge)
infra/
  docker-compose.yml                    # 6 services + parameterised WEB_PORT
  .env.example
  rag-corpus/                           # markdown seed corpus
  postgres/init.sql
docker-compose.yml                      # Root shim → infra/docker-compose.yml
```

## How privacy + IP is handled

- **Aadhaar masking** is enforced server-side in code (not by trusting the model) — vision OCR returns the full 12-digit number, and `mask_aadhaar()` reduces it to `XXXX XXXX <last4>` before persisting or returning. Re-applied in the confirm route in case the user un-masks during edit.
- **PII in transit** — backend traffic is local-only by default. CORS is locked to `localhost`/`127.0.0.1` origins.
- **Real client IP** — Docker hides the user IP behind the bridge. The FE auto-discovers your public IP via `api.ipify.org` (CORS-friendly, no key) and sends it as `X-Real-IP` on every API call. The backend's `get_client_ip()` helper prefers that header, falls back to `X-Forwarded-For`, then the socket peer.

## Troubleshooting

- **`"ollama": "unreachable"` in `/health`** — Ollama isn't running, or the container can't reach `host.docker.internal`. On Linux, the `extra_hosts` entry in `docker-compose.yml` adds `host.docker.internal` via `host-gateway`. On Docker Desktop (Mac/Windows), it's built in.
- **First selfie is slow** — only the very first time, while DeepFace downloads VGG-Face weights (~580 MB). The lifespan task pre-warms in the background, so this only matters if the user reaches the selfie step before warmup completes. Subsequent runs are seconds.
- **Container logs show repeated `WatchFiles detected changes`** — uvicorn's `--reload` reacts to host bind-mount edits. Loud but harmless; means new code is picked up live without restart.
- **Geolocation shows the wrong city for mobile users** — IP geolocation for mobile carriers (Jio, Airtel, etc.) returns the carrier's metro aggregation point, not the actual user location. This is a fundamental limit of IP-based geolocation; no service can give street-level accuracy from a mobile IP. ipinfo.io is generally most accurate; ipwho.is is the fallback.
- **`X-Real-IP` not flowing** — the FE badge in the chat header shows the IP it discovered. Green = sending; amber = ipify fetch failed (network/CORS issue from your browser). Check the browser console for `[useClientIP] failed`.
- **Langfuse healthcheck times out on first boot** — Langfuse runs its own migrations on first start; it takes 30-60 s. Give it a moment, then `docker compose ps` should show `healthy`.
- **Qdrant collection missing** — run `docker compose exec api uv run python -m app.scripts.reindex_rag` to (re)create it.
- **PDF upload fails** — `pymupdf` renders the first page to PNG before OCR. If a PDF is encrypted or corrupted, the agent surfaces a friendly "please upload an image instead" reply.
- **Stale browser session after backend changes** — click **Restart** in the chat header to clear the stored session id and force `/session/init`. Or hard-refresh (Ctrl+Shift+R) to drop cached JS.

## Developing

- **Backend code is bind-mounted** — edits to `apps/api/app/**/*.py` trigger uvicorn's auto-reload. No rebuild needed for code changes.
- **Backend dep changes** — edit `apps/api/pyproject.toml`, then `docker compose build api && docker compose up -d api`.
- **Frontend** — `cd apps/web && npm install && npm run dev` to run the Vite dev server outside Docker (port 5173). Set `WEB_PORT` in `.env` to avoid clashing with the docker web container.
- **Tests** — `docker compose exec api uv run pytest -v` (runs inside the API container, where deps are installed).
- **DB inspection** — `docker compose exec postgres psql -U kyc -d kyc`. Or any GUI client at `127.0.0.1:5432` with `kyc / change-me-in-prod / kyc`.

## Stopping

```bash
docker compose stop      # keeps volumes; fast restart
# or
docker compose down      # stops + removes containers; keeps volumes
# or (wipes the database — use with care)
docker compose down -v
```

## License

[Add your licence here.]
