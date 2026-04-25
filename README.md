# Conversational KYC Agent

A chat-first KYC (Know Your Customer) flow for Indian users, built as a multi-agent LangGraph pipeline. Chat in Hindi or English, upload Aadhaar and PAN, take a selfie, get a verdict. Full audit trail in Postgres, compliance Q&A over a Qdrant RAG corpus, observability via self-hosted Langfuse.

## What you get

- **Clone and run** — one `docker compose up`.
- **Seven specialist agents** — orchestrator, intake (OCR), validation, biometric, geolocation, compliance (RAG), decision.
- **Mobile-first chat UI** — React 19, Tailwind, shadcn/ui. Camera capture with crop. FAQ drawer.
- **Postgres audit** — every agent writes its own table; easy to query who decided what and why.
- **Langfuse traces** — every LLM call is observable; per-agent spans.

## Prerequisites

1. Docker Desktop (or Docker Engine + Compose v2 on Linux)
2. [Ollama](https://ollama.com/download) installed and running on the host
3. ~16 GB free disk for Postgres, Qdrant, Langfuse, uploads

## One-time setup

```bash
# Pull the three models the agents need
ollama pull gemma3:27b-cloud       # chat + reply generation; vision-capable
ollama pull ministral-3:14b-cloud  # OCR / vision extraction (multimodal)
ollama pull bge-m3:latest          # 1024-dim embeddings for RAG

# Clone and configure
git clone https://github.com/cosmo666/ai-kyc-agent.git
cd ai-kyc-agent/infra
cp .env.example .env
```

Edit `.env` if you want different Postgres passwords. The Langfuse keys can stay blank — traces are no-ops until you fill them in (see below).

## Run it

```bash
cd infra
docker compose up --build
```

First boot: 3-5 min for the API container build. The first selfie capture also takes ~2 min the first time as DeepFace downloads the VGG-Face weights (~500 MB) — subsequent calls are fast.

Then:

- **Web app:** <http://localhost:5173>
- **API docs:** <http://localhost:8000/docs>
- **Langfuse:** <http://localhost:3000> — see [Connecting to Langfuse](#connecting-to-langfuse) below.
- **Qdrant dashboard:** <http://localhost:6333/dashboard>

> **Port 5173 already in use?** A common cause is a Vite dev server (`npm run dev`) already running on the host. The compose mapping is parameterised — set `WEB_PORT=5174` (or any free port) in `infra/.env` and `docker compose up -d --build web` will rebind. The web container is opt-in; the rest of the stack runs without it.

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

1. Open <http://localhost:5173>.
2. Say hi. The assistant asks for your name.
3. Give it, then upload an Aadhaar image (or open the camera).
4. Review the OCR'd fields, confirm.
5. Upload PAN, confirm.
6. Take a selfie. Get your verdict.
7. Tap the ❓ FAB any time to ask a compliance question without leaving the flow.

## Project layout

```text
apps/
  api/              # FastAPI + LangGraph backend
    app/
      agents/       # 7 specialist agents (orchestrator, intake, validation, biometric,
                    #                       geolocation, compliance, decision)
      graph/        # KYCState, builder, AsyncPostgresSaver checkpointer
      routers/      # /chat, /upload, /confirm, /capture, /session, /health
      services/     # ollama_client, deepface_runner, ipwhois_client, rag, langfuse_client
      db/           # SQLAlchemy models + Alembic migrations
      schemas/      # Pydantic chat I/O
      scripts/      # reindex_rag.py
    tests/          # pytest (parsers, validation math, decision thresholds, ollama/ipwhois mocks)
  web/              # Vite + React 19 + TypeScript + Tailwind + shadcn
    src/
      components/
        chat/       # ChatShell, MessageList, ChatInput, MessageBubble
        widgets/    # DocumentUploadWidget, EditableFieldCard, SelfieCamera, VerdictCard
        camera/     # CameraCaptureModal (react-easy-crop)
        faq/        # FaqDrawer + FAB
        ui/         # shadcn primitives (button, card, input, dialog, …)
      api/          # zod-validated client
      hooks/        # useSession (sessionStorage-backed)
infra/
  docker-compose.yml
  .env.example
  rag-corpus/       # markdown seed corpus
  postgres/init.sql
docs/superpowers/
  specs/2026-04-24-conversational-kyc-agent-design.md
  plans/2026-04-24-kyc-agent-implementation-plan.md
```

The full design rationale lives in [docs/superpowers/specs/2026-04-24-conversational-kyc-agent-design.md](docs/superpowers/specs/2026-04-24-conversational-kyc-agent-design.md).

## Troubleshooting

- **`"ollama": "unreachable"` in `/health`** — Ollama isn't running, or the container can't reach `host.docker.internal`. On Linux, the `extra_hosts` entry in `docker-compose.yml` adds `host.docker.internal` via `host-gateway`. On Docker Desktop (Mac/Windows), it's built in.
- **First selfie is very slow** — DeepFace downloads VGG-Face weights on first call (~500 MB). Subsequent calls are fast.
- **Langfuse healthcheck times out on first boot** — Langfuse runs its own migrations on first start; it takes 30-60 s. Give it a moment, then `docker compose ps` should show `healthy`.
- **Qdrant collection missing** — run `docker compose exec api uv run python -m app.scripts.reindex_rag` to (re)create it.
- **`ipwhois` returns reserved/private** — in dev the container sees a private bridge IP. The geolocation agent falls back to `8.8.8.8` (US), which trips the country gate. In prod, the real client IP comes through the proxy and the gate behaves correctly.
- **ipwhois rate limit** — the free tier is rate-limited (~1k/day). Real deployments should grab an API key; set `IPWHOIS_API_KEY` in `.env`.

## Developing

- **Backend:** `cd apps/api && uv sync && uv run uvicorn app.main:app --reload`. Depends on a running compose stack for Postgres / Qdrant.
- **Frontend:** `cd apps/web && npm install && npm run dev`.
- **Tests:** `docker compose exec api uv run pytest -v` (runs inside the API container, where deps are installed).

## Stopping

```bash
cd infra
docker compose stop      # keeps volumes; fast restart
# or
docker compose down      # stops + removes containers; keeps volumes
# or (wipes the database — use with care)
docker compose down -v
```

## License

[Add your licence here.]
