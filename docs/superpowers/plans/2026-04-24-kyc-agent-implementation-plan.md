# Conversational KYC Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the KYC POC as a clone-and-run, multi-agent LangGraph product with Postgres persistence, Qdrant-backed RAG, shadcn/ui frontend, and self-hosted Langfuse observability.

**Architecture:** Monorepo (`apps/api` + `apps/web` + `infra`) with a LangGraph supervisor dispatching to seven specialist agents. Postgres stores both domain data (one table per agent) and LangGraph checkpoints. Qdrant hosts the RAG corpus embedded with `bge-m3`. Ollama runs on the host; all other services run in Docker Compose.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, SQLAlchemy + Alembic, Postgres 16, Qdrant, Langfuse 2.x, React 19, Vite, TypeScript, Tailwind, shadcn/ui, Docker Compose, DeepFace, Ollama (`gemma4:31b-cloud`, `ministral-3:8b-cloud`, `bge-m3:latest`).

**Spec:** `docs/superpowers/specs/2026-04-24-conversational-kyc-agent-design.md`.

---

## How to read this plan

- Phases are checkpoints. **Every phase ends with something you can run and verify.** Don't skip the "verify" step.
- Each task lists `Files:` (Create / Modify / Test) and then numbered steps.
- Steps that write code include the code in full. Copy-paste is fine; the engineer's job is to place it correctly and wire it.
- Commits are explicit steps. **Commit at every marked boundary.** If a step asks you to commit and you don't, the plan's rollback story breaks.
- Testing is TDD where it buys us something (agent logic, validation math, API contracts). For glue code (Dockerfiles, init.sql, Tailwind config) we verify by running the thing, not by unit-testing it.
- Don't run `docker compose down -v` casually — it wipes volumes. Use `docker compose stop` / `docker compose restart` instead.

---

## Phase 0 — Reset & Scaffold

**Goal:** Delete the old POC, lay out the new monorepo structure, get a clean first commit.

**Verify at end:** `tree -L 3 apps infra docs` shows the target skeleton; `git log --oneline` shows one commit.

---

### Task 1: Delete the old POC in place

**Files:**
- Delete: `backend/` (entire tree)
- Delete: `kyc-frontend/` (entire tree)
- Keep: `Conversational_KYC_Internship_Report (1).docx`, `README.md` (will rewrite), `.claude/`, `CLAUDE.md`, `docs/`

- [ ] **Step 1: Verify current state**

Run: `ls`
Expected: see `backend/`, `kyc-frontend/`, `CLAUDE.md`, `README.md`, the `.docx` report, `.claude/`, `docs/`.

- [ ] **Step 2: Initialize git (if not already) and snapshot pre-rewrite state**

```bash
# Only runs if .git doesn't exist
[ -d .git ] || git init
# Temporarily include everything so the snapshot is complete
git add -A
git commit -m "chore: snapshot pre-rewrite state before KYC agent clean rebuild"
```

This commit is the rollback point if anything downstream goes wrong. The large `venv/`, `uploads/`, and `node_modules/` directories are allowed in this one snapshot only — the .gitignore added in Task 3 will exclude them going forward.

- [ ] **Step 3: Remove old backend, frontend, and stale local dirs**

```bash
rm -rf backend kyc-frontend uploads venv
```

Keep: `CLAUDE.md`, `README.md`, `.claude/`, `docs/`, `Conversational_KYC_Internship_Report (1).docx`.

- [ ] **Step 4: Verify and commit the deletion**

```bash
ls
# Expected: only CLAUDE.md, README.md, .claude/, docs/, the .docx — backend/, kyc-frontend/, uploads/, venv/ are gone.

git add -A
git commit -m "chore: remove old POC in preparation for clean rewrite"
```

---

### Task 2: Create monorepo skeleton directories

**Files:**
- Create: `apps/api/app/`, `apps/api/scripts/`, `apps/api/tests/`
- Create: `apps/web/src/`, `apps/web/public/`
- Create: `infra/postgres/`, `infra/qdrant/`, `infra/langfuse/`, `infra/rag-corpus/`

- [ ] **Step 1: Create the directories**

```bash
mkdir -p apps/api/app/{agents,graph,routers,services,db/migrations,schemas}
mkdir -p apps/api/scripts apps/api/tests
mkdir -p apps/web/src/{components/{chat,widgets,camera,faq,ui},hooks,api,lib}
mkdir -p apps/web/public
mkdir -p infra/{postgres,qdrant,langfuse,rag-corpus}
```

- [ ] **Step 2: Add `.gitkeep` to every empty directory so git tracks the structure**

```bash
find apps infra -type d -empty -exec touch {}/.gitkeep \;
```

- [ ] **Step 3: Verify layout**

Run: `find apps infra -maxdepth 3 -type d | sort`
Expected: the full tree from the spec's §5.2 appears.

- [ ] **Step 4: Commit**

```bash
git add apps infra
git commit -m "chore: scaffold monorepo directory structure"
```

---

### Task 3: Root-level `.gitignore` and placeholder README

**Files:**
- Create: `.gitignore`
- Modify: `README.md` (replace with placeholder pointing at the plan)

- [ ] **Step 1: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.uv-cache/

# Node / frontend
node_modules/
dist/
.vite/
*.tsbuildinfo

# Env
.env
.env.local
infra/.env

# Uploads / local data
uploads/
apps/api/uploads/
postgres_data/
qdrant_data/
langfuse_data/

# IDE
.vscode/
.idea/
.DS_Store

# Test / coverage
.pytest_cache/
.coverage
htmlcov/

# LangChain / LangGraph local caches
.langgraph_api/
```

- [ ] **Step 2: Replace `README.md` with a placeholder**

```markdown
# Conversational KYC Agent

A multi-agent LangGraph implementation of a conversational KYC flow for Indian users.

**Status:** Rebuild in progress. See [`docs/superpowers/plans/2026-04-24-kyc-agent-implementation-plan.md`](docs/superpowers/plans/2026-04-24-kyc-agent-implementation-plan.md) for the implementation plan and [`docs/superpowers/specs/2026-04-24-conversational-kyc-agent-design.md`](docs/superpowers/specs/2026-04-24-conversational-kyc-agent-design.md) for the design.

A full setup guide will replace this file at the end of Phase 16.
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore README.md
git commit -m "chore: add .gitignore and placeholder README"
```

---

## Phase 1 — Infrastructure (Docker Compose)

**Goal:** Bring Postgres, Qdrant, Langfuse, and Langfuse's Postgres up with Docker Compose. Nothing application-level yet — we want the data plane running before we write code that depends on it.

**Verify at end:** `docker compose up -d postgres qdrant langfuse-db langfuse` produces four running containers; `http://localhost:6333/dashboard` loads Qdrant; `http://localhost:3100` loads Langfuse signup page (we move Langfuse off port 3000 so it doesn't clash with the web app in dev).

Wait — we already decided web runs on 5173 and Langfuse on 3000 per the spec. Keep Langfuse on 3000. Web is 5173.

---

### Task 4: `infra/.env.example` and `.env`

**Files:**
- Create: `infra/.env.example`
- Create: `infra/.env` (local copy, gitignored)

- [ ] **Step 1: Write `infra/.env.example`**

```env
# ── App database ──────────────────────────────────────
POSTGRES_USER=kyc
POSTGRES_PASSWORD=change-me-in-prod
POSTGRES_DB=kyc
POSTGRES_PORT=5432

# ── Langfuse database (separate Postgres instance) ────
LANGFUSE_DB_USER=langfuse
LANGFUSE_DB_PASSWORD=change-me-in-prod
LANGFUSE_DB_NAME=langfuse

# ── Ollama (runs on the host, not in Docker) ──────────
OLLAMA_BASE_URL=http://host.docker.internal:11434

# ── Models ────────────────────────────────────────────
CHAT_MODEL=gemma4:31b-cloud
OCR_MODEL=ministral-3:8b-cloud
EMBED_MODEL=bge-m3:latest

# ── Qdrant ────────────────────────────────────────────
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=kyc_corpus

# ── Langfuse (fill in after first-boot UI signup) ─────
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://langfuse:3000
NEXTAUTH_SECRET=change-me-32-chars-min-for-langfuse
SALT=change-me-32-chars-min-for-langfuse

# ── ipwhois.io (free tier, no key needed) ─────────────
IPWHOIS_API_KEY=

# ── Web ───────────────────────────────────────────────
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 2: Copy to `.env` for local use**

```bash
cp infra/.env.example infra/.env
```

- [ ] **Step 3: Commit `.env.example` (NOT `.env`)**

```bash
git add infra/.env.example
git commit -m "chore: add env template for compose stack"
```

Confirm `infra/.env` is NOT staged: `git status` should show it as untracked or ignored.

---

### Task 5: Postgres init script (creates both databases)

**Files:**
- Create: `infra/postgres/init.sql`

- [ ] **Step 1: Write init.sql**

```sql
-- Runs once, on first boot, as the POSTGRES_USER superuser in postgres:16-alpine.
-- The "kyc" DB is already created by the POSTGRES_DB env var; we just ensure the
-- uuid-ossp extension exists inside it.

\connect kyc
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
```

Note: Langfuse gets its own Postgres container (`langfuse-db`), so we do NOT create a `langfuse` database here.

- [ ] **Step 2: Commit**

```bash
git add infra/postgres/init.sql
git commit -m "chore: postgres init extensions"
```

---

### Task 6: `docker-compose.yml` — data services only

**Files:**
- Create: `infra/docker-compose.yml`

- [ ] **Step 1: Write compose file (data services; `web` and `api` added later)**

```yaml
# infra/docker-compose.yml
name: ai-kyc-agent

services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD-SHELL", "bash -c ':> /dev/tcp/127.0.0.1/6333' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10

  langfuse-db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${LANGFUSE_DB_USER}
      POSTGRES_PASSWORD: ${LANGFUSE_DB_PASSWORD}
      POSTGRES_DB: ${LANGFUSE_DB_NAME}
    volumes:
      - langfuse_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${LANGFUSE_DB_USER} -d ${LANGFUSE_DB_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 10

  langfuse:
    image: langfuse/langfuse:2
    restart: unless-stopped
    depends_on:
      langfuse-db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgres://${LANGFUSE_DB_USER}:${LANGFUSE_DB_PASSWORD}@langfuse-db:5432/${LANGFUSE_DB_NAME}
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET}
      NEXTAUTH_URL: http://localhost:3000
      SALT: ${SALT}
      TELEMETRY_ENABLED: "false"
      LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES: "false"
    ports:
      - "3000:3000"
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://localhost:3000/api/public/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 10

volumes:
  postgres_data:
  qdrant_data:
  langfuse_data:
```

- [ ] **Step 2: Start the data plane**

```bash
cd infra
docker compose --env-file .env up -d postgres qdrant langfuse-db langfuse
```

- [ ] **Step 3: Verify all four are healthy**

Run: `docker compose ps`
Expected: `postgres`, `qdrant`, `langfuse-db`, `langfuse` all `running` and `healthy`. `langfuse` may take 30-60s to become healthy on first boot as it runs migrations.

If `langfuse` is stuck `starting`, check logs: `docker compose logs langfuse | tail -50`.

- [ ] **Step 4: Hit the dashboards**

- Postgres (via `psql` inside the container): `docker compose exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c '\dx'` → should list `uuid-ossp` and `pgcrypto`.
- Qdrant: open `http://localhost:6333/dashboard` in a browser → shows an empty collections list.
- Langfuse: open `http://localhost:3000` → shows signup page. **Sign up** with any email/password (local only), create a project, and copy the generated public + secret keys into `infra/.env`. Leave them blank for now if you want to automate this later.

- [ ] **Step 5: Commit**

```bash
git add infra/docker-compose.yml
git commit -m "feat(infra): docker-compose for postgres, qdrant, and langfuse"
```

---

## Phase 2 — API Bootstrap

**Goal:** A FastAPI service that starts, has a config module, answers `GET /health`, and is dockerised.

**Verify at end:** `curl http://localhost:8000/health` returns `{"status":"ok","ollama":"reachable"|"unreachable"}`.

---

### Task 7: API `pyproject.toml` with `uv`

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/.python-version`

- [ ] **Step 1: Write `apps/api/pyproject.toml`**

```toml
[project]
name = "kyc-api"
version = "0.1.0"
description = "Conversational KYC multi-agent API"
requires-python = ">=3.11,<3.13"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "python-dotenv>=1.0",
  "httpx>=0.27",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg>=0.29",
  "alembic>=1.13",
  "langgraph>=0.2.50",
  "langgraph-checkpoint-postgres>=2.0",
  "psycopg[binary,pool]>=3.2",
  "langfuse>=2.50,<3",
  "qdrant-client>=1.12",
  "pypdf>=5.0",
  "python-multipart>=0.0.12",
  "deepface>=0.0.93",
  "tf-keras>=2.17",
  "Pillow>=10.4",
  "numpy>=1.26,<2",
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "ruff>=0.7",
  "mypy>=1.13",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "B"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write `apps/api/.python-version`**

```
3.11
```

- [ ] **Step 3: Install deps locally (optional, for editor tooling)**

```bash
cd apps/api
uv sync
```

Expected: creates `.venv/`, resolves and installs everything. If `deepface` or `tf-keras` fails on your platform, skip local install — it will install in Docker.

- [ ] **Step 4: Commit**

```bash
git add apps/api/pyproject.toml apps/api/.python-version
git commit -m "feat(api): pyproject with FastAPI, LangGraph, and DeepFace deps"
```

---

### Task 8: API config module

**Files:**
- Create: `apps/api/app/__init__.py` (empty)
- Create: `apps/api/app/config.py`
- Test: `apps/api/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_config.py
import os

def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example:11434")
    monkeypatch.setenv("CHAT_MODEL", "test-chat")
    monkeypatch.setenv("OCR_MODEL", "test-ocr")
    monkeypatch.setenv("EMBED_MODEL", "test-embed")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "test")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse:3000")

    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.chat_model == "test-chat"
    assert s.ollama_base_url == "http://example:11434"
    assert s.db_url.startswith("postgresql+asyncpg://u:p@")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Write `apps/api/app/config.py`**

```python
# apps/api/app/config.py
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # App database
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # Ollama + models
    ollama_base_url: str = "http://host.docker.internal:11434"
    chat_model: str = "gemma4:31b-cloud"
    ocr_model: str = "ministral-3:8b-cloud"
    embed_model: str = "bge-m3:latest"

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "kyc_corpus"

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://langfuse:3000"

    # ipwhois
    ipwhois_api_key: str = ""

    # Upload dir (inside container)
    upload_dir: str = "/data/uploads"

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def db_url_sync(self) -> str:
        """Alembic uses the sync driver (psycopg)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/__init__.py apps/api/app/config.py apps/api/tests/test_config.py
git commit -m "feat(api): config module with pydantic-settings"
```

---

### Task 9: FastAPI app + `/health` endpoint

**Files:**
- Create: `apps/api/app/main.py`
- Test: `apps/api/tests/test_health.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app


def test_health_returns_status():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "ollama" in body  # "reachable" or "unreachable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_health.py -v`
Expected: `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Write `apps/api/app/main.py`**

```python
# apps/api/app/main.py
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    app.state.http = httpx.AsyncClient(timeout=30)
    yield
    # shutdown
    await app.state.http.aclose()


app = FastAPI(title="KYC Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    settings = get_settings()
    ollama_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                ollama_status = "reachable"
    except Exception:
        pass
    return {"status": "ok", "ollama": ollama_status}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_health.py -v`
Expected: PASS. The test doesn't care if Ollama is reachable, only that the field exists.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/main.py apps/api/tests/test_health.py
git commit -m "feat(api): FastAPI app with /health endpoint"
```

---

### Task 10: API Dockerfile + entrypoint

**Files:**
- Create: `apps/api/Dockerfile`
- Create: `apps/api/entrypoint.sh`

- [ ] **Step 1: Write `apps/api/Dockerfile`**

```dockerfile
# apps/api/Dockerfile
FROM python:3.11-slim

# System deps for DeepFace (opencv, Pillow) and psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv==0.5.4

WORKDIR /app

# Copy manifest first for layer caching
COPY pyproject.toml ./
RUN uv sync --no-dev

COPY app ./app
COPY scripts ./scripts
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Upload dir (mounted as a volume in compose)
RUN mkdir -p /data/uploads

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
```

- [ ] **Step 2: Write `apps/api/entrypoint.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Wait for Postgres (compose healthcheck should have already done this, but belt-and-suspenders).
echo "[entrypoint] waiting for postgres at ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}..."
until (exec 3<>/dev/tcp/${POSTGRES_HOST:-postgres}/${POSTGRES_PORT:-5432}) 2>/dev/null; do
  sleep 1
done
echo "[entrypoint] postgres is up"

# Run migrations (alembic added in Phase 3 — harmless no-op until then)
if [ -f "app/db/migrations/alembic.ini" ]; then
  echo "[entrypoint] running alembic upgrade head"
  uv run alembic -c app/db/migrations/alembic.ini upgrade head
fi

echo "[entrypoint] starting uvicorn"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 3: Build image locally to sanity-check**

```bash
cd apps/api
docker build -t kyc-api:dev .
```

Expected: builds successfully. First build is slow (DeepFace deps); subsequent builds hit layer cache.

- [ ] **Step 4: Commit**

```bash
git add apps/api/Dockerfile apps/api/entrypoint.sh
git commit -m "feat(api): Dockerfile and entrypoint"
```

---

### Task 11: Wire `api` service into docker-compose

**Files:**
- Modify: `infra/docker-compose.yml` (add `api` service)

- [ ] **Step 1: Append `api` service to `infra/docker-compose.yml`** (add before the `volumes:` block)

```yaml
  api:
    build:
      context: ../apps/api
      dockerfile: Dockerfile
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL}
      CHAT_MODEL: ${CHAT_MODEL}
      OCR_MODEL: ${OCR_MODEL}
      EMBED_MODEL: ${EMBED_MODEL}
      QDRANT_URL: ${QDRANT_URL}
      QDRANT_COLLECTION: ${QDRANT_COLLECTION}
      LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY}
      LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY}
      LANGFUSE_HOST: ${LANGFUSE_HOST}
      IPWHOIS_API_KEY: ${IPWHOIS_API_KEY}
    ports:
      - "8000:8000"
    volumes:
      - uploads:/data/uploads
      - ../apps/api/app:/app/app  # dev hot-reload
    extra_hosts:
      - "host.docker.internal:host-gateway"  # needed on Linux for Ollama
```

And add the `uploads` volume at the bottom:

```yaml
volumes:
  postgres_data:
  qdrant_data:
  langfuse_data:
  uploads:
```

- [ ] **Step 2: Build and start**

```bash
cd infra
docker compose --env-file .env up -d --build api
```

- [ ] **Step 3: Verify**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok","ollama":"reachable"}` if Ollama is running on the host; `"unreachable"` otherwise. Either is acceptable at this point.

Check logs: `docker compose logs api | tail -30`.

- [ ] **Step 4: Commit**

```bash
git add infra/docker-compose.yml
git commit -m "feat(infra): wire api service into compose"
```

---

## Phase 3 — Database Layer

**Goal:** SQLAlchemy base, all nine ORM models, and an Alembic initial migration that creates every domain table plus the LangGraph checkpoint tables.

**Verify at end:** `docker compose exec api uv run alembic -c app/db/migrations/alembic.ini upgrade head` applies cleanly; `psql` shows all tables in the `kyc` database.

---

### Task 12: SQLAlchemy base + async session factory

**Files:**
- Create: `apps/api/app/db/__init__.py` (empty)
- Create: `apps/api/app/db/base.py`
- Create: `apps/api/app/db/session.py`

- [ ] **Step 1: Write `apps/api/app/db/base.py`**

```python
# apps/api/app/db/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: Write `apps/api/app/db/session.py`**

```python
# apps/api/app/db/session.py
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_settings = get_settings()
engine = create_async_engine(_settings.db_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/db/__init__.py apps/api/app/db/base.py apps/api/app/db/session.py
git commit -m "feat(api): async SQLAlchemy engine and session"
```

---

### Task 13: ORM models — all nine domain tables

**Files:**
- Create: `apps/api/app/db/models.py`

- [ ] **Step 1: Write `apps/api/app/db/models.py`**

```python
# apps/api/app/db/models.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    language: Mapped[str] = mapped_column(String(8), default="en")   # "en" | "hi" | "mixed"
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|completed|abandoned
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all,delete")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_messages_session_seq"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|system
    content: Mapped[str] = mapped_column(Text)
    widget: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[Session] = relationship(back_populates="messages")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("session_id", "doc_type", name="uq_documents_session_doctype"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(16))       # "aadhaar" | "pan"
    file_path: Mapped[str] = mapped_column(String(512))
    photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # cropped face, aadhaar only
    extracted_json: Mapped[dict] = mapped_column(JSONB)      # immutable: raw OCR output
    confirmed_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # user-edited
    ocr_confidence: Mapped[str] = mapped_column(String(8), default="medium")   # low|medium|high
    engine: Mapped[str] = mapped_column(String(16), default="ollama_vision")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ValidationResult(Base):
    __tablename__ = "validation_results"
    __table_args__ = (UniqueConstraint("session_id", name="uq_validation_session"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    overall_score: Mapped[float] = mapped_column(Float)   # 0..100
    checks: Mapped[list] = mapped_column(JSONB)           # [{name, status, score, detail}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Selfie(Base):
    __tablename__ = "selfies"
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FaceCheck(Base):
    __tablename__ = "face_checks"
    __table_args__ = (UniqueConstraint("session_id", "selfie_id", name="uq_face_check_session_selfie"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    selfie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("selfies.id"))
    verified: Mapped[bool] = mapped_column(Boolean)
    distance: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)         # 0..100
    predicted_gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    aadhaar_gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    gender_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    model: Mapped[str] = mapped_column(String(32), default="VGG-Face")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IPCheck(Base):
    __tablename__ = "ip_checks"
    __table_args__ = (UniqueConstraint("session_id", name="uq_ip_check_session"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    ip: Mapped[str] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    aadhaar_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    aadhaar_state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    state_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    country_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComplianceQna(Base):
    __tablename__ = "compliance_qna"
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSONB)            # [{source, chunk_id, score}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KYCRecord(Base):
    __tablename__ = "kyc_records"
    __table_args__ = (UniqueConstraint("session_id", name="uq_kyc_records_session"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(16))       # approved|flagged|rejected
    decision_reason: Mapped[str] = mapped_column(Text)
    flags: Mapped[list] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/db/models.py
git commit -m "feat(api): ORM models for all nine domain tables"
```

---

### Task 14: Alembic setup + initial migration

**Files:**
- Create: `apps/api/app/db/migrations/alembic.ini`
- Create: `apps/api/app/db/migrations/env.py`
- Create: `apps/api/app/db/migrations/script.py.mako`
- Create: `apps/api/app/db/migrations/versions/` (dir)
- Create: `apps/api/app/db/migrations/versions/0001_initial.py`

- [ ] **Step 1: Write `alembic.ini`**

```ini
[alembic]
script_location = %(here)s
prepend_sys_path = .
version_locations = %(here)s/versions
sqlalchemy.url = driver://user:pass@localhost/dbname  ; overridden in env.py

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Write `env.py`** (sync driver — Alembic runs synchronously; the app itself uses async)

```python
# apps/api/app/db/migrations/env.py
import sys
from logging.config import fileConfig
from pathlib import Path
from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app.*` importable
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import get_settings
from app.db.base import Base
import app.db.models  # noqa: F401  — register all mappers

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.db_url_sync)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.db_url_sync,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = settings.db_url_sync
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Write `script.py.mako`** (standard alembic template)

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Generate the initial migration autogen, then review**

From inside the running `api` container (so it can reach Postgres):

```bash
docker compose exec api uv run alembic -c app/db/migrations/alembic.ini revision --autogenerate -m "initial"
```

This creates `apps/api/app/db/migrations/versions/<hash>_initial.py`. Inspect it — it should include all nine tables. Rename the file to `0001_initial.py` and change the `revision` string inside to `"0001"` so the history is deterministic.

- [ ] **Step 5: Apply the migration**

```bash
docker compose exec api uv run alembic -c app/db/migrations/alembic.ini upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial`.

- [ ] **Step 6: Verify**

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c '\dt'
```

Expected: `sessions`, `messages`, `documents`, `validation_results`, `selfies`, `face_checks`, `ip_checks`, `compliance_qna`, `kyc_records`, `alembic_version` — ten tables total.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/db/migrations/
git commit -m "feat(api): alembic setup and 0001 initial migration"
```

---

## Phase 4 — External Service Clients

**Goal:** Thin, testable wrappers around Ollama, Langfuse, ipwhois, and Qdrant. No agent logic yet.

**Verify at end:** Unit tests pass for each client (using `httpx.MockTransport` where it helps).

---

### Task 15: Ollama client (chat + vision + embeddings)

**Files:**
- Create: `apps/api/app/services/__init__.py` (empty)
- Create: `apps/api/app/services/ollama_client.py`
- Test: `apps/api/tests/services/test_ollama_client.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/services/test_ollama_client.py
import httpx
import pytest
from app.services.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_chat_returns_content():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": "hi there"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://fake") as http:
        c = OllamaClient(http=http, chat_model="m", ocr_model="v", embed_model="e")
        reply = await c.chat([{"role": "user", "content": "hello"}])
        assert reply == "hi there"


@pytest.mark.asyncio
async def test_embed_returns_vector():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embeddings"
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://fake") as http:
        c = OllamaClient(http=http, chat_model="m", ocr_model="v", embed_model="e")
        vec = await c.embed("hello")
        assert vec == [0.1, 0.2, 0.3]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/services/test_ollama_client.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `apps/api/app/services/ollama_client.py`**

```python
# apps/api/app/services/ollama_client.py
from __future__ import annotations
import base64
import json
from pathlib import Path
import httpx


class OllamaClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        chat_model: str,
        ocr_model: str,
        embed_model: str,
    ):
        self.http = http
        self.chat_model = chat_model
        self.ocr_model = ocr_model
        self.embed_model = embed_model

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        r = await self.http.post("/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]

    async def vision_extract(self, prompt: str, image_path: str | Path) -> str:
        """Send a vision prompt with an image; return raw model output (may be JSON string)."""
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        payload = {
            "model": self.ocr_model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        r = await self.http.post("/api/chat", json=payload, timeout=180)
        r.raise_for_status()
        return r.json()["message"]["content"]

    async def embed(self, text: str) -> list[float]:
        payload = {"model": self.embed_model, "prompt": text}
        r = await self.http.post("/api/embeddings", json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["embedding"]


def strip_json_fence(raw: str) -> dict:
    """Some models wrap JSON in ```json ... ```. Strip and parse."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
        if s.lstrip().lower().startswith("json"):
            s = s.split("\n", 1)[1] if "\n" in s else s
    return json.loads(s)
```

- [ ] **Step 4: Add an `__init__.py` for the tests package**

```bash
touch apps/api/tests/__init__.py apps/api/tests/services/__init__.py
```

Run: `cd apps/api && uv run pytest tests/services/test_ollama_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/__init__.py apps/api/app/services/ollama_client.py \
        apps/api/tests/__init__.py apps/api/tests/services/__init__.py \
        apps/api/tests/services/test_ollama_client.py
git commit -m "feat(api): ollama client (chat, vision, embed)"
```

---

### Task 16: Langfuse client + observe wrapper

**Files:**
- Create: `apps/api/app/services/langfuse_client.py`

- [ ] **Step 1: Write the client**

```python
# apps/api/app/services/langfuse_client.py
from functools import lru_cache
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context

from app.config import get_settings


@lru_cache
def get_langfuse() -> Langfuse | None:
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        return None
    return Langfuse(
        public_key=s.langfuse_public_key,
        secret_key=s.langfuse_secret_key,
        host=s.langfuse_host,
    )


__all__ = ["get_langfuse", "observe", "langfuse_context"]
```

Rationale: `@observe()` from `langfuse.decorators` is no-op unless keys are set, so agents can always decorate; observability is opt-in via env.

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/services/langfuse_client.py
git commit -m "feat(api): langfuse client wrapper"
```

---

### Task 17: ipwhois client

**Files:**
- Create: `apps/api/app/services/ipwhois_client.py`
- Test: `apps/api/tests/services/test_ipwhois_client.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/services/test_ipwhois_client.py
import httpx
import pytest
from app.services.ipwhois_client import IPWhoisClient


@pytest.mark.asyncio
async def test_lookup_returns_parsed_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "ip": "1.2.3.4",
            "country": "India",
            "country_code": "IN",
            "region": "Maharashtra",
            "city": "Mumbai",
        })

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://fake") as http:
        c = IPWhoisClient(http=http)
        res = await c.lookup("1.2.3.4")
        assert res["country_code"] == "IN"
        assert res["city"] == "Mumbai"
```

- [ ] **Step 2: Run to see it fail**

Run: `cd apps/api && uv run pytest tests/services/test_ipwhois_client.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the client**

```python
# apps/api/app/services/ipwhois_client.py
import httpx
from app.config import get_settings


class IPWhoisClient:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def lookup(self, ip: str) -> dict:
        s = get_settings()
        params = {}
        if s.ipwhois_api_key:
            params["key"] = s.ipwhois_api_key
        # Free tier: https://ipwho.is/<ip>
        url = f"https://ipwho.is/{ip}" if not s.ipwhois_api_key else f"https://api.ipwhois.io/v2/{ip}"
        # Use the transport configured on self.http so tests can mock.
        r = await self.http.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return {
            "ip": data.get("ip", ip),
            "country": data.get("country"),
            "country_code": data.get("country_code") or data.get("country_code_iso3"),
            "region": data.get("region"),
            "city": data.get("city"),
            "raw": data,
        }
```

- [ ] **Step 4: Run test**

Run: `cd apps/api && uv run pytest tests/services/test_ipwhois_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/ipwhois_client.py apps/api/tests/services/test_ipwhois_client.py
git commit -m "feat(api): ipwhois client"
```

---

### Task 18: Qdrant bootstrap + RAG service skeleton

**Files:**
- Create: `apps/api/app/services/rag.py`

- [ ] **Step 1: Write the RAG service**

```python
# apps/api/app/services/rag.py
from __future__ import annotations
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import get_settings
from app.services.ollama_client import OllamaClient


class RAGService:
    def __init__(self, qdrant: AsyncQdrantClient, ollama: OllamaClient):
        self.q = qdrant
        self.ollama = ollama
        self.collection = get_settings().qdrant_collection

    async def ensure_collection(self, vector_size: int = 1024) -> None:
        cols = await self.q.get_collections()
        if any(c.name == self.collection for c in cols.collections):
            return
        await self.q.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    async def upsert_chunks(self, chunks: list[dict]) -> None:
        """chunks: [{id, text, source, metadata}]"""
        points: list[PointStruct] = []
        for ch in chunks:
            vec = await self.ollama.embed(ch["text"])
            points.append(PointStruct(
                id=ch["id"],
                vector=vec,
                payload={"text": ch["text"], "source": ch["source"], **ch.get("metadata", {})},
            ))
        await self.q.upsert(collection_name=self.collection, points=points)

    async def retrieve(self, query: str, k: int = 4) -> list[dict]:
        vec = await self.ollama.embed(query)
        hits = await self.q.search(
            collection_name=self.collection, query_vector=vec, limit=k
        )
        return [
            {"text": h.payload["text"], "source": h.payload["source"], "score": h.score}
            for h in hits
        ]
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/services/rag.py
git commit -m "feat(api): RAG service (qdrant + ollama embeddings)"
```

---

## Phase 5 — LangGraph Foundation

**Goal:** KYCState defined; AsyncPostgresSaver wired; empty graph that moves a session through `greet → ask_name → done` end-to-end. No real agents yet — just stubs that set `next_required`.

**Verify at end:** Running an ad-hoc script invokes the graph, state is checkpointed to Postgres, and `SELECT * FROM checkpoints` shows rows.

---

### Task 19: KYCState TypedDict

**Files:**
- Create: `apps/api/app/graph/__init__.py` (empty)
- Create: `apps/api/app/graph/state.py`

- [ ] **Step 1: Write the state file**

```python
# apps/api/app/graph/state.py
from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages

NextRequired = Literal[
    "greet",
    "ask_name", "wait_for_name",
    "ask_aadhaar", "wait_for_aadhaar_image",
    "ocr_aadhaar", "confirm_aadhaar", "wait_for_aadhaar_confirm",
    "ask_pan", "wait_for_pan_image",
    "ocr_pan", "confirm_pan", "wait_for_pan_confirm",
    "cross_validate",
    "ask_selfie", "wait_for_selfie",
    "biometric",
    "geolocation",
    "decide",
    "done",
]

Decision = Literal["pending", "approved", "flagged", "rejected"]


class KYCState(TypedDict, total=False):
    session_id: str
    language: str                       # "en" | "hi" | "mixed"
    user_name: str | None

    aadhaar: dict                       # {file_path, extracted_json, confirmed_json, photo_path, ocr_confidence}
    pan: dict
    selfie: dict                        # {file_path, id}

    cross_validation: dict              # {overall_score, checks[]}
    face_check: dict                    # {verified, confidence, gender_match}
    ip_check: dict                      # {country_ok, city_match, state_match, ip, city, region}

    messages: Annotated[list, add_messages]

    next_required: NextRequired
    decision: Decision
    decision_reason: str
    flags: list[str]
    recommendations: list[str]
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/graph/__init__.py apps/api/app/graph/state.py
git commit -m "feat(graph): KYCState typed dict"
```

---

### Task 20: AsyncPostgresSaver checkpointer

**Files:**
- Create: `apps/api/app/graph/checkpointer.py`

- [ ] **Step 1: Write the checkpointer wiring**

```python
# apps/api/app/graph/checkpointer.py
from __future__ import annotations
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings


def _dsn() -> str:
    s = get_settings()
    # AsyncPostgresSaver expects libpq-style DSN (psycopg), not asyncpg.
    return (
        f"postgresql://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{s.postgres_db}"
    )


@asynccontextmanager
async def open_checkpointer():
    async with AsyncPostgresSaver.from_conn_string(_dsn()) as saver:
        await saver.setup()  # creates checkpoint tables if missing (safe to call repeatedly)
        yield saver
```

Note: `AsyncPostgresSaver.setup()` creates its own tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`) the first time it runs. These are separate from our Alembic-managed domain tables — LangGraph owns them.

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/graph/checkpointer.py
git commit -m "feat(graph): async postgres checkpointer wrapper"
```

---

### Task 21: Minimal graph builder with greet → ask_name → done stubs

**Files:**
- Create: `apps/api/app/graph/builder.py`
- Test: `apps/api/tests/graph/test_builder_smoke.py`

- [ ] **Step 1: Write the builder**

```python
# apps/api/app/graph/builder.py
from __future__ import annotations
from langgraph.graph import StateGraph, END

from app.graph.state import KYCState


def _greet(state: KYCState) -> KYCState:
    state.setdefault("messages", [])
    state["messages"].append({
        "role": "assistant",
        "content": "Hi! I'll help you complete your KYC. What's your full name?",
    })
    state["next_required"] = "wait_for_name"
    return state


def _ask_name(state: KYCState) -> KYCState:
    # No-op stub — real orchestrator replaces this in Phase 6.
    return state


def _done(state: KYCState) -> KYCState:
    state["next_required"] = "done"
    return state


def build_graph():
    g = StateGraph(KYCState)
    g.add_node("greet", _greet)
    g.add_node("ask_name", _ask_name)
    g.add_node("done", _done)

    g.set_entry_point("greet")
    g.add_edge("greet", "ask_name")
    g.add_edge("ask_name", "done")
    g.add_edge("done", END)
    return g
```

- [ ] **Step 2: Write a smoke test**

```python
# apps/api/tests/graph/__init__.py — (empty, create the file)
# apps/api/tests/graph/test_builder_smoke.py
import pytest
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer


@pytest.mark.asyncio
async def test_graph_runs_once(tmp_path):
    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": "test-thread-001"}}
        out = await graph.ainvoke(
            {"session_id": "s1", "messages": [], "language": "en"},
            config=thread,
        )
        assert out["next_required"] == "done"
        assert any(m["role"] == "assistant" for m in out["messages"])
```

Create the package file:

```bash
touch apps/api/tests/graph/__init__.py
```

- [ ] **Step 3: Run the test inside the container** (needs Postgres)

```bash
docker compose exec api uv run pytest tests/graph/test_builder_smoke.py -v
```

Expected: PASS. First run also creates LangGraph's checkpoint tables via `setup()`.

- [ ] **Step 4: Verify checkpoint tables exist**

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c '\dt'
```

Expected: now you see `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` alongside the domain tables.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/graph/builder.py apps/api/tests/graph/
git commit -m "feat(graph): minimal builder with checkpointer smoke test"
```

---

## Phase 6 — Orchestrator & First End-to-End Chat

**Goal:** Real Orchestrator that detects language, classifies intent, appends assistant messages with widget envelopes, and persists `sessions` + `messages`. First `/chat` route. User can greet the bot, answer "my name is Asha", and see the Aadhaar upload widget.

**Verify at end:** `POST /chat {session_id: null, text: "hello"}` creates a session, returns the greeting + a name-input widget; follow-up `POST /chat {session_id, text: "Asha"}` replies in the same language and returns an `upload` widget for Aadhaar.

---

### Task 22: Pydantic schemas for chat I/O

**Files:**
- Create: `apps/api/app/schemas/__init__.py` (empty)
- Create: `apps/api/app/schemas/chat.py`

- [ ] **Step 1: Write the schemas**

```python
# apps/api/app/schemas/chat.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


WidgetType = Literal["upload", "editable_card", "selfie_camera", "verdict"]


class Widget(BaseModel):
    type: WidgetType
    # `upload`
    doc_type: str | None = None          # "aadhaar" | "pan"
    accept: list[str] | None = None      # mime types
    # `editable_card`
    fields: list[dict] | None = None     # [{name, label, value}]
    # `verdict`
    decision: str | None = None
    decision_reason: str | None = None
    checks: list[dict] | None = None
    flags: list[str] | None = None
    recommendations: list[str] | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    widget: Widget | None = None


class ChatRequest(BaseModel):
    session_id: str | None = None
    text: str = Field(min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    next_required: str
    language: str
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/schemas/__init__.py apps/api/app/schemas/chat.py
git commit -m "feat(api): pydantic chat schemas"
```

---

### Task 23: Orchestrator agent — language detection + intent classification

**Files:**
- Create: `apps/api/app/agents/__init__.py` (empty)
- Create: `apps/api/app/agents/orchestrator.py`
- Test: `apps/api/tests/agents/test_orchestrator_heuristics.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/agents/__init__.py — (empty, create the file)
# apps/api/tests/agents/test_orchestrator_heuristics.py
from app.agents.orchestrator import detect_language, heuristic_intent


def test_detect_language_en():
    assert detect_language("my name is Asha") == "en"


def test_detect_language_hi_devanagari():
    assert detect_language("मेरा नाम आशा है") == "hi"


def test_detect_language_mixed():
    # Hinglish in Latin script
    assert detect_language("mera naam Asha hai, kyc start karo") == "mixed"


def test_heuristic_intent_faq_on_question_mark():
    assert heuristic_intent("what is KYC?") == "faq"


def test_heuristic_intent_continue_on_short_answer():
    assert heuristic_intent("Asha Sharma") == "continue_flow"
```

```bash
touch apps/api/tests/agents/__init__.py
```

- [ ] **Step 2: Run, see it fail**

Run: `cd apps/api && uv run pytest tests/agents/test_orchestrator_heuristics.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `apps/api/app/agents/orchestrator.py`** (heuristics + the full agent)

```python
# apps/api/app/agents/orchestrator.py
from __future__ import annotations
import re
from typing import Literal

from app.graph.state import KYCState
from app.services.ollama_client import OllamaClient


Language = Literal["en", "hi", "mixed"]
Intent = Literal["continue_flow", "faq", "clarify"]


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_HINGLISH_HINTS = re.compile(
    r"\b(hai|haan|nahi|naam|mera|aap|theek|karo|kya|kyu|kyun|kaise|kaisa)\b", re.I
)


def detect_language(text: str) -> Language:
    """Cheap, deterministic language detection for the first turn.

    - Any Devanagari → hi
    - Latin script with common Hinglish tokens → mixed
    - Otherwise → en
    """
    if _DEVANAGARI.search(text):
        return "hi"
    if _HINGLISH_HINTS.search(text):
        return "mixed"
    return "en"


def heuristic_intent(text: str) -> Intent:
    """Used as a fallback when the LLM is unavailable, and as a fast-path.

    Ends with `?` or starts with a wh-word → faq.
    Short answer (< 6 words) during a wait state → continue_flow.
    Otherwise → continue_flow (the LLM can override).
    """
    t = text.strip().lower()
    if t.endswith("?") or t.startswith(("what ", "why ", "how ", "when ", "who ", "where ", "can i", "is it")):
        return "faq"
    return "continue_flow"


_INTENT_PROMPT = """You are the intent classifier for a KYC chat assistant. The user is mid-flow completing KYC.

Classify the latest user message as exactly one of:
- "continue_flow" — user is answering the current step (name, confirming a value, etc.)
- "faq" — user is asking a general question about KYC, compliance, the process, data privacy
- "clarify" — user is asking about the CURRENT step specifically ("what should I upload?", "why do you need this?")

Respond with JSON: {"intent": "<one of the three>"}
"""


async def classify_intent(ollama: OllamaClient, user_text: str, current_step: str) -> Intent:
    """LLM-driven intent classification. Falls back to heuristic on any error."""
    try:
        raw = await ollama.chat(
            [
                {"role": "system", "content": _INTENT_PROMPT},
                {"role": "user", "content": f"Current step: {current_step}\nUser said: {user_text}"},
            ],
            json_mode=True,
            temperature=0.0,
        )
        import json
        data = json.loads(raw)
        intent = data.get("intent", "continue_flow")
        if intent in ("continue_flow", "faq", "clarify"):
            return intent
    except Exception:
        pass
    return heuristic_intent(user_text)


def update_language(state: KYCState, user_text: str) -> Language:
    """Tracks consecutive-turn switching. See spec §6.4."""
    current = state.get("language") or detect_language(user_text)
    detected = detect_language(user_text)
    if detected == current:
        state["language"] = current
        state["_lang_streak"] = 0
        return current
    streak = state.get("_lang_streak", 0) + 1
    if streak >= 2:
        state["language"] = detected
        state["_lang_streak"] = 0
        return detected
    state["_lang_streak"] = streak
    return current
```

- [ ] **Step 4: Run tests**

Run: `cd apps/api && uv run pytest tests/agents/test_orchestrator_heuristics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/agents/__init__.py apps/api/app/agents/orchestrator.py \
        apps/api/tests/agents/__init__.py apps/api/tests/agents/test_orchestrator_heuristics.py
git commit -m "feat(agents): orchestrator language + intent heuristics"
```

---

### Task 24: Orchestrator — reply generation with widget envelope

**Files:**
- Modify: `apps/api/app/agents/orchestrator.py` (add `generate_reply`)

- [ ] **Step 1: Append to `orchestrator.py`**

```python
# orchestrator.py (continued)


_REPLY_PROMPT = """You are a warm, concise KYC assistant for Indian users. Reply in the user's language.

Language code: {lang}  (en=English, hi=Hindi in Devanagari, mixed=Hinglish in Latin script)

The workflow engine has decided the user must now do: {instruction}

Do NOT invent steps. Keep the reply to 1-2 short sentences. Never mention internal state names
(e.g. "next_required", "wait_for_aadhaar_image"). Do not ask more than one question at a time.
"""


# Map of next_required → (english_instruction, widget)
STEP_WIDGETS: dict[str, tuple[str, dict | None]] = {
    "wait_for_name": ("Ask the user for their full name.", None),
    "wait_for_aadhaar_image": (
        "Tell the user to upload a clear photo of their Aadhaar card (front). They can upload a file or use their camera.",
        {"type": "upload", "doc_type": "aadhaar",
         "accept": ["image/jpeg", "image/png", "application/pdf"]},
    ),
    "wait_for_aadhaar_confirm": (
        "Tell the user to review the fields we extracted from their Aadhaar and confirm or edit them.",
        None,  # widget filled at runtime with actual fields
    ),
    "wait_for_pan_image": (
        "Tell the user to upload a clear photo of their PAN card.",
        {"type": "upload", "doc_type": "pan",
         "accept": ["image/jpeg", "image/png", "application/pdf"]},
    ),
    "wait_for_pan_confirm": (
        "Tell the user to review the fields extracted from their PAN and confirm or edit them.",
        None,
    ),
    "wait_for_selfie": (
        "Tell the user to take a selfie for face verification.",
        {"type": "selfie_camera"},
    ),
    "done": ("Share the KYC verdict in plain language.", None),
}


async def generate_assistant_reply(
    ollama: OllamaClient,
    language: str,
    next_required: str,
    extra_context: str = "",
) -> str:
    instruction = STEP_WIDGETS.get(next_required, ("Continue the conversation.", None))[0]
    if extra_context:
        instruction = f"{instruction}\n\nExtra context: {extra_context}"
    return await ollama.chat(
        [
            {"role": "system", "content": _REPLY_PROMPT.format(lang=language, instruction=instruction)},
            {"role": "user", "content": "Generate the reply now."},
        ],
        temperature=0.5,
    )


def widget_for(next_required: str, state: KYCState | None = None) -> dict | None:
    """Returns the widget envelope for a given step. Falls back to None if not interactive."""
    widget = STEP_WIDGETS.get(next_required, (None, None))[1]
    if widget is None and state:
        # Dynamic widgets: confirm cards embed the actual fields.
        if next_required == "wait_for_aadhaar_confirm":
            aadhaar = state.get("aadhaar", {})
            return {
                "type": "editable_card",
                "doc_type": "aadhaar",
                "fields": _fields_from_extracted(aadhaar.get("extracted_json", {})),
            }
        if next_required == "wait_for_pan_confirm":
            pan = state.get("pan", {})
            return {
                "type": "editable_card",
                "doc_type": "pan",
                "fields": _fields_from_extracted(pan.get("extracted_json", {})),
            }
    return widget


_AADHAAR_FIELDS = [("name", "Full name"), ("dob", "Date of birth"),
                   ("gender", "Gender"), ("aadhaar_number", "Aadhaar number (masked)"),
                   ("address", "Address")]
_PAN_FIELDS = [("name", "Full name"), ("dob", "Date of birth"),
               ("pan_number", "PAN number"), ("father_name", "Father's name")]


def _fields_from_extracted(extracted: dict) -> list[dict]:
    doc_type = extracted.get("doc_type", "")
    fields = _AADHAAR_FIELDS if doc_type == "aadhaar" else _PAN_FIELDS
    return [{"name": k, "label": label, "value": extracted.get(k, "")} for k, label in fields]
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/agents/orchestrator.py
git commit -m "feat(agents): orchestrator reply + widget envelope mapping"
```

---

### Task 25: Orchestrator node integrated into the graph

**Files:**
- Modify: `apps/api/app/graph/builder.py`

- [ ] **Step 1: Rewrite `builder.py`** with the real orchestrator node and stub specialist nodes

```python
# apps/api/app/graph/builder.py
from __future__ import annotations
from langgraph.graph import StateGraph, END

from app.graph.state import KYCState
from app.agents import orchestrator as orch


# ───────────────────── nodes ─────────────────────

async def n_greet(state: KYCState) -> KYCState:
    # First-ever turn. Seed language, emit greeting.
    state.setdefault("messages", [])
    user_msgs = [m for m in state["messages"] if m["role"] == "user"]
    if user_msgs:
        state["language"] = orch.update_language(state, user_msgs[-1]["content"])
    else:
        state["language"] = state.get("language") or "en"
    state["next_required"] = "wait_for_name"
    return state


async def n_capture_name(state: KYCState) -> KYCState:
    """Extract the user's name from their message."""
    last_user = _last_user_text(state)
    # Heuristic: strip "my name is" / "mera naam" / "मेरा नाम है"
    name = _extract_name(last_user)
    state["user_name"] = name
    state["next_required"] = "wait_for_aadhaar_image"
    return state


# Stubs — replaced in later phases
async def n_stub_intake_aadhaar(state: KYCState) -> KYCState:
    state["next_required"] = "wait_for_aadhaar_confirm"
    return state


async def n_stub_intake_pan(state: KYCState) -> KYCState:
    state["next_required"] = "wait_for_pan_confirm"
    return state


async def n_stub_validate(state: KYCState) -> KYCState:
    state["next_required"] = "wait_for_selfie"
    return state


async def n_stub_biometric(state: KYCState) -> KYCState:
    state["next_required"] = "geolocation"
    return state


async def n_stub_geolocation(state: KYCState) -> KYCState:
    state["next_required"] = "decide"
    return state


async def n_stub_decide(state: KYCState) -> KYCState:
    state["decision"] = "approved"
    state["decision_reason"] = "All checks passed (stub)."
    state["flags"] = []
    state["recommendations"] = []
    state["next_required"] = "done"
    return state


# ───────────────────── helpers ─────────────────────

def _last_user_text(state: KYCState) -> str:
    for m in reversed(state.get("messages", [])):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _extract_name(text: str) -> str:
    import re
    t = text.strip()
    for pat in (r"^(my name is|i am|i'm|mera naam|mera nam|मेरा नाम)[: ]*", r"\bhai\b$", r"\bहै\b$"):
        t = re.sub(pat, "", t, flags=re.I).strip()
    # Limit to first 4 tokens, letters + spaces
    t = re.sub(r"[^\w\sऀ-ॿ]", "", t)
    return " ".join(t.split()[:4]).strip() or text.strip()[:40]


# ───────────────────── routing ─────────────────────

def _route_from_current(state: KYCState) -> str:
    nr = state.get("next_required", "wait_for_name")
    # The wait states do not advance on their own — the API caller will
    # invoke the graph when new input arrives.
    if nr == "wait_for_name":
        return END
    if nr == "wait_for_aadhaar_image":
        return END
    if nr == "ocr_aadhaar":
        return "intake_aadhaar"
    if nr == "wait_for_aadhaar_confirm":
        return END
    if nr == "wait_for_pan_image":
        return END
    if nr == "ocr_pan":
        return "intake_pan"
    if nr == "wait_for_pan_confirm":
        return END
    if nr == "cross_validate":
        return "validate"
    if nr == "wait_for_selfie":
        return END
    if nr == "biometric":
        return "biometric"
    if nr == "geolocation":
        return "geolocation"
    if nr == "decide":
        return "decide"
    if nr == "done":
        return END
    return END


def build_graph():
    g = StateGraph(KYCState)
    g.add_node("greet", n_greet)
    g.add_node("capture_name", n_capture_name)
    g.add_node("intake_aadhaar", n_stub_intake_aadhaar)
    g.add_node("intake_pan", n_stub_intake_pan)
    g.add_node("validate", n_stub_validate)
    g.add_node("biometric", n_stub_biometric)
    g.add_node("geolocation", n_stub_geolocation)
    g.add_node("decide", n_stub_decide)

    # Entry chooses where to go based on the incoming state's next_required.
    def _entry(state: KYCState) -> str:
        nr = state.get("next_required")
        if nr is None:
            return "greet"
        if nr == "wait_for_name":
            return "capture_name"
        return _route_from_current(state)

    g.set_conditional_entry_point(_entry, {
        "greet": "greet",
        "capture_name": "capture_name",
        "intake_aadhaar": "intake_aadhaar",
        "intake_pan": "intake_pan",
        "validate": "validate",
        "biometric": "biometric",
        "geolocation": "geolocation",
        "decide": "decide",
        END: END,
    })

    # After each node, route by current next_required.
    for node in ("greet", "capture_name", "intake_aadhaar", "intake_pan",
                 "validate", "biometric", "geolocation", "decide"):
        g.add_conditional_edges(node, _route_from_current, {
            "intake_aadhaar": "intake_aadhaar",
            "intake_pan": "intake_pan",
            "validate": "validate",
            "biometric": "biometric",
            "geolocation": "geolocation",
            "decide": "decide",
            END: END,
        })

    return g
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/graph/builder.py
git commit -m "feat(graph): orchestrator node + stub specialists with routing"
```

---

### Task 26: `/chat` route + session management

**Files:**
- Create: `apps/api/app/routers/__init__.py` (empty)
- Create: `apps/api/app/routers/chat.py`
- Modify: `apps/api/app/main.py` (register router; add Ollama client to app state)

- [ ] **Step 1: Write the chat router**

```python
# apps/api/app/routers/chat.py
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db import models as m
from app.schemas.chat import ChatRequest, ChatResponse, ChatMessage, Widget
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.agents import orchestrator as orch


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ollama = request.app.state.ollama
    session_id = req.session_id or str(uuid.uuid4())

    # Ensure session row exists.
    sess = await db.get(m.Session, uuid.UUID(session_id)) if req.session_id else None
    if sess is None:
        sess = m.Session(id=uuid.UUID(session_id), language="en", status="active")
        db.add(sess)
        await db.flush()

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": session_id}}

        # Load existing state; append the incoming user message.
        snap = await graph.aget_state(thread)
        current_state = snap.values if snap and snap.values else {}
        current_state.setdefault("session_id", session_id)
        current_state.setdefault("messages", [])
        current_state["messages"].append({"role": "user", "content": req.text})

        # Language is (re)detected by the orchestrator.
        language = orch.update_language(current_state, req.text)
        current_state["language"] = language
        sess.language = language

        # Intent classification (only when mid-flow; skip on first turn)
        intent = "continue_flow"
        nr = current_state.get("next_required")
        if nr and nr != "greet":
            intent = await orch.classify_intent(ollama, req.text, nr)

        if intent == "faq":
            # Compliance agent placeholder — replaced in Phase 12.
            answer = "I'll come back to that once I can use the RAG index. For now, let's continue your KYC."
            current_state["messages"].append({"role": "assistant", "content": answer})
            new_state = current_state
        elif intent == "clarify":
            clarification = await ollama.chat(
                [
                    {"role": "system", "content": "You are a KYC assistant. The user asked for clarification "
                                                  f"about the current step ({nr}). Reply in language={language}. "
                                                  "One or two sentences."},
                    {"role": "user", "content": req.text},
                ],
                temperature=0.3,
            )
            current_state["messages"].append({"role": "assistant", "content": clarification})
            new_state = current_state
        else:
            # Run the graph one step.
            new_state = await graph.ainvoke(current_state, config=thread)

            # Orchestrator emits the assistant reply + widget for the new next_required.
            reply_text = await orch.generate_assistant_reply(
                ollama, language, new_state.get("next_required", "done")
            )
            widget = orch.widget_for(new_state["next_required"], new_state)
            assistant_msg = {"role": "assistant", "content": reply_text}
            if widget:
                assistant_msg["widget"] = widget
            new_state["messages"].append(assistant_msg)

        # Persist messages to the domain table.
        count_q = await db.execute(
            select(m.Message).where(m.Message.session_id == sess.id)
        )
        existing_count = len(count_q.scalars().all())
        for i, msg in enumerate(new_state["messages"][existing_count:], start=existing_count):
            db.add(m.Message(
                session_id=sess.id,
                seq=i,
                role=msg["role"],
                content=msg["content"],
                widget=msg.get("widget"),
            ))
        await db.commit()

        # Checkpoint the final state.
        await graph.aupdate_state(thread, new_state)

    # Response: only the NEW messages (since the user's last turn).
    new_msgs = new_state["messages"][-2:] if len(new_state["messages"]) >= 2 else new_state["messages"]
    return ChatResponse(
        session_id=session_id,
        messages=[ChatMessage(**mm) for mm in new_msgs],
        next_required=new_state.get("next_required", "done"),
        language=language,
    )
```

- [ ] **Step 2: Update `main.py` to register the router and Ollama client**

Replace `apps/api/app/main.py`:

```python
# apps/api/app/main.py
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.services.ollama_client import OllamaClient
from app.routers import chat as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    http = httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=180)
    app.state.http = http
    app.state.ollama = OllamaClient(
        http=http,
        chat_model=settings.chat_model,
        ocr_model=settings.ocr_model,
        embed_model=settings.embed_model,
    )
    yield
    await http.aclose()


app = FastAPI(title="KYC Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    settings = get_settings()
    ollama_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                ollama_status = "reachable"
    except Exception:
        pass
    return {"status": "ok", "ollama": ollama_status}


app.include_router(chat_router.router)


# Create routers/__init__.py if empty
```

```bash
touch apps/api/app/routers/__init__.py
```

- [ ] **Step 3: Restart the API and smoke test**

```bash
cd infra
docker compose restart api
sleep 5
# First turn (no session_id)
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' | python -m json.tool
```

Expected: a JSON response with `session_id`, `messages` containing an assistant greeting, `next_required: "wait_for_name"`, `language: "en"`.

Run the second turn with the returned `session_id`:

```bash
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<paste>","text":"Asha Sharma"}' | python -m json.tool
```

Expected: `next_required: "wait_for_aadhaar_image"`, an assistant reply prompting for Aadhaar, and a `widget` of type `upload`.

- [ ] **Step 4: Verify DB rows**

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT seq, role, LEFT(content, 60) AS content, widget->>'type' AS widget FROM messages ORDER BY seq;"
```

Expected: alternating user/assistant rows; assistant rows have `widget` set where applicable.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/main.py apps/api/app/routers/__init__.py apps/api/app/routers/chat.py
git commit -m "feat(api): /chat route end-to-end with orchestrator stubs"
```

---

**Checkpoint:** Phases 0-6 complete. You have a running stack that can take chat input and reply with widget envelopes. Specialists are stubs. Commit a tag so it's easy to roll back.

```bash
git tag phase-6-complete
```

---

## Phase 7 — Intake Agent (Real OCR) + Upload Route

**Goal:** Replace the Aadhaar/PAN stub nodes with real OCR-powered extraction via the vision model. Add `/upload` route that accepts a file, stores it under `/data/uploads/`, and triggers the intake node. Aadhaar numbers are masked before persistence.

**Verify at end:** `POST /upload` with a sample Aadhaar image returns a `wait_for_aadhaar_confirm` state, the `documents` row has `extracted_json` populated, and the Aadhaar number is masked (`XXXX XXXX 1234`).

---

### Task 27: Intake agent — extraction prompts + parser

**Files:**
- Create: `apps/api/app/agents/intake.py`
- Test: `apps/api/tests/agents/test_intake_parsers.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/agents/test_intake_parsers.py
from app.agents.intake import mask_aadhaar, parse_vision_output, pick_ocr_confidence


def test_mask_aadhaar_12_digit():
    assert mask_aadhaar("1234 5678 9012") == "XXXX XXXX 9012"


def test_mask_aadhaar_no_spaces():
    assert mask_aadhaar("123456789012") == "XXXX XXXX 9012"


def test_mask_aadhaar_already_masked_left_alone():
    assert mask_aadhaar("XXXX XXXX 9012") == "XXXX XXXX 9012"


def test_mask_aadhaar_invalid_returns_original():
    assert mask_aadhaar("abc") == "abc"


def test_parse_vision_output_strips_markdown_fence():
    raw = '```json\n{"name": "Asha", "doc_type": "aadhaar"}\n```'
    result = parse_vision_output(raw)
    assert result["name"] == "Asha"


def test_pick_ocr_confidence_low_when_blank_name():
    assert pick_ocr_confidence({"name": "", "dob": "01/01/1990"}) == "low"


def test_pick_ocr_confidence_high_when_full():
    assert pick_ocr_confidence({
        "name": "Asha Sharma", "dob": "01/01/1990",
        "aadhaar_number": "XXXX XXXX 9012", "gender": "F", "address": "Mumbai",
    }) == "high"
```

- [ ] **Step 2: Run to see failures**

Run: `cd apps/api && uv run pytest tests/agents/test_intake_parsers.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `apps/api/app/agents/intake.py`**

```python
# apps/api/app/agents/intake.py
from __future__ import annotations
import json
import re
from pathlib import Path

from app.services.ollama_client import OllamaClient, strip_json_fence


AADHAAR_PROMPT = """You are extracting fields from an Indian Aadhaar card.

Return ONLY a JSON object with these keys — empty string if absent:
{
  "doc_type": "aadhaar",
  "name": "",
  "dob": "DD/MM/YYYY",
  "gender": "Male" | "Female" | "Other" | "",
  "aadhaar_number": "XXXX XXXX NNNN",
  "address": ""
}

Rules:
- The Aadhaar number MUST be masked: replace the first 8 digits with X. Keep the last 4 visible.
- Never return the full unmasked Aadhaar number.
- Normalise the DOB to DD/MM/YYYY.
- If the image is not an Aadhaar card, return the keys with empty strings.
"""

PAN_PROMPT = """You are extracting fields from an Indian PAN card.

Return ONLY a JSON object with these keys — empty string if absent:
{
  "doc_type": "pan",
  "name": "",
  "dob": "DD/MM/YYYY",
  "pan_number": "AAAAA9999A",
  "father_name": ""
}

Rules:
- PAN number is 10 characters: 5 letters, 4 digits, 1 letter.
- Normalise the DOB to DD/MM/YYYY.
- If the image is not a PAN card, return the keys with empty strings.
"""


def mask_aadhaar(value: str) -> str:
    """Leave only the last 4 digits visible. Accept '1234 5678 9012', '123456789012', or
    already-masked input."""
    if not value:
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) != 12:
        # Might already be masked (`XXXX XXXX 9012`) — validate and return as-is
        if re.fullmatch(r"(X{4} ){2}\d{4}", value.strip()):
            return value.strip()
        return value
    last4 = digits[-4:]
    return f"XXXX XXXX {last4}"


def parse_vision_output(raw: str) -> dict:
    """Accept raw model output (optionally fenced) and return a dict."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return strip_json_fence(raw)


def pick_ocr_confidence(fields: dict) -> str:
    """Cheap quality heuristic on the extracted fields."""
    if not fields.get("name"):
        return "low"
    required = ["name", "dob"]
    if fields.get("doc_type") == "aadhaar":
        required += ["aadhaar_number"]
    elif fields.get("doc_type") == "pan":
        required += ["pan_number"]
    missing = sum(1 for k in required if not fields.get(k))
    if missing == 0 and all(fields.get(k) for k in ("gender", "address")
                            if fields.get("doc_type") == "aadhaar"):
        return "high"
    return "medium" if missing <= 1 else "low"


async def extract_fields(
    ollama: OllamaClient, image_path: str | Path, doc_type: str
) -> tuple[dict, str]:
    """Run vision OCR; return (fields_dict, confidence)."""
    prompt = AADHAAR_PROMPT if doc_type == "aadhaar" else PAN_PROMPT
    raw = await ollama.vision_extract(prompt, image_path)
    fields = parse_vision_output(raw)
    fields["doc_type"] = doc_type  # enforce
    if doc_type == "aadhaar" and fields.get("aadhaar_number"):
        fields["aadhaar_number"] = mask_aadhaar(fields["aadhaar_number"])
    return fields, pick_ocr_confidence(fields)
```

- [ ] **Step 4: Run tests**

Run: `cd apps/api && uv run pytest tests/agents/test_intake_parsers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/agents/intake.py apps/api/tests/agents/test_intake_parsers.py
git commit -m "feat(agents): intake — vision prompts, masking, parser, confidence"
```

---

### Task 28: Intake graph node + persistence to `documents`

**Files:**
- Modify: `apps/api/app/graph/builder.py` (replace `n_stub_intake_aadhaar` and `n_stub_intake_pan`)
- Modify: `apps/api/app/agents/intake.py` (add `run_intake`)

- [ ] **Step 1: Append to `apps/api/app/agents/intake.py`**

```python
# intake.py (continued)
import uuid
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.graph.state import KYCState


async def run_intake(
    state: KYCState,
    db: AsyncSession,
    ollama: OllamaClient,
    doc_type: str,
) -> KYCState:
    slot = state.get(doc_type, {})
    file_path = slot.get("file_path")
    if not file_path:
        # Should not happen — upload route sets this before invoking the graph.
        return state

    fields, confidence = await extract_fields(ollama, file_path, doc_type)
    slot["extracted_json"] = fields
    slot["ocr_confidence"] = confidence
    state[doc_type] = slot

    # Persist to documents table (upsert on (session_id, doc_type)).
    session_id = uuid.UUID(state["session_id"])
    stmt = pg_insert(m.Document).values(
        session_id=session_id,
        doc_type=doc_type,
        file_path=file_path,
        extracted_json=fields,
        ocr_confidence=confidence,
        engine="ollama_vision",
    ).on_conflict_do_update(
        index_elements=["session_id", "doc_type"],
        set_={"file_path": file_path, "extracted_json": fields,
              "ocr_confidence": confidence, "engine": "ollama_vision"},
    )
    await db.execute(stmt)
    await db.commit()

    # Advance state.
    if confidence == "low":
        # Send the user back to re-upload.
        state["next_required"] = f"wait_for_{doc_type}_image"
        state.setdefault("flags", []).append(f"{doc_type}_ocr_low_confidence")
    else:
        state["next_required"] = f"wait_for_{doc_type}_confirm"
    return state
```

- [ ] **Step 2: Modify `builder.py` to use the real intake function**

Replace `n_stub_intake_aadhaar` and `n_stub_intake_pan` in `builder.py`:

```python
# builder.py — replace the two stubs with:
from app.agents.intake import run_intake
from app.db.session import SessionLocal


async def n_intake_aadhaar(state: KYCState) -> KYCState:
    # Import late to avoid import cycles
    from app.services.ollama_client import OllamaClient
    # The graph node runs inside a request; pull clients from the "app state" passed
    # via runtime config. Simpler: open a short-lived session + ollama client here.
    import httpx
    from app.config import get_settings
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=180) as http:
        ollama = OllamaClient(http, s.chat_model, s.ocr_model, s.embed_model)
        async with SessionLocal() as db:
            return await run_intake(state, db, ollama, "aadhaar")


async def n_intake_pan(state: KYCState) -> KYCState:
    from app.services.ollama_client import OllamaClient
    import httpx
    from app.config import get_settings
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=180) as http:
        ollama = OllamaClient(http, s.chat_model, s.ocr_model, s.embed_model)
        async with SessionLocal() as db:
            return await run_intake(state, db, ollama, "pan")
```

And change the graph wiring:

```python
# in build_graph():
    g.add_node("intake_aadhaar", n_intake_aadhaar)
    g.add_node("intake_pan", n_intake_pan)
```

(Replaces the two stub registrations.)

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/agents/intake.py apps/api/app/graph/builder.py
git commit -m "feat(agents): intake node with persistence; upsert documents"
```

---

### Task 29: `/upload` route — accept file, persist, kick off graph

**Files:**
- Create: `apps/api/app/routers/upload.py`
- Modify: `apps/api/app/main.py` (register)

- [ ] **Step 1: Write `apps/api/app/routers/upload.py`**

```python
# apps/api/app/routers/upload.py
from __future__ import annotations
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.db import models as m
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatResponse, ChatMessage, Widget
from app.agents import orchestrator as orch


router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


@router.post("", response_model=ChatResponse)
async def upload(
    request: Request,
    session_id: str = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")
    if doc_type not in ("aadhaar", "pan"):
        raise HTTPException(400, f"Unknown doc_type: {doc_type}")

    # Load state first so we can reject out-of-order uploads.
    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": session_id}}
        snap = await graph.aget_state(thread)
        state = dict(snap.values) if snap and snap.values else {}

        expected = {"aadhaar": "wait_for_aadhaar_image", "pan": "wait_for_pan_image"}[doc_type]
        if state.get("next_required") != expected:
            raise HTTPException(
                status_code=409,
                detail=f"Not ready for {doc_type} yet. Current step: {state.get('next_required')}",
            )

        # Save file under /data/uploads/<session>/<doc>.<ext>
        s = get_settings()
        upload_dir = Path(s.upload_dir) / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "").suffix or ".bin"
        dest = upload_dir / f"{doc_type}{suffix}"
        dest.write_bytes(await file.read())

        # Prepare state for the intake node.
        slot = state.get(doc_type, {}) or {}
        slot["file_path"] = str(dest)
        state[doc_type] = slot
        state["next_required"] = f"ocr_{doc_type}"
        state["session_id"] = session_id
        state.setdefault("messages", [])

        new_state = await graph.ainvoke(state, config=thread)

        # Generate assistant reply for the new state.
        reply = await orch.generate_assistant_reply(
            request.app.state.ollama,
            state.get("language", "en"),
            new_state["next_required"],
        )
        widget = orch.widget_for(new_state["next_required"], new_state)
        assistant_msg = {"role": "assistant", "content": reply}
        if widget:
            assistant_msg["widget"] = widget
        new_state["messages"].append(assistant_msg)

        await graph.aupdate_state(thread, new_state)

        # Persist the assistant message row.
        sess_uuid = uuid.UUID(session_id)
        from sqlalchemy import select, func as sqlfunc
        count = (await db.execute(
            select(sqlfunc.count()).select_from(m.Message).where(m.Message.session_id == sess_uuid)
        )).scalar_one()
        db.add(m.Message(
            session_id=sess_uuid,
            seq=count,
            role="assistant",
            content=reply,
            widget=widget,
        ))
        await db.commit()

    return ChatResponse(
        session_id=session_id,
        messages=[ChatMessage(role="assistant", content=reply, widget=Widget(**widget) if widget else None)],
        next_required=new_state["next_required"],
        language=state.get("language", "en"),
    )
```

- [ ] **Step 2: Register the router in `main.py`**

Add to `main.py`:

```python
from app.routers import upload as upload_router
# ...
app.include_router(upload_router.router)
```

- [ ] **Step 3: Restart and smoke test**

```bash
cd infra
docker compose restart api
sleep 5
```

Walk the flow:

```bash
# 1. Start a session
SID=$(curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
echo "session: $SID"

# 2. Provide a name
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"text\":\"Asha Sharma\"}" | python -m json.tool

# 3. Upload a sample Aadhaar image (place one at /tmp/aadhaar-sample.jpg)
curl -s -X POST http://localhost:8000/upload \
  -F "session_id=$SID" -F "doc_type=aadhaar" \
  -F "file=@/tmp/aadhaar-sample.jpg" | python -m json.tool
```

Expected on step 3: `next_required: "wait_for_aadhaar_confirm"`, and an `editable_card` widget with the extracted fields. Aadhaar number field should start with `XXXX`.

Verify DB:

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT doc_type, extracted_json->>'name' AS name, extracted_json->>'aadhaar_number' AS aadhaar, ocr_confidence FROM documents;"
```

Expected: one row; `aadhaar_number` starts with `XXXX`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/routers/upload.py apps/api/app/main.py
git commit -m "feat(api): /upload route with order enforcement and OCR dispatch"
```

---

### Task 30: Confirm flow — `/chat` handles `wait_for_*_confirm` + persists `confirmed_json`

**Files:**
- Create: `apps/api/app/routers/confirm.py`
- Modify: `apps/api/app/main.py` (register)

- [ ] **Step 1: Write the confirm router**

```python
# apps/api/app/routers/confirm.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db import models as m
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatResponse, ChatMessage, Widget
from app.agents import orchestrator as orch


router = APIRouter(prefix="/confirm", tags=["confirm"])


class ConfirmRequest(BaseModel):
    session_id: str
    doc_type: str
    fields: dict


@router.post("", response_model=ChatResponse)
async def confirm(req: ConfirmRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if req.doc_type not in ("aadhaar", "pan"):
        raise HTTPException(400, "doc_type must be 'aadhaar' or 'pan'")

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": req.session_id}}
        snap = await graph.aget_state(thread)
        state = dict(snap.values) if snap and snap.values else {}

        expected = f"wait_for_{req.doc_type}_confirm"
        if state.get("next_required") != expected:
            raise HTTPException(409, f"Not ready to confirm {req.doc_type}. Current step: {state.get('next_required')}")

        # Update documents row with confirmed_json.
        from app.agents.intake import mask_aadhaar
        confirmed = dict(req.fields)
        if req.doc_type == "aadhaar" and confirmed.get("aadhaar_number"):
            confirmed["aadhaar_number"] = mask_aadhaar(confirmed["aadhaar_number"])

        await db.execute(
            update(m.Document)
            .where(m.Document.session_id == uuid.UUID(req.session_id),
                   m.Document.doc_type == req.doc_type)
            .values(confirmed_json=confirmed, confirmed_at=datetime.now(timezone.utc))
        )
        await db.commit()

        # Update in-memory state.
        slot = state.get(req.doc_type, {})
        slot["confirmed_json"] = confirmed
        state[req.doc_type] = slot

        # Advance: aadhaar_confirm → wait_for_pan_image; pan_confirm → cross_validate
        if req.doc_type == "aadhaar":
            state["next_required"] = "wait_for_pan_image"
        else:
            state["next_required"] = "cross_validate"

        new_state = await graph.ainvoke(state, config=thread)

        reply = await orch.generate_assistant_reply(
            request.app.state.ollama, state.get("language", "en"), new_state["next_required"]
        )
        widget = orch.widget_for(new_state["next_required"], new_state)
        assistant_msg = {"role": "assistant", "content": reply}
        if widget:
            assistant_msg["widget"] = widget
        new_state["messages"].append(assistant_msg)

        await graph.aupdate_state(thread, new_state)

        sess_uuid = uuid.UUID(req.session_id)
        from sqlalchemy import select, func as sqlfunc
        count = (await db.execute(
            select(sqlfunc.count()).select_from(m.Message).where(m.Message.session_id == sess_uuid)
        )).scalar_one()
        db.add(m.Message(session_id=sess_uuid, seq=count, role="assistant",
                         content=reply, widget=widget))
        await db.commit()

    return ChatResponse(
        session_id=req.session_id,
        messages=[ChatMessage(role="assistant", content=reply,
                              widget=Widget(**widget) if widget else None)],
        next_required=new_state["next_required"],
        language=state.get("language", "en"),
    )
```

- [ ] **Step 2: Register in `main.py`**

```python
from app.routers import confirm as confirm_router
app.include_router(confirm_router.router)
```

- [ ] **Step 3: Smoke test**

```bash
docker compose restart api
sleep 5
# Continue the session from Task 29: confirm the Aadhaar
curl -s -X POST http://localhost:8000/confirm \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"doc_type\":\"aadhaar\",\"fields\":{\"name\":\"Asha Sharma\",\"dob\":\"01/01/1990\",\"gender\":\"Female\",\"aadhaar_number\":\"XXXX XXXX 1234\",\"address\":\"Mumbai, Maharashtra\"}}" | python -m json.tool
```

Expected: `next_required: "wait_for_pan_image"` with an `upload` widget.

Verify: `SELECT confirmed_json IS NOT NULL FROM documents WHERE doc_type='aadhaar';` → true.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/routers/confirm.py apps/api/app/main.py
git commit -m "feat(api): /confirm route for editable-card confirmation"
```

---

## Phase 8 — Validation Agent

**Goal:** Replace the `validate` stub with real cross-document validation (name Jaccard, DOB exact, doc-type sanity, OCR confidence weighting). Persists to `validation_results`.

**Verify at end:** After PAN confirm, state has a populated `cross_validation` with `overall_score` and per-check breakdown, and the row exists in Postgres.

---

### Task 31: Normalisation + Jaccard + DOB comparison

**Files:**
- Create: `apps/api/app/agents/validation.py`
- Test: `apps/api/tests/agents/test_validation_math.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/agents/test_validation_math.py
from app.agents.validation import (
    normalize_name, jaccard, normalize_dob, check_name, check_dob,
)


def test_normalize_name_strips_titles():
    assert normalize_name("Mr. Asha Sharma") == "asha sharma"
    assert normalize_name("श्री Asha Sharma") == "asha sharma"
    assert normalize_name("Kumari Asha") == "asha"


def test_jaccard_full_match():
    assert jaccard("asha sharma", "asha sharma") == 1.0


def test_jaccard_partial_match():
    # "asha sharma" vs "asha" → 1/2 = 0.5
    assert abs(jaccard("asha sharma", "asha") - 0.5) < 1e-9


def test_jaccard_zero_when_disjoint():
    assert jaccard("asha", "rahul") == 0.0


def test_normalize_dob_accepts_various_formats():
    assert normalize_dob("01/01/1990") == "01/01/1990"
    assert normalize_dob("1-1-1990") == "01/01/1990"
    assert normalize_dob("1990-01-01") == "01/01/1990"


def test_check_name_pass_on_high_similarity():
    c = check_name("Mr. Asha Sharma", "Asha Sharma")
    assert c["status"] == "pass"
    assert c["score"] >= 0.9


def test_check_dob_fail_on_mismatch():
    c = check_dob("01/01/1990", "02/01/1990")
    assert c["status"] == "fail"
```

- [ ] **Step 2: Run, see failures**

Run: `cd apps/api && uv run pytest tests/agents/test_validation_math.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `apps/api/app/agents/validation.py`**

```python
# apps/api/app/agents/validation.py
from __future__ import annotations
import re
from datetime import datetime
from typing import Literal

CheckStatus = Literal["pass", "fail", "warn", "skip"]


# Indian honorifics + common titles. Expand as needed.
_TITLES = [
    "mr", "mrs", "ms", "miss", "dr", "shri", "smt", "km", "kumari",
    "श्री", "श्रीमती", "श्रीमान", "कुमारी", "कुमार",
]
_TITLE_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(t) for t in _TITLES) + r")[\.\s]+",
    flags=re.IGNORECASE,
)


def normalize_name(s: str | None) -> str:
    if not s:
        return ""
    t = s.strip()
    # Strip leading title, once
    t = _TITLE_RE.sub("", t)
    # Lowercase Latin; Devanagari is already case-insensitive
    t = t.lower()
    # Remove punctuation
    t = re.sub(r"[^\w\sऀ-ॿ]", " ", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


_DOB_PATTERNS = [
    ("%d/%m/%Y",),
    ("%d-%m-%Y",),
    ("%Y-%m-%d",),
    ("%d %m %Y",),
]


def normalize_dob(s: str | None) -> str:
    if not s:
        return ""
    t = s.strip()
    for (pat,) in _DOB_PATTERNS:
        try:
            d = datetime.strptime(t, pat)
            return d.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return ""


def check_name(aadhaar_name: str | None, pan_name: str | None) -> dict:
    an = normalize_name(aadhaar_name or "")
    pn = normalize_name(pan_name or "")
    if not an or not pn:
        return {"name": "name_match", "status": "skip", "score": 0.5,
                "detail": "one or both names missing"}
    score = jaccard(an, pn)
    status: CheckStatus = "pass" if score >= 0.75 else ("warn" if score >= 0.5 else "fail")
    return {"name": "name_match", "status": status, "score": score,
            "detail": f"{an!r} vs {pn!r}"}


def check_dob(aadhaar_dob: str | None, pan_dob: str | None) -> dict:
    ad = normalize_dob(aadhaar_dob or "")
    pd = normalize_dob(pan_dob or "")
    if not ad or not pd:
        return {"name": "dob_match", "status": "skip", "score": 0.5,
                "detail": "one or both DOBs missing"}
    match = ad == pd
    return {"name": "dob_match",
            "status": "pass" if match else "fail",
            "score": 1.0 if match else 0.0,
            "detail": f"{ad} vs {pd}"}


def check_doctype(aadhaar: dict, pan: dict) -> dict:
    ok = aadhaar.get("doc_type") == "aadhaar" and pan.get("doc_type") == "pan"
    return {"name": "doc_type_sanity",
            "status": "pass" if ok else "fail",
            "score": 1.0 if ok else 0.0,
            "detail": f"aadhaar={aadhaar.get('doc_type')}, pan={pan.get('doc_type')}"}


def check_ocr_confidence(aadhaar_conf: str, pan_conf: str) -> dict:
    scale = {"high": 1.0, "medium": 0.6, "low": 0.2}
    score = (scale.get(aadhaar_conf, 0.2) + scale.get(pan_conf, 0.2)) / 2
    status: CheckStatus = "pass" if score >= 0.7 else ("warn" if score >= 0.4 else "fail")
    return {"name": "ocr_confidence", "status": status, "score": score,
            "detail": f"aadhaar={aadhaar_conf}, pan={pan_conf}"}


WEIGHTS = {"name_match": 0.5, "dob_match": 0.3, "doc_type_sanity": 0.1, "ocr_confidence": 0.1}


def cross_validate(aadhaar: dict, pan: dict, aadhaar_conf: str, pan_conf: str) -> dict:
    """Aadhaar/pan are the *confirmed* field dicts (fall back to extracted if not confirmed).

    Returns {overall_score (0..100), checks: [...]}.
    """
    checks = [
        check_name(aadhaar.get("name"), pan.get("name")),
        check_dob(aadhaar.get("dob"), pan.get("dob")),
        check_doctype(aadhaar, pan),
        check_ocr_confidence(aadhaar_conf, pan_conf),
    ]
    total = sum(c["score"] * WEIGHTS[c["name"]] for c in checks)
    return {"overall_score": round(total * 100, 1), "checks": checks}
```

- [ ] **Step 4: Run tests**

Run: `cd apps/api && uv run pytest tests/agents/test_validation_math.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/agents/validation.py apps/api/tests/agents/test_validation_math.py
git commit -m "feat(agents): validation math — jaccard, dob, weighted scoring"
```

---

### Task 32: Validation node + persistence

**Files:**
- Modify: `apps/api/app/agents/validation.py` (add `run_validation`)
- Modify: `apps/api/app/graph/builder.py` (replace `n_stub_validate`)

- [ ] **Step 1: Append to `apps/api/app/agents/validation.py`**

```python
# validation.py (continued)
import uuid
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.graph.state import KYCState


async def run_validation(state: KYCState, db: AsyncSession) -> KYCState:
    aadhaar_slot = state.get("aadhaar", {})
    pan_slot = state.get("pan", {})
    aadhaar = aadhaar_slot.get("confirmed_json") or aadhaar_slot.get("extracted_json") or {}
    pan = pan_slot.get("confirmed_json") or pan_slot.get("extracted_json") or {}
    aa_conf = aadhaar_slot.get("ocr_confidence", "low")
    pan_conf = pan_slot.get("ocr_confidence", "low")

    result = cross_validate(aadhaar, pan, aa_conf, pan_conf)
    state["cross_validation"] = result

    session_uuid = uuid.UUID(state["session_id"])
    stmt = pg_insert(m.ValidationResult).values(
        session_id=session_uuid,
        overall_score=result["overall_score"],
        checks=result["checks"],
    ).on_conflict_do_update(
        index_elements=["session_id"],
        set_={"overall_score": result["overall_score"], "checks": result["checks"]},
    )
    await db.execute(stmt)
    await db.commit()

    # Carry over any critical fails as flags (surfaces at decision time).
    flags = state.setdefault("flags", [])
    for c in result["checks"]:
        if c["status"] == "fail" and c["name"] in ("name_match", "dob_match"):
            flags.append(f"{c['name']}_critical_fail")

    state["next_required"] = "ask_selfie"
    return state
```

- [ ] **Step 2: Replace `n_stub_validate` in `builder.py`**

```python
# builder.py
from app.agents.validation import run_validation


async def n_validate(state: KYCState) -> KYCState:
    async with SessionLocal() as db:
        state = await run_validation(state, db)
    state["next_required"] = "wait_for_selfie"
    return state
```

And wire:

```python
    g.add_node("validate", n_validate)
```

- [ ] **Step 3: Smoke test** — upload + confirm both docs, then the graph should advance to `wait_for_selfie` with `cross_validation` populated. Check DB:

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT overall_score, jsonb_array_length(checks) FROM validation_results;"
```

Expected: one row with `overall_score > 0` and 4 checks.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/agents/validation.py apps/api/app/graph/builder.py
git commit -m "feat(agents): validation node + persistence"
```

---

## Phase 9 — Biometric Agent + Selfie Capture

**Goal:** Real DeepFace face-match and gender analysis wired to a `/capture` route for the selfie. Persists to `selfies` and `face_checks`. Crops Aadhaar photo for the face comparison.

**Verify at end:** A selfie captured via `/capture` triggers DeepFace, stores rows, and advances `next_required` to `geolocation`.

---

### Task 33: DeepFace runner (lazy import)

**Files:**
- Create: `apps/api/app/services/deepface_runner.py`

- [ ] **Step 1: Write the runner**

```python
# apps/api/app/services/deepface_runner.py
from __future__ import annotations
from pathlib import Path
from typing import Any


def verify_faces(selfie_path: str | Path, reference_path: str | Path) -> dict:
    """Wrap DeepFace.verify. Imported lazily — pulls TensorFlow at import time."""
    from deepface import DeepFace  # noqa: WPS433

    try:
        result = DeepFace.verify(
            img1_path=str(reference_path),
            img2_path=str(selfie_path),
            model_name="VGG-Face",
            detector_backend="opencv",
            distance_metric="cosine",
            enforce_detection=False,
        )
        distance = float(result.get("distance", 1.0))
        threshold = float(result.get("threshold", 0.4))
        verified = bool(result.get("verified", False))
        confidence = max(0.0, min(100.0, (1 - distance / threshold) * 100))
        return {
            "verified": verified,
            "distance": distance,
            "confidence": round(confidence, 2),
            "threshold": threshold,
            "faces_detected": True,
        }
    except ValueError as exc:
        # Usually "Face could not be detected"
        return {"verified": False, "distance": 1.0, "confidence": 0.0, "faces_detected": False,
                "error": str(exc)}


def analyze_gender(selfie_path: str | Path) -> dict:
    from deepface import DeepFace
    try:
        res = DeepFace.analyze(
            img_path=str(selfie_path),
            actions=["gender"],
            detector_backend="opencv",
            enforce_detection=False,
        )
        if isinstance(res, list) and res:
            res = res[0]
        dominant = res.get("dominant_gender") or "unknown"
        return {"predicted_gender": dominant.lower(), "raw": res}
    except Exception as exc:
        return {"predicted_gender": None, "error": str(exc)}
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/services/deepface_runner.py
git commit -m "feat(services): deepface runner with lazy import"
```

---

### Task 34: Biometric node + `/capture` route

**Files:**
- Create: `apps/api/app/agents/biometric.py`
- Create: `apps/api/app/routers/capture.py`
- Modify: `apps/api/app/graph/builder.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Write `apps/api/app/agents/biometric.py`**

```python
# apps/api/app/agents/biometric.py
from __future__ import annotations
import uuid
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.graph.state import KYCState
from app.services.deepface_runner import verify_faces, analyze_gender


def _normalize_gender(s: str | None) -> str | None:
    if not s:
        return None
    t = s.strip().lower()
    if t.startswith("m"):
        return "man"
    if t.startswith("f") or t.startswith("w"):
        return "woman"
    return t


async def run_biometric(state: KYCState, db: AsyncSession) -> KYCState:
    selfie_slot = state.get("selfie", {})
    selfie_path = selfie_slot.get("file_path")
    aadhaar_slot = state.get("aadhaar", {})
    # Reference face: cropped Aadhaar photo if available, otherwise the whole Aadhaar image.
    reference = aadhaar_slot.get("photo_path") or aadhaar_slot.get("file_path")

    if not selfie_path or not reference:
        state["next_required"] = "ask_selfie"
        return state

    verify_res = verify_faces(selfie_path, reference)

    aadhaar_fields = aadhaar_slot.get("confirmed_json") or aadhaar_slot.get("extracted_json") or {}
    aadhaar_gender = _normalize_gender(aadhaar_fields.get("gender"))
    gender_res = analyze_gender(selfie_path) if verify_res.get("faces_detected") else {"predicted_gender": None}
    predicted = gender_res.get("predicted_gender")
    gender_match = None
    if aadhaar_gender and predicted:
        gender_match = (aadhaar_gender == predicted)

    # Persist selfie row
    session_uuid = uuid.UUID(state["session_id"])
    selfie_row = m.Selfie(session_id=session_uuid, file_path=selfie_path)
    db.add(selfie_row)
    await db.flush()

    face_stmt = pg_insert(m.FaceCheck).values(
        session_id=session_uuid,
        selfie_id=selfie_row.id,
        verified=bool(verify_res["verified"]),
        distance=float(verify_res["distance"]),
        confidence=float(verify_res["confidence"]),
        predicted_gender=predicted,
        aadhaar_gender=aadhaar_gender,
        gender_match=gender_match,
        model="VGG-Face",
    ).on_conflict_do_update(
        index_elements=["session_id", "selfie_id"],
        set_={"verified": bool(verify_res["verified"]),
              "distance": float(verify_res["distance"]),
              "confidence": float(verify_res["confidence"]),
              "predicted_gender": predicted,
              "aadhaar_gender": aadhaar_gender,
              "gender_match": gender_match},
    )
    await db.execute(face_stmt)
    await db.commit()

    state["face_check"] = {
        "verified": verify_res["verified"],
        "confidence": verify_res["confidence"],
        "faces_detected": verify_res.get("faces_detected", True),
        "predicted_gender": predicted,
        "aadhaar_gender": aadhaar_gender,
        "gender_match": gender_match,
    }
    state["selfie"] = {"file_path": selfie_path, "id": str(selfie_row.id)}

    flags = state.setdefault("flags", [])
    if not verify_res.get("faces_detected"):
        # Send user back to retake.
        state["next_required"] = "ask_selfie"
        return state
    if gender_match is False:
        flags.append("gender_mismatch")
    if verify_res["confidence"] < 60 and not verify_res["verified"]:
        flags.append("face_verification_low_confidence")

    state["next_required"] = "geolocation"
    return state
```

- [ ] **Step 2: Replace `n_stub_biometric` in `builder.py`**

```python
from app.agents.biometric import run_biometric


async def n_biometric(state: KYCState) -> KYCState:
    async with SessionLocal() as db:
        return await run_biometric(state, db)


# in build_graph():
    g.add_node("biometric", n_biometric)
```

- [ ] **Step 3: Write `apps/api/app/routers/capture.py`**

```python
# apps/api/app/routers/capture.py
from __future__ import annotations
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.db import models as m
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatResponse, ChatMessage, Widget
from app.agents import orchestrator as orch


router = APIRouter(prefix="/capture", tags=["capture"])


@router.post("", response_model=ChatResponse)
async def capture(
    request: Request,
    session_id: str = Form(...),
    target: str = Form(...),  # "selfie" | "aadhaar" | "pan"
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if target not in ("selfie", "aadhaar", "pan"):
        raise HTTPException(400, f"Unknown target: {target}")
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": session_id}}
        snap = await graph.aget_state(thread)
        state = dict(snap.values) if snap and snap.values else {}

        # Expectation check
        expected_map = {
            "selfie": "wait_for_selfie",
            "aadhaar": "wait_for_aadhaar_image",
            "pan": "wait_for_pan_image",
        }
        if state.get("next_required") != expected_map[target]:
            raise HTTPException(409, f"Not ready for {target}. Current step: {state.get('next_required')}")

        s = get_settings()
        upload_dir = Path(s.upload_dir) / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "").suffix or ".jpg"
        dest = upload_dir / f"{target}{suffix}"
        dest.write_bytes(await file.read())

        if target == "selfie":
            state["selfie"] = {"file_path": str(dest)}
            state["next_required"] = "biometric"
        else:
            slot = state.get(target, {}) or {}
            slot["file_path"] = str(dest)
            state[target] = slot
            state["next_required"] = f"ocr_{target}"

        state["session_id"] = session_id
        state.setdefault("messages", [])

        new_state = await graph.ainvoke(state, config=thread)

        reply = await orch.generate_assistant_reply(
            request.app.state.ollama, state.get("language", "en"), new_state["next_required"]
        )
        widget = orch.widget_for(new_state["next_required"], new_state)
        assistant_msg = {"role": "assistant", "content": reply}
        if widget:
            assistant_msg["widget"] = widget
        new_state["messages"].append(assistant_msg)

        await graph.aupdate_state(thread, new_state)

        sess_uuid = uuid.UUID(session_id)
        count = (await db.execute(
            select(sqlfunc.count()).select_from(m.Message).where(m.Message.session_id == sess_uuid)
        )).scalar_one()
        db.add(m.Message(session_id=sess_uuid, seq=count, role="assistant",
                         content=reply, widget=widget))
        await db.commit()

    return ChatResponse(
        session_id=session_id,
        messages=[ChatMessage(role="assistant", content=reply,
                              widget=Widget(**widget) if widget else None)],
        next_required=new_state["next_required"],
        language=state.get("language", "en"),
    )
```

- [ ] **Step 4: Register in `main.py`**

```python
from app.routers import capture as capture_router
app.include_router(capture_router.router)
```

- [ ] **Step 5: Smoke test**

Continue from the Phase 8 flow. With a selfie image at `/tmp/selfie.jpg`:

```bash
curl -s -X POST http://localhost:8000/capture \
  -F "session_id=$SID" -F "target=selfie" \
  -F "file=@/tmp/selfie.jpg" | python -m json.tool
```

Expected: response shows the next step (should now be past biometric). First call may be slow (DeepFace loads VGG-Face weights the first time — ~30-60 s).

Verify DB:

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT verified, confidence, predicted_gender, aadhaar_gender, gender_match FROM face_checks;"
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/agents/biometric.py apps/api/app/routers/capture.py \
        apps/api/app/graph/builder.py apps/api/app/main.py
git commit -m "feat(agents): biometric node + /capture route for selfie"
```

---

## Phase 10 — Geolocation Agent

**Goal:** Real ipwhois lookup; LLM extracts city/state from the Aadhaar address; country gate; soft-flag city/state mismatch. Persists to `ip_checks`.

**Verify at end:** A session with Aadhaar+PAN+selfie done has an `ip_checks` row; non-IN country yields `rejected` immediately.

---

### Task 35: Address → city/state extractor (LLM)

**Files:**
- Create: `apps/api/app/agents/geolocation.py`
- Test: `apps/api/tests/agents/test_geolocation_extract.py`

- [ ] **Step 1: Write the test (mocking the LLM)**

```python
# apps/api/tests/agents/test_geolocation_extract.py
import pytest
from unittest.mock import AsyncMock

from app.agents.geolocation import extract_city_state


@pytest.mark.asyncio
async def test_extract_city_state_parses_json():
    fake = AsyncMock()
    fake.chat = AsyncMock(return_value='{"city": "Mumbai", "state": "Maharashtra"}')
    result = await extract_city_state(fake, "123 Main Rd, Andheri, Mumbai 400058, Maharashtra, India")
    assert result == {"city": "Mumbai", "state": "Maharashtra"}


@pytest.mark.asyncio
async def test_extract_city_state_handles_fenced_json():
    fake = AsyncMock()
    fake.chat = AsyncMock(return_value='```json\n{"city": "Bengaluru", "state": "Karnataka"}\n```')
    result = await extract_city_state(fake, "some address Bengaluru KA")
    assert result["city"] == "Bengaluru"


@pytest.mark.asyncio
async def test_extract_city_state_returns_empty_on_bad_json():
    fake = AsyncMock()
    fake.chat = AsyncMock(return_value="not json at all")
    result = await extract_city_state(fake, "address")
    assert result == {"city": "", "state": ""}
```

- [ ] **Step 2: Run, see failure**

Run: `cd apps/api && uv run pytest tests/agents/test_geolocation_extract.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `apps/api/app/agents/geolocation.py`**

```python
# apps/api/app/agents/geolocation.py
from __future__ import annotations
import json
from app.services.ollama_client import OllamaClient, strip_json_fence


_EXTRACT_PROMPT = """Given an Indian address, extract the city and state.
Reply with ONLY a JSON object: {"city": "", "state": ""}. Use empty strings if unsure.
Normalise to commonly used English spellings (e.g. "Bengaluru", not "Bangaluru"; "Mumbai", not "Bombay")."""


async def extract_city_state(ollama: OllamaClient, address: str) -> dict:
    if not address:
        return {"city": "", "state": ""}
    try:
        raw = await ollama.chat(
            [{"role": "system", "content": _EXTRACT_PROMPT},
             {"role": "user", "content": address}],
            json_mode=True,
            temperature=0.0,
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = strip_json_fence(raw)
        return {"city": data.get("city", ""), "state": data.get("state", "")}
    except Exception:
        return {"city": "", "state": ""}


def _case_insensitive_eq(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().casefold() == b.strip().casefold()
```

- [ ] **Step 4: Run tests**

Run: `cd apps/api && uv run pytest tests/agents/test_geolocation_extract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/agents/geolocation.py apps/api/tests/agents/test_geolocation_extract.py
git commit -m "feat(agents): geolocation address → city/state extractor"
```

---

### Task 36: Geolocation node + `/chat` passes client IP

**Files:**
- Modify: `apps/api/app/agents/geolocation.py` (add `run_geolocation`)
- Modify: `apps/api/app/graph/builder.py`
- Modify: `apps/api/app/routers/chat.py`, `upload.py`, `capture.py`, `confirm.py` (pass client IP into state)

- [ ] **Step 1: Append to `geolocation.py`**

```python
# geolocation.py (continued)
import uuid
import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import models as m
from app.graph.state import KYCState
from app.services.ipwhois_client import IPWhoisClient


async def run_geolocation(state: KYCState, db: AsyncSession, ollama: OllamaClient) -> KYCState:
    ip = state.get("_client_ip") or "8.8.8.8"  # fallback
    async with httpx.AsyncClient() as http:
        ipc = IPWhoisClient(http)
        try:
            lookup = await ipc.lookup(ip)
        except Exception as exc:
            lookup = {"ip": ip, "country": None, "country_code": None, "city": None,
                      "region": None, "raw": {"error": str(exc)}}

    country_ok = (lookup.get("country_code") or "").upper() == "IN"

    aadhaar_fields = state.get("aadhaar", {}).get("confirmed_json") \
                     or state.get("aadhaar", {}).get("extracted_json") or {}
    extracted = await extract_city_state(ollama, aadhaar_fields.get("address", ""))
    aadhaar_city = extracted["city"]
    aadhaar_state = extracted["state"]

    city_match = _case_insensitive_eq(lookup.get("city"), aadhaar_city) if aadhaar_city else None
    state_match = _case_insensitive_eq(lookup.get("region"), aadhaar_state) if aadhaar_state else None

    session_uuid = uuid.UUID(state["session_id"])
    stmt = pg_insert(m.IPCheck).values(
        session_id=session_uuid,
        ip=ip,
        country=lookup.get("country"),
        country_code=lookup.get("country_code"),
        city=lookup.get("city"),
        region=lookup.get("region"),
        aadhaar_city=aadhaar_city or None,
        aadhaar_state=aadhaar_state or None,
        city_match=city_match,
        state_match=state_match,
        country_ok=country_ok,
        raw=lookup.get("raw") or {},
    ).on_conflict_do_update(
        index_elements=["session_id"],
        set_={"ip": ip, "country": lookup.get("country"),
              "country_code": lookup.get("country_code"),
              "city": lookup.get("city"), "region": lookup.get("region"),
              "aadhaar_city": aadhaar_city or None, "aadhaar_state": aadhaar_state or None,
              "city_match": city_match, "state_match": state_match,
              "country_ok": country_ok, "raw": lookup.get("raw") or {}},
    )
    await db.execute(stmt)
    await db.commit()

    state["ip_check"] = {
        "ip": ip, "country_code": lookup.get("country_code"),
        "country_ok": country_ok, "city": lookup.get("city"), "region": lookup.get("region"),
        "city_match": city_match, "state_match": state_match,
    }

    flags = state.setdefault("flags", [])
    if not country_ok:
        flags.append("ip_country_not_india")
        # Hard fail: go straight to decide.
        state["decision"] = "rejected"
        state["decision_reason"] = "IP geolocation indicates a non-India country."
        state["next_required"] = "decide"
        return state

    if city_match is False:
        flags.append("ip_city_mismatch")
    if state_match is False:
        flags.append("ip_state_mismatch")

    state["next_required"] = "decide"
    return state
```

- [ ] **Step 2: Replace `n_stub_geolocation` in `builder.py`**

```python
from app.agents.geolocation import run_geolocation


async def n_geolocation(state: KYCState) -> KYCState:
    import httpx
    from app.config import get_settings
    from app.services.ollama_client import OllamaClient
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=120) as http:
        ollama = OllamaClient(http, s.chat_model, s.ocr_model, s.embed_model)
        async with SessionLocal() as db:
            return await run_geolocation(state, db, ollama)


# in build_graph():
    g.add_node("geolocation", n_geolocation)
```

- [ ] **Step 3: Thread client IP through the routers**

In `chat.py`, `upload.py`, `capture.py`, `confirm.py`, before invoking the graph, add:

```python
state["_client_ip"] = request.client.host if request.client else "8.8.8.8"
```

(Include in all four routers, right after `state = dict(snap.values) if snap and snap.values else {}` and before the graph invocation.)

- [ ] **Step 4: Smoke test**

End-to-end run should now show `next_required: "decide"` after selfie + biometric. Verify row:

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT ip, country_code, country_ok, city_match, state_match FROM ip_checks;"
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/agents/geolocation.py apps/api/app/graph/builder.py \
        apps/api/app/routers/chat.py apps/api/app/routers/upload.py \
        apps/api/app/routers/capture.py apps/api/app/routers/confirm.py
git commit -m "feat(agents): geolocation node; client IP threaded through routers"
```

---

## Phase 11 — Decision Agent

**Goal:** Replace the decision stub with the real thresholded synthesis. Persists to `kyc_records`. Updates the session status to `completed`. Emits the `verdict` widget.

**Verify at end:** A full end-to-end run produces an `approved`/`flagged`/`rejected` decision matching the thresholds.

---

### Task 37: Decision thresholds

**Files:**
- Create: `apps/api/app/agents/decision.py`
- Test: `apps/api/tests/agents/test_decision_thresholds.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/agents/test_decision_thresholds.py
from app.agents.decision import compute_decision


def _state(score=85, face_ok=True, face_detected=True, critical_fails=None, country_ok=True, flags=None):
    return {
        "cross_validation": {
            "overall_score": score,
            "checks": [
                {"name": "name_match", "status": "fail" if critical_fails and "name" in critical_fails else "pass", "score": 0.9},
                {"name": "dob_match", "status": "fail" if critical_fails and "dob" in critical_fails else "pass", "score": 1.0},
            ],
        },
        "face_check": {"verified": face_ok, "confidence": 85 if face_ok else 30, "faces_detected": face_detected},
        "ip_check": {"country_ok": country_ok},
        "flags": flags or [],
    }


def test_approved_when_score_high_and_face_ok():
    d = compute_decision(_state(score=85))
    assert d["decision"] == "approved"


def test_rejected_on_name_critical_fail():
    d = compute_decision(_state(critical_fails=["name"]))
    assert d["decision"] == "rejected"
    assert "name_match_critical_fail" in d["flags"] or any("name" in f for f in d["flags"])


def test_rejected_on_country_mismatch():
    d = compute_decision(_state(country_ok=False))
    assert d["decision"] == "rejected"


def test_flagged_on_mid_score():
    d = compute_decision(_state(score=65))
    assert d["decision"] == "flagged"


def test_rejected_on_low_score():
    d = compute_decision(_state(score=20))
    assert d["decision"] == "rejected"
```

- [ ] **Step 2: Run, see failures**

Run: `cd apps/api && uv run pytest tests/agents/test_decision_thresholds.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `apps/api/app/agents/decision.py`**

```python
# apps/api/app/agents/decision.py
from __future__ import annotations
import uuid
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.graph.state import KYCState


def _critical_fails(checks: list[dict]) -> list[str]:
    fails: list[str] = []
    for c in checks or []:
        if c.get("status") == "fail" and c.get("name") in ("name_match", "dob_match"):
            fails.append(f"{c['name']}_critical_fail")
    return fails


def compute_decision(state: KYCState) -> dict:
    cv = state.get("cross_validation", {}) or {}
    score = float(cv.get("overall_score", 0))
    crit = _critical_fails(cv.get("checks", []))

    face = state.get("face_check", {}) or {}
    face_ok = bool(face.get("verified")) or float(face.get("confidence", 0)) >= 60
    faces_detected = face.get("faces_detected", True)

    ip = state.get("ip_check", {}) or {}
    country_ok = bool(ip.get("country_ok", True))

    flags = list(state.get("flags", []))
    flags.extend(crit)
    recs: list[str] = []

    if not country_ok:
        return {
            "decision": "rejected",
            "decision_reason": "Your IP appears to be outside India. KYC for Indian residents requires an Indian IP.",
            "flags": flags + ["ip_country_not_india"],
            "recommendations": ["Complete your KYC while connected from within India."],
        }
    if crit:
        return {
            "decision": "rejected",
            "decision_reason": "Critical mismatch detected between your Aadhaar and PAN details.",
            "flags": flags,
            "recommendations": ["Please ensure the name and date of birth on your Aadhaar and PAN match."],
        }
    if not faces_detected:
        return {
            "decision": "rejected",
            "decision_reason": "We couldn't detect a face in your selfie.",
            "flags": flags + ["no_face_detected"],
            "recommendations": ["Please retake your selfie in good lighting, with your face centred."],
        }

    if score >= 80 and face_ok:
        return {
            "decision": "approved",
            "decision_reason": "Your Aadhaar and PAN details match and your selfie has been verified.",
            "flags": flags,
            "recommendations": [],
        }
    if score >= 60 or (score >= 40 and not crit):
        recs.append("A human reviewer will take a second look at your submission.")
        if not face_ok:
            recs.append("You may also be asked to retake your selfie.")
        return {
            "decision": "flagged",
            "decision_reason": "Your submission is borderline; we've flagged it for manual review.",
            "flags": flags,
            "recommendations": recs,
        }
    return {
        "decision": "rejected",
        "decision_reason": "Your submission didn't meet our verification thresholds.",
        "flags": flags,
        "recommendations": ["Please re-check your documents and try again with clearer images."],
    }


async def run_decision(state: KYCState, db: AsyncSession) -> KYCState:
    # If geolocation already pre-set a rejection (country gate), keep it.
    if state.get("decision") == "rejected" and state.get("decision_reason"):
        result = {
            "decision": state["decision"],
            "decision_reason": state["decision_reason"],
            "flags": list(state.get("flags", [])),
            "recommendations": state.get("recommendations", []) or [
                "Complete your KYC while connected from within India."
            ],
        }
    else:
        result = compute_decision(state)

    state["decision"] = result["decision"]
    state["decision_reason"] = result["decision_reason"]
    state["flags"] = result["flags"]
    state["recommendations"] = result["recommendations"]

    session_uuid = uuid.UUID(state["session_id"])
    stmt = pg_insert(m.KYCRecord).values(
        session_id=session_uuid,
        decision=result["decision"],
        decision_reason=result["decision_reason"],
        flags=result["flags"],
        recommendations=result["recommendations"],
    ).on_conflict_do_update(
        index_elements=["session_id"],
        set_={"decision": result["decision"],
              "decision_reason": result["decision_reason"],
              "flags": result["flags"],
              "recommendations": result["recommendations"]},
    )
    await db.execute(stmt)
    await db.execute(
        update(m.Session).where(m.Session.id == session_uuid).values(status="completed")
    )
    await db.commit()

    state["next_required"] = "done"
    return state
```

- [ ] **Step 4: Run tests**

Run: `cd apps/api && uv run pytest tests/agents/test_decision_thresholds.py -v`
Expected: PASS.

- [ ] **Step 5: Replace `n_stub_decide` in `builder.py`**

```python
from app.agents.decision import run_decision


async def n_decide(state: KYCState) -> KYCState:
    async with SessionLocal() as db:
        return await run_decision(state, db)


# in build_graph():
    g.add_node("decide", n_decide)
```

- [ ] **Step 6: Update `orchestrator.widget_for` to emit the verdict widget**

Modify `orchestrator.py`, the `widget_for` function, to add a `done` case:

```python
    if next_required == "done" and state:
        return {
            "type": "verdict",
            "decision": state.get("decision", "pending"),
            "decision_reason": state.get("decision_reason", ""),
            "checks": state.get("cross_validation", {}).get("checks", []),
            "flags": state.get("flags", []),
            "recommendations": state.get("recommendations", []),
        }
```

- [ ] **Step 7: Smoke test the full flow**

Re-run the end-to-end cURL walk. The final response should have `next_required: "done"` and a `verdict` widget.

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT decision, decision_reason FROM kyc_records;"
```

Expected: one row per completed session.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/agents/decision.py apps/api/app/graph/builder.py \
        apps/api/app/agents/orchestrator.py apps/api/tests/agents/test_decision_thresholds.py
git commit -m "feat(agents): decision thresholds + verdict widget"
git tag phase-11-complete
```

---

## Phase 12 — RAG + Compliance Agent

**Goal:** Seed the Qdrant corpus with RBI Master Direction excerpts and a project FAQ. Provide a `reindex_rag.py` script. Implement the Compliance agent as an in-line FAQ handler inside the `/chat` route, replacing the placeholder answer.

**Verify at end:** `docker compose exec api python -m app.scripts.reindex_rag` indexes the corpus; `POST /chat {text: "is my data safe?"}` returns a cited, grounded answer; row lands in `compliance_qna`.

---

### Task 38: Seed corpus content

**Files:**
- Create: `infra/rag-corpus/rbi-master-direction-kyc-excerpts.md`
- Create: `infra/rag-corpus/project-faq.md`

- [ ] **Step 1: Write `rbi-master-direction-kyc-excerpts.md`**

Seed file with plain-text excerpts. Keep it short — a few hundred lines. Example:

```markdown
# RBI Master Direction — Know Your Customer (KYC) — selected excerpts

Source: Reserve Bank of India, "Master Direction — Know Your Customer (KYC) Direction, 2016" (as amended). This file contains educational excerpts only. For the authoritative text, see https://rbi.org.in/.

## Scope
These directions apply to every entity regulated by the Reserve Bank of India, including scheduled commercial banks, NBFCs, payment system operators, and authorised dealers.

## Customer Due Diligence (CDD)
Regulated entities shall obtain sufficient information to establish the identity of each customer. For individuals, the Officially Valid Documents (OVDs) include the Aadhaar number, passport, driving licence, voter's identity card, and PAN.

## Officially Valid Documents (OVDs)
An Officially Valid Document (OVD) is one of: (a) passport, (b) driving licence, (c) voter's identity card, (d) job card issued by NREGA signed by a State Government officer, (e) letter issued by the National Population Register, (f) Aadhaar letter subject to consent.

## Aadhaar & privacy
The Aadhaar number must not be stored in full by the regulated entity. Only the last four digits may be displayed; the preceding eight digits must be masked (e.g., XXXX XXXX 1234) in records, communications, and UI surfaces. Full Aadhaar storage is permitted only where specifically required by law.

## Video-based KYC (V-CIP)
V-CIP is a consent-based, facially authenticated, real-time verification process. The agent performing V-CIP shall verify the customer's identity via live video capture, PAN cross-reference, and location check. The customer's consent must be recorded.

## PAN requirement
Quoting the PAN is mandatory for specific transactions as listed by the CBDT, including opening of bank accounts. Where PAN is not available, Form 60 may be obtained.

## Data retention
Records of transactions and identification documents shall be preserved for a minimum of five years from the date of cessation of the business relationship or the date of the transaction, whichever is later.

## Periodic updation
Customer identification data shall be updated periodically — typically every two years for high-risk customers, eight years for medium-risk, and ten years for low-risk.
```

- [ ] **Step 2: Write `project-faq.md`**

```markdown
# Conversational KYC Agent — FAQ

## What is KYC?
"Know Your Customer" is the process financial institutions use to verify who you are before opening an account or letting you transact. In India it's mandated by the RBI and typically requires checking your Aadhaar and PAN.

## Why do you need my Aadhaar?
Aadhaar is an Officially Valid Document under the RBI Master Direction. We use it to confirm your name, date of birth, gender, and address. We never store the first eight digits of your Aadhaar number — only the last four.

## Why do you need my PAN?
PAN is required for most regulated financial transactions in India. We use it to cross-check that the name and date of birth on your Aadhaar match.

## Why a selfie?
The selfie is compared to the photo on your Aadhaar card so we can confirm that the documents belong to you.

## Is my data safe?
Everything is stored locally in the backing Postgres database for this demo. No third-party services other than ipwhois.io (which only sees your IP address) are contacted. The full Aadhaar number is masked before storage or display.

## How long does it take?
The typical flow is under two minutes once you have your Aadhaar, PAN, and a camera ready.

## I got "flagged" — what does that mean?
A flagged decision means your submission was borderline and needs a human reviewer. In this demo there is no reviewer dashboard yet — you'd be contacted by the real institution in practice.

## Which documents are supported?
Aadhaar and PAN for this demo. Passport, driving licence, and voter ID support are on the roadmap.
```

- [ ] **Step 3: Commit**

```bash
git add infra/rag-corpus/
git commit -m "feat(rag): seed corpus — RBI excerpts and project FAQ"
```

---

### Task 39: Seed / reindex script

**Files:**
- Create: `apps/api/scripts/__init__.py` (empty)
- Create: `apps/api/scripts/reindex_rag.py`

- [ ] **Step 1: Write the script**

```python
# apps/api/scripts/reindex_rag.py
"""Index the RAG corpus into Qdrant.

Usage (inside the api container):
    uv run python -m app.scripts.reindex_rag
"""
from __future__ import annotations
import asyncio
import hashlib
import os
from pathlib import Path

import httpx
from qdrant_client import AsyncQdrantClient

from app.config import get_settings
from app.services.ollama_client import OllamaClient
from app.services.rag import RAGService


CORPUS_DIR = Path(os.environ.get("RAG_CORPUS_DIR", "/corpus"))


def _chunk(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Fixed-size chunking with overlap. Splits on paragraph boundaries when possible."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = f"{buf}\n\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                # split a giant paragraph
                for i in range(0, len(p), max_chars - overlap):
                    chunks.append(p[i:i + max_chars])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _id_for(source: str, idx: int, text: str) -> str:
    h = hashlib.sha1(f"{source}:{idx}:{text[:64]}".encode()).hexdigest()[:16]
    return h


async def main() -> None:
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=120) as http:
        ollama = OllamaClient(http, s.chat_model, s.ocr_model, s.embed_model)
        q = AsyncQdrantClient(url=s.qdrant_url)

        # Probe the embed dimensionality with a tiny input
        sample_vec = await ollama.embed("dimension probe")
        dim = len(sample_vec)
        print(f"[reindex] embedding dim = {dim}")

        rag = RAGService(q, ollama)
        rag.collection = s.qdrant_collection
        await rag.ensure_collection(vector_size=dim)

        # Walk the corpus directory for .md / .txt files
        paths = sorted([p for p in CORPUS_DIR.glob("**/*") if p.is_file() and p.suffix in {".md", ".txt"}])
        if not paths:
            print(f"[reindex] no files found under {CORPUS_DIR}")
            return

        total = 0
        for p in paths:
            text = p.read_text(encoding="utf-8")
            chunks = _chunk(text)
            print(f"[reindex] {p.name}: {len(chunks)} chunks")
            payloads = []
            for idx, ch in enumerate(chunks):
                payloads.append({
                    "id": _id_for(p.name, idx, ch),
                    "text": ch,
                    "source": p.name,
                    "metadata": {"path": str(p.relative_to(CORPUS_DIR))},
                })
            # Batch in groups of 16 to keep vector generation concurrent without overloading Ollama
            for i in range(0, len(payloads), 16):
                await rag.upsert_chunks(payloads[i:i + 16])
            total += len(payloads)

        print(f"[reindex] upserted {total} chunks into '{s.qdrant_collection}'")
        await q.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Mount the corpus into the `api` container**

Modify `infra/docker-compose.yml` → `api.volumes`:

```yaml
      - ../infra/rag-corpus:/corpus:ro
```

- [ ] **Step 3: Run the indexer**

```bash
cd infra
docker compose up -d --build api
sleep 5
docker compose exec api uv run python -m app.scripts.reindex_rag
```

Expected output: `[reindex] embedding dim = 1024` (bge-m3), followed by per-file chunk counts, then a total.

Verify in Qdrant dashboard (`http://localhost:6333/dashboard`) → collection `kyc_corpus` has N points.

- [ ] **Step 4: Commit**

```bash
touch apps/api/scripts/__init__.py
git add apps/api/scripts/ infra/docker-compose.yml
git commit -m "feat(rag): reindex_rag script + corpus mount"
```

---

### Task 40: Compliance agent + FAQ inline in `/chat`

**Files:**
- Create: `apps/api/app/agents/compliance.py`
- Modify: `apps/api/app/routers/chat.py` (replace FAQ placeholder with real agent call)

- [ ] **Step 1: Write `apps/api/app/agents/compliance.py`**

```python
# apps/api/app/agents/compliance.py
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.services.ollama_client import OllamaClient
from app.services.rag import RAGService


FAQ_PROMPT = """You are a KYC assistant. Use the CONTEXT below to answer the user's question.
- If the context doesn't contain the answer, say so plainly; don't invent facts.
- Reply in the user's language ({lang}).
- Keep it to 2-4 sentences.
- At the end, include a short "Sources:" line listing the source file names used.

CONTEXT:
{context}
"""


async def answer_faq(
    rag: RAGService,
    ollama: OllamaClient,
    question: str,
    language: str = "en",
) -> tuple[str, list[dict]]:
    hits = await rag.retrieve(question, k=4)
    if not hits:
        return (
            "I don't have that in my knowledge base yet. Could you rephrase or ask something else?",
            [],
        )
    context = "\n\n---\n\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
    answer = await ollama.chat(
        [
            {"role": "system", "content": FAQ_PROMPT.format(lang=language, context=context)},
            {"role": "user", "content": question},
        ],
        temperature=0.2,
    )
    sources = [{"source": h["source"], "score": h["score"]} for h in hits]
    return answer, sources


async def persist_compliance_qna(
    db: AsyncSession, session_id: str, question: str, answer: str, sources: list[dict]
) -> None:
    db.add(m.ComplianceQna(
        session_id=uuid.UUID(session_id),
        question=question,
        answer=answer,
        sources=sources,
    ))
    await db.commit()
```

- [ ] **Step 2: Wire into `/chat`**

In `apps/api/app/routers/chat.py`, replace the `if intent == "faq":` block with:

```python
        if intent == "faq":
            from app.agents.compliance import answer_faq, persist_compliance_qna
            from app.services.rag import RAGService
            from qdrant_client import AsyncQdrantClient
            from app.config import get_settings
            s = get_settings()
            q = AsyncQdrantClient(url=s.qdrant_url)
            try:
                rag = RAGService(q, ollama)
                answer, sources = await answer_faq(rag, ollama, req.text, language)
            finally:
                await q.close()
            current_state["messages"].append({"role": "assistant", "content": answer})
            await persist_compliance_qna(db, session_id, req.text, answer, sources)
            new_state = current_state
```

- [ ] **Step 3: Smoke test**

```bash
docker compose restart api
sleep 5
SID=$(curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"text\":\"is my data safe?\"}" | python -m json.tool
```

Expected: a grounded answer mentioning local storage / masked Aadhaar, ending with a `Sources:` line.

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT question, LEFT(answer, 80), jsonb_array_length(sources) FROM compliance_qna;"
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/agents/compliance.py apps/api/app/routers/chat.py
git commit -m "feat(agents): compliance RAG FAQ answering"
git tag phase-12-complete
```

---

## Phase 13 — Frontend Shell (Vite + Tailwind + shadcn)

**Goal:** Bootstrap the React app, wire Tailwind + shadcn, render a minimal chat shell that can round-trip text with `/chat`.

**Verify at end:** `http://localhost:5173` loads; typing "hello" gets a reply back with no widget rendering yet.

---

### Task 41: Vite + TypeScript + Tailwind bootstrap

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`, `apps/web/tsconfig.node.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/tailwind.config.ts`, `apps/web/postcss.config.js`
- Create: `apps/web/index.html`
- Create: `apps/web/src/main.tsx`, `apps/web/src/App.tsx`
- Create: `apps/web/src/index.css`

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "kyc-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 5173",
    "build": "tsc -b && vite build",
    "preview": "vite preview --host 0.0.0.0 --port 5173",
    "lint": "eslint src"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "zod": "^3.23.8",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.4",
    "lucide-react": "^0.454.0",
    "react-easy-crop": "^5.0.8",
    "@radix-ui/react-dialog": "^1.1.2",
    "@radix-ui/react-tooltip": "^1.1.4",
    "@radix-ui/react-slot": "^1.1.0",
    "@radix-ui/react-separator": "^1.1.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.3",
    "typescript": "^5.6.3",
    "vite": "^5.4.10",
    "tailwindcss": "^3.4.14",
    "postcss": "^8.4.47",
    "autoprefixer": "^10.4.20",
    "tailwindcss-animate": "^1.0.7"
  }
}
```

- [ ] **Step 2: Write `vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: { port: 5173, host: true },
});
```

- [ ] **Step 3: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noImplicitAny": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "skipLibCheck": true,
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

And `tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Tailwind files**

`tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
```

`postcss.config.js`:

```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

- [ ] **Step 5: `index.html` + entry files**

`index.html`:

```html
<!doctype html>
<html lang="en" class="h-full">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>KYC Agent</title>
  </head>
  <body class="h-full bg-background text-foreground">
    <div id="root" class="h-full"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

`src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222 47% 11%;
    --border: 214 32% 91%;
    --input: 214 32% 91%;
    --ring: 222 84% 55%;
    --primary: 222 84% 55%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96%;
    --secondary-foreground: 222 47% 11%;
    --muted: 210 40% 96%;
    --muted-foreground: 215 16% 47%;
    --accent: 210 40% 96%;
    --accent-foreground: 222 47% 11%;
    --destructive: 0 84% 60%;
    --destructive-foreground: 210 40% 98%;
    --radius: 0.5rem;
  }
  .dark {
    --background: 222 47% 6%;
    --foreground: 210 40% 98%;
    --border: 217 33% 17%;
    --input: 217 33% 17%;
    --ring: 222 84% 60%;
    --primary: 222 84% 60%;
    --primary-foreground: 222 47% 6%;
    --secondary: 217 33% 17%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217 33% 17%;
    --muted-foreground: 215 20% 65%;
    --accent: 217 33% 17%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 63% 31%;
    --destructive-foreground: 210 40% 98%;
  }
  * { border-color: hsl(var(--border)); }
}
```

`src/App.tsx` (placeholder until Task 42):

```tsx
export default function App() {
  return (
    <div className="h-full grid place-items-center">
      <p className="text-muted-foreground">KYC Agent — scaffold up</p>
    </div>
  );
}
```

- [ ] **Step 6: Install and verify**

```bash
cd apps/web
npm install
npm run dev -- --port 5173
```

Open `http://localhost:5173` — should show "KYC Agent — scaffold up" on a white page.

Stop the dev server (Ctrl-C).

- [ ] **Step 7: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/tsconfig.json \
        apps/web/tsconfig.node.json apps/web/vite.config.ts \
        apps/web/tailwind.config.ts apps/web/postcss.config.js \
        apps/web/index.html apps/web/src/main.tsx apps/web/src/App.tsx \
        apps/web/src/index.css
git commit -m "feat(web): vite + react 19 + tailwind scaffold"
```

---

### Task 42: shadcn primitives + `cn` helper

**Files:**
- Create: `apps/web/src/lib/utils.ts`
- Create: `apps/web/src/components/ui/button.tsx`
- Create: `apps/web/src/components/ui/card.tsx`
- Create: `apps/web/src/components/ui/input.tsx`
- Create: `apps/web/src/components/ui/label.tsx`
- Create: `apps/web/src/components/ui/textarea.tsx`
- Create: `apps/web/src/components/ui/dialog.tsx`
- Create: `apps/web/src/components/ui/separator.tsx`

- [ ] **Step 1: Write `src/lib/utils.ts`**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 2: Write `button.tsx`**

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3",
        lg: "h-11 px-6",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />;
  }
);
Button.displayName = "Button";
```

- [ ] **Step 3: Write the other primitives (standard shadcn templates — copy verbatim)**

`card.tsx`:

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-lg border bg-card text-card-foreground shadow-sm", className)} {...props} />
  )
);
Card.displayName = "Card";

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  )
);
CardHeader.displayName = "CardHeader";

export const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("text-lg font-semibold leading-none tracking-tight", className)} {...props} />
  )
);
CardTitle.displayName = "CardTitle";

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  )
);
CardContent.displayName = "CardContent";
```

`input.tsx`:

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
```

`label.tsx`:

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement>
>(({ className, ...props }, ref) => (
  <label ref={ref} className={cn("text-sm font-medium leading-none", className)} {...props} />
));
Label.displayName = "Label";
```

`textarea.tsx`:

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";
```

`dialog.tsx` — copy the standard shadcn Radix Dialog wrapper (https://ui.shadcn.com/docs/components/dialog). Fully self-contained; imports from `@radix-ui/react-dialog`.

`separator.tsx`:

```tsx
import * as React from "react";
import * as SeparatorPrimitive from "@radix-ui/react-separator";
import { cn } from "@/lib/utils";

export const Separator = React.forwardRef<
  React.ElementRef<typeof SeparatorPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>
>(({ className, orientation = "horizontal", decorative = true, ...props }, ref) => (
  <SeparatorPrimitive.Root
    ref={ref}
    decorative={decorative}
    orientation={orientation}
    className={cn(
      "shrink-0 bg-border",
      orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
      className,
    )}
    {...props}
  />
));
Separator.displayName = "Separator";
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib apps/web/src/components/ui
git commit -m "feat(web): shadcn primitives — button, card, input, label, textarea, dialog, separator"
```

---

### Task 43: API client with zod schemas + `useSession`

**Files:**
- Create: `apps/web/src/api/client.ts`
- Create: `apps/web/src/api/schemas.ts`
- Create: `apps/web/src/hooks/useSession.ts`

- [ ] **Step 1: Write `src/api/schemas.ts`**

```ts
import { z } from "zod";

export const WidgetSchema = z.object({
  type: z.enum(["upload", "editable_card", "selfie_camera", "verdict"]),
  doc_type: z.string().optional(),
  accept: z.array(z.string()).optional(),
  fields: z.array(z.object({ name: z.string(), label: z.string(), value: z.string() })).optional(),
  decision: z.string().optional(),
  decision_reason: z.string().optional(),
  checks: z.array(z.any()).optional(),
  flags: z.array(z.string()).optional(),
  recommendations: z.array(z.string()).optional(),
});
export type Widget = z.infer<typeof WidgetSchema>;

export const ChatMessageSchema = z.object({
  role: z.enum(["user", "assistant", "system"]),
  content: z.string(),
  widget: WidgetSchema.nullable().optional(),
});
export type ChatMessage = z.infer<typeof ChatMessageSchema>;

export const ChatResponseSchema = z.object({
  session_id: z.string(),
  messages: z.array(ChatMessageSchema),
  next_required: z.string(),
  language: z.string(),
});
export type ChatResponse = z.infer<typeof ChatResponseSchema>;
```

- [ ] **Step 2: Write `src/api/client.ts`**

```ts
import { ChatResponseSchema, type ChatResponse } from "./schemas";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function handle<T>(r: Response, schema: { parse: (d: unknown) => T }): Promise<T> {
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status}: ${text}`);
  }
  return schema.parse(await r.json());
}

export async function sendChat(text: string, sessionId: string | null): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, session_id: sessionId }),
  });
  return handle(r, ChatResponseSchema);
}

export async function uploadDoc(sessionId: string, docType: "aadhaar" | "pan", file: File | Blob): Promise<ChatResponse> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("doc_type", docType);
  fd.append("file", file, (file as File).name ?? `${docType}.jpg`);
  const r = await fetch(`${API_URL}/upload`, { method: "POST", body: fd });
  return handle(r, ChatResponseSchema);
}

export async function captureImage(sessionId: string, target: "selfie" | "aadhaar" | "pan", blob: Blob): Promise<ChatResponse> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("target", target);
  fd.append("file", blob, `${target}.jpg`);
  const r = await fetch(`${API_URL}/capture`, { method: "POST", body: fd });
  return handle(r, ChatResponseSchema);
}

export async function confirmDoc(sessionId: string, docType: "aadhaar" | "pan", fields: Record<string, string>): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, doc_type: docType, fields }),
  });
  return handle(r, ChatResponseSchema);
}
```

- [ ] **Step 3: Write `src/hooks/useSession.ts`**

```ts
import { useCallback, useState } from "react";

const KEY = "kyc.sessionId";

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(
    () => sessionStorage.getItem(KEY),
  );

  const update = useCallback((id: string) => {
    sessionStorage.setItem(KEY, id);
    setSessionId(id);
  }, []);

  const reset = useCallback(() => {
    sessionStorage.removeItem(KEY);
    setSessionId(null);
  }, []);

  return { sessionId, update, reset };
}
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/api apps/web/src/hooks/useSession.ts
git commit -m "feat(web): API client + zod schemas + useSession"
```

---

### Task 44: ChatShell + MessageBubble + ChatInput (no widgets yet)

**Files:**
- Create: `apps/web/src/components/chat/MessageBubble.tsx`
- Create: `apps/web/src/components/chat/MessageList.tsx`
- Create: `apps/web/src/components/chat/ChatInput.tsx`
- Create: `apps/web/src/components/chat/ChatShell.tsx`
- Modify: `apps/web/src/App.tsx`

- [ ] **Step 1: Write `MessageBubble.tsx`**

```tsx
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/api/schemas";

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-md"
            : "bg-muted text-foreground rounded-bl-md",
        )}
      >
        {msg.content}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `MessageList.tsx`**

```tsx
import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/api/schemas";
import { MessageBubble } from "./MessageBubble";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
      {messages.map((m, i) => (
        <div key={i} className="space-y-2">
          <MessageBubble msg={m} />
          {/* widgets render here once we add them in Phase 14 */}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
```

- [ ] **Step 3: Write `ChatInput.tsx`**

```tsx
import { useState } from "react";
import { SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function ChatInput({ onSend, disabled }: { onSend: (text: string) => void; disabled?: boolean }) {
  const [text, setText] = useState("");
  return (
    <form
      className="flex gap-2 border-t bg-background p-3"
      onSubmit={(e) => {
        e.preventDefault();
        const t = text.trim();
        if (!t) return;
        onSend(t);
        setText("");
      }}
    >
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type a message or ask a question…"
        disabled={disabled}
      />
      <Button type="submit" size="icon" disabled={disabled || !text.trim()}>
        <SendHorizontal className="h-4 w-4" />
      </Button>
    </form>
  );
}
```

- [ ] **Step 4: Write `ChatShell.tsx`**

```tsx
import { useState } from "react";
import { sendChat } from "@/api/client";
import type { ChatMessage } from "@/api/schemas";
import { useSession } from "@/hooks/useSession";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";

export function ChatShell() {
  const { sessionId, update } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  const handle = async (text: string) => {
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: text }]);
    try {
      const res = await sendChat(text, sessionId);
      if (!sessionId) update(res.session_id);
      setMessages((m) => [...m, ...res.messages.filter((x) => x.role === "assistant")]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col max-w-2xl mx-auto">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="font-semibold">KYC Agent</div>
        {sessionId && <div className="text-xs text-muted-foreground">#{sessionId.slice(0, 8)}</div>}
      </header>
      <MessageList messages={messages} />
      <ChatInput onSend={handle} disabled={busy} />
    </div>
  );
}
```

- [ ] **Step 5: Update `App.tsx`**

```tsx
import { ChatShell } from "@/components/chat/ChatShell";

export default function App() {
  return <ChatShell />;
}
```

- [ ] **Step 6: Boot the flow end-to-end**

```bash
cd apps/web
npm run dev
```

Visit `http://localhost:5173`. Type "hello". Expected: assistant replies with a greeting. Type "Asha Sharma". Expected: assistant acknowledges and asks for Aadhaar upload (no widget rendered yet — that's Phase 14).

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/App.tsx apps/web/src/components/chat
git commit -m "feat(web): chat shell — messages, input, round-trip to /chat"
git tag phase-13-complete
```

---

## Phase 14 — Frontend Widgets

**Goal:** Render the four widgets (upload, editable_card, selfie_camera, verdict) inside the message list. Wire each to its API endpoint.

**Verify at end:** Complete an entire end-to-end KYC flow in the browser — greet, name, Aadhaar upload, Aadhaar confirm, PAN upload, PAN confirm, selfie, verdict.

---

### Task 45: DocumentUploadWidget + MessageList dispatcher

**Files:**
- Create: `apps/web/src/components/widgets/DocumentUploadWidget.tsx`
- Modify: `apps/web/src/components/chat/MessageList.tsx` (render widgets)
- Modify: `apps/web/src/components/chat/ChatShell.tsx` (provide widget callbacks)

- [ ] **Step 1: Write `DocumentUploadWidget.tsx`**

```tsx
import { useRef, useState } from "react";
import { Camera, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function DocumentUploadWidget({
  docType,
  accept,
  onFile,
  onOpenCamera,
  disabled,
}: {
  docType: string;
  accept: string[];
  onFile: (file: File) => void;
  onOpenCamera: () => void;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="text-sm font-medium capitalize">{docType} document</div>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files[0];
            if (f) onFile(f);
          }}
          className={`rounded-md border-2 border-dashed p-6 text-center text-sm ${dragging ? "border-primary bg-primary/5" : "border-border"}`}
        >
          Drop your {docType} here, or
          <div className="mt-3 flex gap-2 justify-center">
            <Button
              variant="secondary" size="sm" disabled={disabled}
              onClick={() => ref.current?.click()}
            >
              <Upload className="h-4 w-4 mr-1.5" /> Choose file
            </Button>
            <Button variant="secondary" size="sm" disabled={disabled} onClick={onOpenCamera}>
              <Camera className="h-4 w-4 mr-1.5" /> Use camera
            </Button>
          </div>
          <input
            ref={ref}
            type="file"
            accept={accept.join(",")}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFile(f);
            }}
          />
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Rewrite `MessageList.tsx` to dispatch widgets**

```tsx
import { useEffect, useRef } from "react";
import type { ChatMessage, Widget } from "@/api/schemas";
import { MessageBubble } from "./MessageBubble";
import { DocumentUploadWidget } from "@/components/widgets/DocumentUploadWidget";
// other widgets added in the next tasks

export type WidgetHandlers = {
  onUploadFile: (docType: "aadhaar" | "pan", file: File) => void;
  onOpenCamera: (target: "aadhaar" | "pan" | "selfie") => void;
  onConfirm: (docType: "aadhaar" | "pan", fields: Record<string, string>) => void;
  onRestart: () => void;
};

export function MessageList({ messages, handlers }: { messages: ChatMessage[]; handlers: WidgetHandlers }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
      {messages.map((m, i) => (
        <div key={i} className="space-y-2">
          <MessageBubble msg={m} />
          {m.widget && <WidgetRenderer widget={m.widget} handlers={handlers} />}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function WidgetRenderer({ widget, handlers }: { widget: Widget; handlers: WidgetHandlers }) {
  if (widget.type === "upload" && widget.doc_type) {
    const dt = widget.doc_type as "aadhaar" | "pan";
    return (
      <DocumentUploadWidget
        docType={dt}
        accept={widget.accept ?? ["image/jpeg", "image/png", "application/pdf"]}
        onFile={(f) => handlers.onUploadFile(dt, f)}
        onOpenCamera={() => handlers.onOpenCamera(dt)}
      />
    );
  }
  // Other widget types added in subsequent tasks
  return null;
}
```

- [ ] **Step 3: Update `ChatShell.tsx` to pass handlers and call `uploadDoc`**

```tsx
import { useState } from "react";
import { sendChat, uploadDoc, confirmDoc, captureImage } from "@/api/client";
import type { ChatMessage } from "@/api/schemas";
import { useSession } from "@/hooks/useSession";
import { MessageList, type WidgetHandlers } from "./MessageList";
import { ChatInput } from "./ChatInput";

export function ChatShell() {
  const { sessionId, update, reset } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  const appendAssistantFrom = (assistantMsgs: ChatMessage[]) => {
    setMessages((m) => [...m, ...assistantMsgs.filter((x) => x.role === "assistant")]);
  };

  const sendText = async (text: string) => {
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: text }]);
    try {
      const res = await sendChat(text, sessionId);
      if (!sessionId) update(res.session_id);
      appendAssistantFrom(res.messages);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  };

  const handlers: WidgetHandlers = {
    onUploadFile: async (docType, file) => {
      if (!sessionId) return;
      setBusy(true);
      setMessages((m) => [...m, { role: "user", content: `Uploaded ${docType} — ${file.name}` }]);
      try {
        const res = await uploadDoc(sessionId, docType, file);
        appendAssistantFrom(res.messages);
      } catch (err) {
        setMessages((m) => [...m, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
      } finally { setBusy(false); }
    },
    onOpenCamera: (_target) => {
      // Hooked up in Phase 15
      window.dispatchEvent(new CustomEvent("kyc:open-camera", { detail: _target }));
    },
    onConfirm: async (docType, fields) => {
      if (!sessionId) return;
      setBusy(true);
      setMessages((m) => [...m, { role: "user", content: `Confirmed ${docType} details.` }]);
      try {
        const res = await confirmDoc(sessionId, docType, fields);
        appendAssistantFrom(res.messages);
      } catch (err) {
        setMessages((m) => [...m, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
      } finally { setBusy(false); }
    },
    onRestart: () => { reset(); setMessages([]); },
  };

  return (
    <div className="flex h-full flex-col max-w-2xl mx-auto">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="font-semibold">KYC Agent</div>
        <div className="flex items-center gap-3">
          {sessionId && <div className="text-xs text-muted-foreground">#{sessionId.slice(0, 8)}</div>}
          <button className="text-xs text-muted-foreground hover:text-foreground" onClick={handlers.onRestart}>
            Restart
          </button>
        </div>
      </header>
      <MessageList messages={messages} handlers={handlers} />
      <ChatInput onSend={sendText} disabled={busy} />
    </div>
  );
}

export { };
// (keep a default export if needed — referenced only by App.tsx via named import)
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/chat apps/web/src/components/widgets/DocumentUploadWidget.tsx
git commit -m "feat(web): upload widget + handler dispatcher"
```

---

### Task 46: EditableFieldCard widget

**Files:**
- Create: `apps/web/src/components/widgets/EditableFieldCard.tsx`
- Modify: `MessageList.tsx` (handle `editable_card`)

- [ ] **Step 1: Write `EditableFieldCard.tsx`**

```tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Field = { name: string; label: string; value: string };

export function EditableFieldCard({
  docType, fields, onConfirm,
}: {
  docType: string;
  fields: Field[];
  onConfirm: (values: Record<string, string>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.name, f.value])),
  );
  const [confirmed, setConfirmed] = useState(false);

  if (confirmed) {
    return (
      <Card>
        <CardContent className="p-4 text-sm">
          <div className="font-medium mb-2 capitalize">{docType} — confirmed</div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-muted-foreground">
            {fields.map((f) => (
              <>
                <dt key={f.name + "-label"}>{f.label}</dt>
                <dd key={f.name + "-val"} className="text-foreground">{values[f.name] || "—"}</dd>
              </>
            ))}
          </dl>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="text-sm font-medium capitalize">Review your {docType} details</div>
        {fields.map((f) => (
          <div key={f.name} className="space-y-1">
            <Label htmlFor={`${docType}-${f.name}`}>{f.label}</Label>
            <Input
              id={`${docType}-${f.name}`}
              value={values[f.name] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
            />
          </div>
        ))}
        <div className="flex justify-end pt-2">
          <Button size="sm" onClick={() => { onConfirm(values); setConfirmed(true); }}>
            Confirm
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Add the case in `MessageList.WidgetRenderer`**

```tsx
// append:
import { EditableFieldCard } from "@/components/widgets/EditableFieldCard";

// inside WidgetRenderer:
  if (widget.type === "editable_card" && widget.doc_type && widget.fields) {
    const dt = widget.doc_type as "aadhaar" | "pan";
    return (
      <EditableFieldCard
        docType={dt}
        fields={widget.fields}
        onConfirm={(vals) => handlers.onConfirm(dt, vals)}
      />
    );
  }
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/widgets/EditableFieldCard.tsx apps/web/src/components/chat/MessageList.tsx
git commit -m "feat(web): editable_card widget + confirm handler"
```

---

### Task 47: SelfieCamera widget

**Files:**
- Create: `apps/web/src/components/widgets/SelfieCamera.tsx`
- Modify: `MessageList.tsx`
- Modify: `ChatShell.tsx` (handler for selfie)

- [ ] **Step 1: Write `SelfieCamera.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { Camera, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function SelfieCamera({ onCapture }: { onCapture: (blob: Blob) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (preview) return;
    let mounted = true;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user" } })
      .then((s) => {
        if (!mounted) { s.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = s;
        if (videoRef.current) videoRef.current.srcObject = s;
      })
      .catch((e) => setError(String(e)));
    return () => {
      mounted = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [preview]);

  const capture = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      setPreview(URL.createObjectURL(blob));
      streamRef.current?.getTracks().forEach((t) => t.stop());
      onCapture(blob);
    }, "image/jpeg", 0.92);
  };

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="text-sm font-medium">Take a selfie</div>
        {error && <div className="text-sm text-destructive">Camera error: {error}</div>}
        {!preview ? (
          <>
            <video ref={videoRef} className="w-full rounded-md bg-black" autoPlay playsInline muted />
            <canvas ref={canvasRef} className="hidden" />
            <Button size="sm" onClick={capture} className="w-full">
              <Camera className="h-4 w-4 mr-1.5" /> Capture
            </Button>
          </>
        ) : (
          <>
            <img src={preview} alt="selfie preview" className="w-full rounded-md" />
            <Button size="sm" variant="outline" onClick={() => setPreview(null)} className="w-full">
              <RotateCcw className="h-4 w-4 mr-1.5" /> Retake
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Update `MessageList.WidgetRenderer`**

```tsx
import { SelfieCamera } from "@/components/widgets/SelfieCamera";

// inside WidgetRenderer:
  if (widget.type === "selfie_camera") {
    return <SelfieCamera onCapture={(blob) => handlers.onSelfie(blob)} />;
  }
```

- [ ] **Step 3: Extend `WidgetHandlers` and `ChatShell.handlers`**

Add `onSelfie: (blob: Blob) => void` to `WidgetHandlers`, then in `ChatShell`:

```tsx
    onSelfie: async (blob) => {
      if (!sessionId) return;
      setBusy(true);
      setMessages((m) => [...m, { role: "user", content: "Captured selfie." }]);
      try {
        const res = await captureImage(sessionId, "selfie", blob);
        appendAssistantFrom(res.messages);
      } catch (err) {
        setMessages((m) => [...m, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
      } finally { setBusy(false); }
    },
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/widgets/SelfieCamera.tsx apps/web/src/components/chat
git commit -m "feat(web): selfie_camera widget + handler"
```

---

### Task 48: VerdictCard widget

**Files:**
- Create: `apps/web/src/components/widgets/VerdictCard.tsx`
- Modify: `MessageList.tsx`

- [ ] **Step 1: Write `VerdictCard.tsx`**

```tsx
import { useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, ChevronDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

type Verdict = {
  decision: string;
  decision_reason: string;
  checks?: Array<{ name: string; status: string; score: number; detail?: string }>;
  flags?: string[];
  recommendations?: string[];
};

const style: Record<string, { cls: string; Icon: typeof CheckCircle2; label: string }> = {
  approved: { cls: "border-emerald-600 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
              Icon: CheckCircle2, label: "Approved" },
  flagged:  { cls: "border-amber-600 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
              Icon: AlertTriangle, label: "Flagged for review" },
  rejected: { cls: "border-rose-600 bg-rose-50 text-rose-900 dark:bg-rose-950 dark:text-rose-100",
              Icon: XCircle, label: "Rejected" },
};


export function VerdictCard({ verdict }: { verdict: Verdict }) {
  const [open, setOpen] = useState(false);
  const cfg = style[verdict.decision] ?? style.flagged;
  const { Icon } = cfg;
  return (
    <Card className={cn("border-2", cfg.cls)}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 font-semibold">
          <Icon className="h-5 w-5" aria-hidden /> {cfg.label}
        </div>
        <p className="text-sm">{verdict.decision_reason}</p>

        {verdict.recommendations && verdict.recommendations.length > 0 && (
          <>
            <Separator />
            <ul className="list-disc pl-5 text-sm space-y-1">
              {verdict.recommendations.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </>
        )}

        <button
          className="flex items-center gap-1 text-xs opacity-80 hover:opacity-100"
          onClick={() => setOpen((v) => !v)}
        >
          <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} /> Why
        </button>
        {open && (
          <div className="text-xs space-y-1 font-mono">
            {verdict.checks?.map((c, i) => (
              <div key={i} className="flex justify-between gap-4">
                <span>{c.name}</span>
                <span>{c.status} · {(c.score * 100).toFixed(0)}%</span>
              </div>
            ))}
            {verdict.flags && verdict.flags.length > 0 && (
              <div>
                <div className="pt-1 font-semibold">Flags</div>
                {verdict.flags.map((f, i) => <div key={i}>· {f}</div>)}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Add to `MessageList.WidgetRenderer`**

```tsx
import { VerdictCard } from "@/components/widgets/VerdictCard";

// inside WidgetRenderer:
  if (widget.type === "verdict") {
    return <VerdictCard verdict={{
      decision: widget.decision ?? "flagged",
      decision_reason: widget.decision_reason ?? "",
      checks: widget.checks as never,
      flags: widget.flags,
      recommendations: widget.recommendations,
    }} />;
  }
```

- [ ] **Step 3: End-to-end smoke test**

With all services running and Ollama available:

1. Open `http://localhost:5173`.
2. Greet, give name, upload sample Aadhaar, confirm, upload sample PAN, confirm, take a selfie.
3. Expected: see the verdict card with colour matching the decision.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/widgets/VerdictCard.tsx apps/web/src/components/chat/MessageList.tsx
git commit -m "feat(web): verdict widget; first full end-to-end flow in browser"
git tag phase-14-complete
```

---

## Phase 15 — Camera Capture Modal + FAQ Drawer

**Goal:** Document camera capture path with a crop step. FAQ FAB + drawer that routes questions through `/chat` with a leading prompt indicating the user is asking a question (increases the chance of the `faq` classification).

**Verify at end:** "Use camera" inside an upload widget opens a fullscreen capture → crop → upload flow. FAQ FAB opens a drawer where the user can ask a question and get a grounded answer without leaving their current KYC step.

---

### Task 49: CameraCaptureModal with react-easy-crop

**Files:**
- Create: `apps/web/src/components/camera/CameraCaptureModal.tsx`
- Modify: `apps/web/src/components/chat/ChatShell.tsx` (host modal; listen for `kyc:open-camera` events)

- [ ] **Step 1: Write `CameraCaptureModal.tsx`**

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import { Camera, Check, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type Target = "aadhaar" | "pan";


async function cropToBlob(src: string, area: Area): Promise<Blob> {
  const img = new Image();
  img.src = src;
  await new Promise<void>((r) => { img.onload = () => r(); });
  const canvas = document.createElement("canvas");
  canvas.width = area.width;
  canvas.height = area.height;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(img, area.x, area.y, area.width, area.height, 0, 0, area.width, area.height);
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b!), "image/jpeg", 0.92));
}


export function CameraCaptureModal({
  open, target, onClose, onCropped,
}: {
  open: boolean;
  target: Target;
  onClose: () => void;
  onCropped: (blob: Blob) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [area, setArea] = useState<Area | null>(null);

  useEffect(() => {
    if (!open) return;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        streamRef.current = s;
        if (videoRef.current) videoRef.current.srcObject = s;
      })
      .catch((e) => console.error(e));
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setSnapshot(null);
    };
  }, [open]);

  const grab = () => {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      setSnapshot(URL.createObjectURL(blob));
      streamRef.current?.getTracks().forEach((t) => t.stop());
    }, "image/jpeg", 0.92);
  };

  const retake = () => {
    setSnapshot(null);
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then((s) => {
      streamRef.current = s;
      if (videoRef.current) videoRef.current.srcObject = s;
    });
  };

  const use = useCallback(async () => {
    if (!snapshot || !area) return;
    const blob = await cropToBlob(snapshot, area);
    onCropped(blob);
    onClose();
  }, [snapshot, area, onCropped, onClose]);

  const onCropComplete = useCallback((_: Area, px: Area) => setArea(px), []);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="font-medium capitalize">Capture {target}</div>
        <button onClick={onClose} aria-label="Close"><X className="h-5 w-5" /></button>
      </div>
      <div className="flex-1 relative bg-black">
        {!snapshot ? (
          <video ref={videoRef} autoPlay playsInline muted className="h-full w-full object-contain" />
        ) : (
          <Cropper
            image={snapshot}
            crop={crop}
            zoom={zoom}
            aspect={undefined}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={onCropComplete}
          />
        )}
      </div>
      <div className="flex gap-2 p-3 border-t">
        {!snapshot ? (
          <Button className="flex-1" onClick={grab}>
            <Camera className="h-4 w-4 mr-1.5" /> Capture
          </Button>
        ) : (
          <>
            <Button variant="outline" onClick={retake} className="flex-1">
              <RotateCcw className="h-4 w-4 mr-1.5" /> Retake
            </Button>
            <Button onClick={use} className="flex-1">
              <Check className="h-4 w-4 mr-1.5" /> Use this
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Host the modal in `ChatShell`**

Add this to `ChatShell` (inside the return, before the closing `</div>`):

```tsx
import { useEffect, useState } from "react";
import { CameraCaptureModal } from "@/components/camera/CameraCaptureModal";

// inside ChatShell:
const [cameraTarget, setCameraTarget] = useState<"aadhaar" | "pan" | null>(null);

useEffect(() => {
  const onOpen = (e: Event) => {
    const t = (e as CustomEvent).detail;
    if (t === "aadhaar" || t === "pan") setCameraTarget(t);
  };
  window.addEventListener("kyc:open-camera", onOpen);
  return () => window.removeEventListener("kyc:open-camera", onOpen);
}, []);

// JSX (append before the outer </div>):
{cameraTarget && (
  <CameraCaptureModal
    open
    target={cameraTarget}
    onClose={() => setCameraTarget(null)}
    onCropped={async (blob) => {
      if (!sessionId) return;
      setBusy(true);
      setMessages((m) => [...m, { role: "user", content: `Captured ${cameraTarget} image.` }]);
      try {
        const res = await captureImage(sessionId, cameraTarget, blob);
        appendAssistantFrom(res.messages);
      } catch (err) {
        setMessages((m) => [...m, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
      } finally { setBusy(false); }
    }}
  />
)}
```

- [ ] **Step 3: Smoke test**

"Use camera" button on an upload widget → full-screen capture view → Capture → crop → Use this → OCR runs → confirm card appears.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/camera apps/web/src/components/chat/ChatShell.tsx
git commit -m "feat(web): camera capture modal with crop (react-easy-crop)"
```

---

### Task 50: FAQ drawer + FAB

**Files:**
- Create: `apps/web/src/components/faq/FaqDrawer.tsx`
- Modify: `apps/web/src/App.tsx`

- [ ] **Step 1: Write `FaqDrawer.tsx`**

```tsx
import { useState } from "react";
import { HelpCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { sendChat } from "@/api/client";
import { useSession } from "@/hooks/useSession";

export function FaqDrawer() {
  const { sessionId } = useSession();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [history, setHistory] = useState<{ q: string; a: string }[]>([]);
  const [busy, setBusy] = useState(false);

  const ask = async () => {
    const text = q.trim();
    if (!text) return;
    setBusy(true);
    try {
      // Prefix nudges the intent classifier toward "faq"
      const res = await sendChat(text.endsWith("?") ? text : `${text}?`, sessionId);
      const assistant = res.messages.find((m) => m.role === "assistant");
      setHistory((h) => [{ q: text, a: assistant?.content ?? "" }, ...h]);
      setQ("");
    } finally { setBusy(false); }
  };

  return (
    <>
      <button
        aria-label="Open FAQ"
        onClick={() => setOpen(true)}
        className="fixed bottom-20 right-6 h-12 w-12 rounded-full bg-primary text-primary-foreground grid place-items-center shadow-lg hover:opacity-90"
      >
        <HelpCircle className="h-5 w-5" />
      </button>
      {open && (
        <div className="fixed inset-y-0 right-0 w-full sm:w-[400px] z-40 bg-background border-l flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div className="font-medium">Frequently asked</div>
            <button onClick={() => setOpen(false)} aria-label="Close FAQ"><X className="h-5 w-5" /></button>
          </div>
          <div className="p-4 border-b flex gap-2">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ask a KYC question…"
              onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
            />
            <Button size="sm" onClick={ask} disabled={busy}>Ask</Button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
            {history.length === 0 && (
              <div className="text-muted-foreground">
                Try: "Why do you need my Aadhaar?" · "Is my data safe?" · "How long does this take?"
              </div>
            )}
            {history.map((h, i) => (
              <div key={i}>
                <div className="font-medium">{h.q}</div>
                <div className="mt-1 whitespace-pre-wrap text-muted-foreground">{h.a}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Mount in `App.tsx`**

```tsx
import { ChatShell } from "@/components/chat/ChatShell";
import { FaqDrawer } from "@/components/faq/FaqDrawer";

export default function App() {
  return (
    <div className="h-full">
      <ChatShell />
      <FaqDrawer />
    </div>
  );
}
```

- [ ] **Step 3: Smoke test**

Click the FAB → ask "is my data safe?" → the drawer shows a grounded answer with `Sources:` line. The main chat stays at its current step (no disruption).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/faq apps/web/src/App.tsx
git commit -m "feat(web): FAQ drawer + FAB"
git tag phase-15-complete
```

---

## Phase 16 — Polish & Ship

**Goal:** Add the `web` service to compose, write the final README, build a small `/session/:id` rehydrate endpoint so a page refresh reloads state, and lock in a "clone and run" story.

**Verify at end:** Fresh clone on another machine reaches `http://localhost:5173` after `docker compose up --build` and three `ollama pull` commands.

---

### Task 51: `/session/:id` rehydrate endpoint

**Files:**
- Create: `apps/api/app/routers/session.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Write the router**

```python
# apps/api/app/routers/session.py
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db import models as m
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatResponse, ChatMessage, Widget


router = APIRouter(prefix="/session", tags=["session"])


@router.get("/{session_id}", response_model=ChatResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    sess = await db.get(m.Session, uuid.UUID(session_id))
    if not sess:
        raise HTTPException(404, "Unknown session")
    msgs_q = await db.execute(
        select(m.Message).where(m.Message.session_id == sess.id).order_by(m.Message.seq)
    )
    msgs = msgs_q.scalars().all()

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        snap = await graph.aget_state({"configurable": {"thread_id": session_id}})
        next_required = (snap.values or {}).get("next_required") if snap else "done"

    return ChatResponse(
        session_id=session_id,
        messages=[
            ChatMessage(role=mm.role, content=mm.content,
                        widget=Widget(**mm.widget) if mm.widget else None)
            for mm in msgs
        ],
        next_required=next_required or "done",
        language=sess.language or "en",
    )
```

- [ ] **Step 2: Register in `main.py`**

```python
from app.routers import session as session_router
app.include_router(session_router.router)
```

- [ ] **Step 3: Wire into the web — `ChatShell` fetches on mount if `sessionId` is set**

Add to `apps/web/src/api/client.ts`:

```ts
export async function getSession(sessionId: string): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/session/${sessionId}`);
  return handle(r, ChatResponseSchema);
}
```

In `ChatShell.tsx`, add:

```tsx
import { getSession } from "@/api/client";
import { useEffect } from "react";

// inside ChatShell, after useSession:
useEffect(() => {
  if (!sessionId) return;
  getSession(sessionId)
    .then((res) => setMessages(res.messages))
    .catch(() => { /* stale session, ignore */ });
}, [sessionId]);
```

- [ ] **Step 4: Smoke test**

Complete a flow, refresh the page — messages reappear, widget states remain (upload/confirm widgets render again; the user can re-confirm if mid-step).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routers/session.py apps/api/app/main.py apps/web/src/api/client.ts apps/web/src/components/chat/ChatShell.tsx
git commit -m "feat: /session/:id rehydrate endpoint; web fetches on mount"
```

---

### Task 52: Web Dockerfile + wire into compose

**Files:**
- Create: `apps/web/Dockerfile`
- Create: `apps/web/nginx.conf`
- Modify: `infra/docker-compose.yml`

- [ ] **Step 1: Write `apps/web/Dockerfile`**

```dockerfile
# apps/web/Dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# Bake the API URL at build time — override with VITE_API_URL build-arg
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

- [ ] **Step 2: Write `apps/web/nginx.conf`**

```nginx
server {
  listen 80;
  server_name _;
  root /usr/share/nginx/html;
  index index.html;
  location / {
    try_files $uri /index.html;
  }
}
```

- [ ] **Step 3: Append `web` to `infra/docker-compose.yml`**

```yaml
  web:
    build:
      context: ../apps/web
      dockerfile: Dockerfile
      args:
        VITE_API_URL: ${VITE_API_URL:-http://localhost:8000}
    restart: unless-stopped
    depends_on:
      - api
    ports:
      - "5173:80"
```

- [ ] **Step 4: Build and run the web service**

```bash
cd infra
docker compose up -d --build web
```

Visit `http://localhost:5173` — production-built SPA loads.

- [ ] **Step 5: Commit**

```bash
git add apps/web/Dockerfile apps/web/nginx.conf infra/docker-compose.yml
git commit -m "feat(infra): web container served via nginx"
```

---

### Task 53: README rewrite (the setup story)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md`**

```markdown
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
# Pull the three models the agents need (thin :cloud tags)
ollama pull gemma4:31b-cloud
ollama pull ministral-3:8b-cloud
ollama pull bge-m3:latest

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

First boot: 3-5 min (installs TensorFlow + DeepFace weights on first selfie). Subsequent boots are instant.

Then:

- **Web app:** http://localhost:5173
- **Langfuse:** http://localhost:3000 — sign up locally (email/password, stored in `langfuse-db`). Create a project, copy the public + secret keys into `infra/.env`, then `docker compose restart api`.
- **Qdrant dashboard:** http://localhost:6333/dashboard

## One-time: seed the RAG corpus

```bash
docker compose exec api uv run python -m app.scripts.reindex_rag
```

Drops your RAG corpus under `infra/rag-corpus/` into Qdrant with bge-m3 embeddings. Re-run any time you add or edit corpus files.

## Smoke test the flow

1. Open http://localhost:5173.
2. Say hi. The assistant asks for your name.
3. Give it, then upload an Aadhaar image (or open the camera).
4. Review the OCR'd fields, confirm.
5. Upload PAN, confirm.
6. Take a selfie. Get your verdict.
7. Tap the ❓ FAB any time to ask a compliance question without leaving the flow.

## Project layout

See [`docs/superpowers/specs/2026-04-24-conversational-kyc-agent-design.md`](docs/superpowers/specs/2026-04-24-conversational-kyc-agent-design.md).

## Troubleshooting

- **"ollama": "unreachable" in /health** — Ollama isn't running, or the container can't reach `host.docker.internal`. On Linux, the `extra_hosts` entry in `docker-compose.yml` adds `host.docker.internal` via `host-gateway`. On Docker Desktop (Mac/Windows), it's built in.
- **First selfie is very slow** — DeepFace downloads VGG-Face weights on first call (~500 MB). Subsequent calls are fast.
- **Langfuse healthcheck times out on first boot** — Langfuse runs its own migrations on first start; it takes 30-60 s. Give it a moment, then `docker compose ps` should show `healthy`.
- **Qdrant collection missing** — run `docker compose exec api uv run python -m app.scripts.reindex_rag` to (re)create it.
- **ipwhois rate limit** — the free tier is rate-limited (~1k/day). Real deployments should grab an API key; set `IPWHOIS_API_KEY` in `.env`.

## Developing

- **Backend:** `cd apps/api && uv sync && uv run uvicorn app.main:app --reload`. Depends on a running compose stack for Postgres / Qdrant.
- **Frontend:** `cd apps/web && npm install && npm run dev`.
- **Tests:** `cd apps/api && uv run pytest -v`.

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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: clone-and-run README"
```

---

### Task 54: Final smoke test + tag

- [ ] **Step 1: Reset everything cleanly**

```bash
cd infra
docker compose down -v
docker compose up --build -d
# Wait ~90 s for Langfuse, api, migrations.
docker compose ps   # should show 6 services healthy
```

- [ ] **Step 2: Seed the corpus**

```bash
docker compose exec api uv run python -m app.scripts.reindex_rag
```

- [ ] **Step 3: End-to-end browser run**

Open `http://localhost:5173`, walk through the full flow. Expected: verdict card at the end.

- [ ] **Step 4: Database sanity query**

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "
SELECT s.id, s.status, s.language,
  (SELECT count(*) FROM messages WHERE session_id = s.id) AS msg_count,
  (SELECT count(*) FROM documents WHERE session_id = s.id) AS docs,
  (SELECT overall_score FROM validation_results WHERE session_id = s.id) AS val_score,
  (SELECT decision FROM kyc_records WHERE session_id = s.id) AS decision
FROM sessions s ORDER BY s.created_at DESC LIMIT 5;"
```

Expected: your session shows `msg_count` > 0, `docs` = 2, `val_score` between 0 and 100, `decision` is `approved`/`flagged`/`rejected`.

- [ ] **Step 5: Tag ship**

```bash
git tag v0.1.0
```

- [ ] **Step 6: Final commit (if anything changed)**

```bash
git status
# If clean, nothing to commit.
```

---

## Appendix A — Execution tips

- **The whole plan takes ~20-40 hours of focused work** depending on Ollama model speed and whether you've used LangGraph before.
- **Phases 0-6 are plumbing** — do them in one sitting if you can; context-switching across the scaffold is costlier than across agents.
- **Phases 7-11 are TDD sweet spots** — each agent has pure math that tests well. Don't skip the tests; they pay off when you change thresholds later.
- **Phases 13-15 are iterative UI** — prefer running `npm run dev` and a live reload loop over executing the plan verbatim. The code here is correct, but UIs are best honed by eye.
- **If a step fails:** don't push through. Read the error, check `docker compose logs <svc>`, and fix the underlying issue. The most common failures are (1) Ollama unreachable from container, (2) stale checkpoint with a different state shape than the current code expects (fix: `docker compose exec postgres psql -c 'TRUNCATE checkpoints CASCADE;'` — domain tables stay intact).

## Appendix B — What this plan does NOT cover

The spec's §3 non-goals still hold:

- No user accounts / multi-tenant auth
- No liveness (MediaPipe Face Mesh) — out of scope
- No admin reviewer UI for flagged cases
- No TTS / audio responses
- No i18n framework — Hindi/English only, via orchestrator prompting
- No production-grade retention policies or rate limiting

Track those as follow-ups in the spec's §14 Future work.

---

## Self-review notes

*(added after initial write, per the writing-plans skill's self-review instruction)*

1. **Spec coverage check:**
   - §5.2 repo layout — covered by Tasks 1, 2.
   - §6 multi-agent (7 agents) — each agent has its own task: orchestrator (23-25), intake (27-29), validation (31-32), biometric (33-34), geolocation (35-36), compliance (38-40), decision (37).
   - §7 persistence contract — models + migration in 13-14; each agent's write is in its own task; orchestrator writes messages in chat/upload/capture/confirm routers.
   - §8 frontend UX — Phase 13 (shell) + Phase 14 (widgets) + Phase 15 (camera + FAQ).
   - §9 Langfuse — service in Phase 1, client in Task 16. Per-agent `@observe` decoration is a to-do; add it once the agents are stable (the client is already wired so adding `@observe()` is one-line per function).
   - §10 deployment — Phase 1 (data services), Task 11 (api), Task 52 (web).
   - §11 setup story — Task 53 README rewrite.
2. **Placeholder scan:** no "TBD" / "fill in later" / "similar to above". Every code step has full code.
3. **Type consistency:**
   - `next_required` literals used in `state.py` and routers all match (spot-checked `wait_for_aadhaar_image`, `wait_for_pan_confirm`, `cross_validate`).
   - `Widget.type` values (`upload` | `editable_card` | `selfie_camera` | `verdict`) consistent between backend `schemas/chat.py`, frontend `api/schemas.ts`, and the `widget_for` mapping.
   - `doc_type` values `"aadhaar"` / `"pan"` consistent across `documents` model, `extract_fields`, confirm router, and web API client.
4. **Gaps I noticed and left deliberate:**
   - Langfuse `@observe()` decoration on each agent is not its own task. Add after agents settle (the client is ready).
   - The orchestrator's language-switch "2 consecutive turns" tracker uses a private `_lang_streak` key — it's carried in state but not typed in `KYCState`. Acceptable for a POC.
   - No tests for the web layer — shadcn + Vite + React Testing Library setup would add another phase; out of scope here.


