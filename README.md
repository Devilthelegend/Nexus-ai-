# 🧠 NexusAI

> Multi-tenant **AI Knowledge Intelligence Platform** — upload your documents and
> get **grounded, cited answers** through Retrieval-Augmented Generation,
> streaming chat, and tool-using agents.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00)
![Tests](https://img.shields.io/badge/tests-76%20passing-brightgreen)
![AI](https://img.shields.io/badge/AI-runs%20offline%20(mock)-informational)

NexusAI is a production-style backend that layers RAG, conversational chat and
autonomous agents on top of a cleanly architected, multi-tenant API. Every
tenant's data — users, documents, vectors, conversations and agent runs — is
isolated by `workspace_id`. The AI layer is provider-abstracted, so the whole
system runs **fully offline with deterministic mock providers** (no API keys or
external services required) and swaps to real Postgres / Qdrant / LLM backends
purely through configuration.

## ✨ Features

- 🔐 **Multi-tenant auth & isolation** — JWT access + rotating refresh tokens with
  server-side revocation, Argon2 password hashing, per-workspace RBAC; every
  query scoped by `workspace_id`.
- 📄 **Document ingestion** — upload → extract (`txt`/`md`/`html`/`pdf`/`docx`) →
  chunk → embed → index, with idempotent content checksums and a
  dead-letter / replay path for failed documents.
- 🔎 **Hybrid RAG retrieval** — dense + keyword recall fused with Reciprocal Rank
  Fusion, reranked and packed into a token budget, returning inline **citations**.
- 💬 **Streaming chat** — Server-Sent Events token streaming, persisted
  conversation history, and a workspace-scoped **semantic answer cache**.
- 🤖 **Agents** — a bounded, tool-using orchestrator with short- and long-term
  memory and a full `AgentRun` audit trail (steps, tool calls, cost, latency).
- 🖥️ **Built-in web UI** — a zero-dependency single-page app at `/ui` for login,
  uploads and streaming chat with citations.
- 📈 **Ops-ready** — Prometheus metrics, correlation IDs, structured JSON logs,
  security headers, rate limiting, health/readiness probes, plus Docker,
  Kubernetes and Terraform artifacts and GitHub Actions CI/CD.

## 🧱 Architecture

```
                          REST + SSE
   ┌────────┐  ───────────────────────────▶  ┌─────────────────────────┐
   │ client │                                │    FastAPI (API tier)   │
   └────────┘  ◀───────────────────────────  └────────────┬────────────┘
       middleware: auth · rate limit · metrics ·           │
       security headers · correlation id · error envelope  │
                                                            ▼
                                              ┌─────────────────────────┐
                                              │  Services / domain logic │
                                              └────────────┬────────────┘
             ┌───────────────┬─────────────────────────────┼──────────────┐
             ▼               ▼                              ▼              ▼
       PostgreSQL      Qdrant (vectors)               Redis (cache/    LLM & embed
       (records)       tenant-scoped                  queue/limits)    providers
                                                            │         (abstracted)
                                                            ▼
                                                     Celery worker
                                            extract → chunk → embed → index
```

Provider abstraction keeps LLM & embedding backends behind protocols, with
deterministic "mock" implementations used for offline runs and the test suite.

## Tech stack

FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Alembic · Redis · Celery ·
Qdrant · JWT auth · Docker · Kubernetes.

## 🚀 Quick start

### Option A — Zero-infra local run (recommended first)

No database server, no Docker, **no API keys**. Uses SQLite + deterministic mock
AI providers + an in-memory vector store.

```bash
# 1. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. Configure (the defaults are already zero-infra)
cp .env.example .env                 # Windows: copy .env.example .env

# 3. Run the API (tables auto-create on startup for SQLite)
python -m app.main
```

Then open **http://localhost:8000/** — it redirects to the built-in UI at
`/ui`. Interactive API docs are at **/docs**.

> Prefer [uv](https://docs.astral.sh/uv/)? Replace step 1 with
> `uv venv --python 3.12 && uv pip install -e ".[dev]"`.

### Option B — Full production-like stack (Docker)

Runs against PostgreSQL, Redis and Qdrant with Alembic migrations.

```bash
cp .env.example .env
# In .env, switch to the production-like values:
#   DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus
#   VECTOR_BACKEND=qdrant
#   DB_AUTO_CREATE=false
docker compose up -d postgres redis qdrant
alembic upgrade head
python -m app.main
```

Or bring up everything (API + services) with `docker compose up --build`.

## 🖥️ Web UI

A self-contained single-page app is served at **`/ui`** from the same origin as
the API (so it shares auth and needs no CORS). It covers register / login,
workspace creation, document upload, and streaming chat with citations — enough
to exercise the full RAG flow from a browser.

## 📡 API overview

Versioned under `/api/v1`; OpenAPI at `/openapi.json`, Swagger UI at `/docs`.
Every failure shares one envelope: `{ code, message, request_id, details }`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register` · `/auth/login` · `/auth/refresh` · `/auth/logout` · `GET /auth/me` |
| Workspaces | `POST` / `GET /workspaces` · `GET /workspaces/{id}` · `POST /workspaces/{id}/members` |
| Documents | `POST /workspaces/{wid}/documents` (multipart) · list / get · `GET …/{id}/status` · `DELETE …/{id}` · `POST …/{id}/reprocess` |
| Conversations | `POST` / `GET …/conversations` · messages · `POST …/messages/stream` (SSE) |
| Agents | `POST …/agent/runs` · `GET …/agent/runs` · `GET …/agent/runs/{id}` |
| Ops | `GET /healthz` · `GET /readyz` · `GET /metrics` |

## ⚙️ Configuration

12-factor settings load from the environment / `.env` (`app/core/config.py`).
`.env.example` documents every option; the most important:

| Variable | Purpose | Offline default |
|---|---|---|
| `DATABASE_URL` | System of record | `sqlite+aiosqlite:///./nexus.db` |
| `DB_AUTO_CREATE` | Create tables on startup (skip Alembic) | `true` (local only) |
| `VECTOR_BACKEND` | `memory` or `qdrant` | `memory` |
| `LLM_PROVIDER` / `EMBEDDING_PROVIDER` | AI backends | `mock` / `mock` |
| `INGEST_EAGER` | Ingest inline (no Celery worker) | `true` |
| `JWT_SECRET_KEY` | Token signing secret (**set a strong one in prod**) | dev placeholder |
| `RATE_LIMIT_*`, `SEMANTIC_CACHE_*` | Hardening toggles | enabled |

## 🤖 Enabling a real LLM (optional)

`mock` is the default so the app, tests and CI run offline with **no API key,
no cost, and deterministic output**. The mock still exercises the entire RAG
pipeline (embed → retrieve → fuse → rerank → assemble context → cite); only the
final text generation is templated.

To use real generative answers, point `LLM_PROVIDER` at the OpenAI-compatible
provider and supply credentials **via environment variables only** — never
commit a key. It works with OpenAI and any OpenAI-compatible endpoint
(e.g. Groq, OpenRouter, or a local server) by setting `LLM_BASE_URL`.

```bash
# In your host's secret/env settings (or a local, gitignored .env):
LLM_PROVIDER=openai
LLM_API_KEY=sk-...              # your key — kept out of the repo
LLM_MODEL=gpt-4o-mini           # any chat model the endpoint supports
# Optional:
LLM_BASE_URL=https://api.openai.com/v1   # e.g. Groq/OpenRouter/local URL
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=0                # 0 = provider default (no explicit cap)
```

| Variable | Purpose | Default |
|---|---|---|
| `LLM_API_KEY` | Credential for the provider (env/secret only) | *(empty)* |
| `LLM_MODEL` | Chat model identifier | `mock-chat-001` |
| `LLM_BASE_URL` | OpenAI-compatible API base URL | `https://api.openai.com/v1` |
| `LLM_TEMPERATURE` | Sampling temperature | `0.2` |
| `LLM_MAX_TOKENS` | Completion cap (`0` = provider default) | `0` |

> **Security:** the key lives only in an environment variable / the host's
> secret manager — never in source, committed `.env`, logs, or images
> (`.env` is gitignored). Leave `LLM_PROVIDER=mock` for tests and CI so they
> stay free and deterministic.

## ✅ Testing & quality gates

The suite runs **entirely offline** (mock AI providers + in-memory SQLite) and
includes an evaluation gate (`tests/test_eval.py`) that asserts retrieval
quality (recall@k / precision@k / MRR).

```bash
pytest                 # full suite — 81 tests
ruff check .           # lint
ruff format --check .  # formatting
mypy app               # strict type-check
```

## Observability

- **Metrics:** Prometheus text-format metrics are exposed at `/metrics`
  (HTTP throughput, latency histogram, in-flight gauge, 5xx errors, and LLM
  token/cost counters). Pods are annotated for scraping.
- **Correlation IDs:** every request is tagged with an `X-Request-ID`
  (propagated if supplied), attached to structured JSON logs and echoed on the
  response and in error envelopes.
- **Errors:** all failures share one envelope —
  `{"code", "message", "request_id", "details"}`.
- **Optional tracing/error tracking:** OpenTelemetry (`OTEL_ENABLED`) and
  Sentry (`SENTRY_DSN`) initialise only when enabled and installed; no-ops
  otherwise.

## Security hardening

Security response headers (HSTS, CSP `frame-ancestors`, `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`) are applied to every
response, and a fixed-window rate limiter throttles abusive callers. Toggle via
`SECURITY_HEADERS_ENABLED` and `RATE_LIMIT_ENABLED`.

## Load testing

```bash
# Locust
locust -f load/locustfile.py --host http://localhost:8000

# k6
k6 run -e BASE_URL=http://localhost:8000 load/chat.js
```

## Deployment

- **Kubernetes:** manifests in `deploy/kubernetes/` (namespace, config,
  example secret, API + worker deployments with probes, service, HPA, ingress).
  `kubectl apply -f deploy/kubernetes/`.
- **Terraform:** an AWS skeleton in `deploy/terraform/` (VPC, EKS, RDS
  PostgreSQL, ElastiCache Redis). `terraform init && terraform plan`.
- **CI/CD:** `.github/workflows/ci.yml` (lint, format, type-check, tests, eval
  gate) and `cd.yml` (build/push image, deploy staging, smoke test, promote to
  production on tags).

## 🗂️ Project structure

```
app/
  api/        HTTP layer — versioned routers (v1) + shared dependencies
  core/       config, security, logging, metrics, rate limiting, error envelope
  db/         SQLAlchemy base, async engine and session
  models/     persistence models (workspace-scoped)
  schemas/    Pydantic request/response models
  services/   domain logic (auth, documents, retrieval, chat, agent, ingestion)
  ai/         provider abstractions (llm / embeddings / vectorstore) + mocks
  workers/    Celery app + ingestion task
  web/        built-in single-page UI (served at /ui)
migrations/   Alembic env + versioned migrations 0001–0005
deploy/       Kubernetes manifests + Terraform (AWS) skeleton
load/         Locust + k6 load tests
tests/        pytest suite (76 tests, offline)
```

## 🛣️ Production readiness & roadmap

The application is functionally complete across Phases 0–5 and fully green
offline. Before a real production deployment, these hardening items are on the
roadmap (none block local / demo use):

- **Durable stores:** run against **PostgreSQL + Qdrant** — the in-memory vector
  store is dev-only and not shared across replicas.
- **Shared state for scale-out:** back rate limiting, semantic cache and agent
  memory with **Redis** (currently in-process, per instance).
- **Object storage:** persist uploads to **S3 / GCS** instead of local disk
  (required for multi-replica and read-only container filesystems).
- **Readiness & secrets:** make `/readyz` check real dependencies, and fail-fast
  on a default / weak `JWT_SECRET_KEY` in production.
- **Compliance:** hard-delete / data-purge path and encryption-at-rest for
  regulated tenants.

## 📚 Documentation

- **Full technical documentation:** [`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md)
- **Design & architecture:** `NexusAI_Project_Design_Document.docx`,
  `NexusAI_System_Architecture_Document_v1.docx`

## 📄 License

No license file is included yet. Add a `LICENSE` (e.g. MIT) before making the
repository public if you want to permit reuse.
