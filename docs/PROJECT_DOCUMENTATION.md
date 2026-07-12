# NexusAI — Project Documentation

> AI Knowledge Intelligence Platform — a production-style backend combining
> scalable APIs, distributed processing, RAG, AI agents, vector search and
> cloud-native infrastructure.

This document is the single reference for **what** NexusAI is, **why** it was
built, **how** it is built, its **structure**, its **processes**, and the
**technologies** used. It reflects the current state of the codebase
(74 automated tests passing).

---

## 1. What this project is

NexusAI is a multi-tenant backend that lets teams upload their documents and
then **ask questions in natural language** and receive **grounded, cited
answers**. It layers three AI capabilities on top of a conventional,
well-engineered API:

1. **Retrieval-Augmented Generation (RAG)** — answers are generated from the
   user's own indexed documents, with inline source citations, never from the
   model's memory alone.
2. **Conversational chat** — streaming, low-latency answers within a
   persistent, auditable conversation history.
3. **Autonomous agents** — a bounded, tool-using orchestrator that can search
   the knowledge base and synthesise multi-step answers, with short- and
   long-term memory.

Everything is **workspace-scoped**: each tenant's users, documents, vectors,
conversations and agent runs are isolated and verified by tests.

### In scope (v1)
- Multi-tenant workspaces with authenticated users and RBAC.
- Document upload, async ingestion, chunking, embedding and indexing.
- Semantic + hybrid retrieval over workspace-scoped content.
- Conversational RAG chat with streaming responses and citations.
- Agent orchestration with tool use and short/long-term memory.
- Evaluation harness, observability, caching and cloud deployment artifacts.

### Out of scope (v1)
- Model fine-tuning / self-hosted training.
- Real-time collaborative document editing.
- Native mobile apps (API/backend only).
- Billing/payments (usage is metered, not billed).

---

## 2. Why it was developed

NexusAI is a **flagship portfolio project** designed to demonstrate the breadth
of skills expected of an AI Software Engineer / backend SDE:

- **Production engineering** — clean architecture, SOLID design, 12-factor
  config, migrations, testing, CI/CD and IaC.
- **Distributed systems** — async ingestion pipeline, queues, dead-letter
  handling, horizontal scaling of API and worker tiers.
- **AI engineering** — RAG, hybrid retrieval + reranking, prompt assembly,
  streaming, agents, semantic caching and an evaluation gate.
- **Operational maturity** — security hardening, observability (metrics,
  correlation IDs, structured logs), rate limiting and cost tracking.

The guiding principle (from the design document) is to **"build like a real
production system"** and treat security, testing and observability as
continuous concerns rather than a final afterthought.

### Target service-level objectives (SLOs)
| Concern | Target |
|---|---|
| API availability | 99.5% monthly |
| Read/API p95 latency (excl. LLM) | < 300 ms |
| Chat first-token p95 | < 2 s |
| Full chat answer p95 | < 6 s |
| Ingestion | 100-page PDF indexed < 90 s |
| Retrieval quality | recall@5 ≥ 0.85 on golden set |
| Concurrency | 200 concurrent chat sessions |

---

## 3. High-level architecture

```
            ┌──────────────┐        REST + SSE
 client ───▶│  FastAPI app │◀───────────────────────────┐
            │  (API tier)  │                             │
            └──────┬───────┘                             │
   middleware:     │  auth · validation · rate limit ·   │
   context id ·    │  metrics · security headers ·       │
   error envelope  │  error handling                     │
            ┌──────▼───────┐   ┌───────────┐   ┌─────────▼────────┐
            │  Services /  │──▶│ PostgreSQL │   │ Qdrant (vectors) │
            │ domain logic │   │ (records)  │   │  tenant-scoped   │
            └──────┬───────┘   └───────────┘   └──────────────────┘
                   │           ┌───────────┐   ┌──────────────────┐
                   ├──────────▶│   Redis    │   │ LLM / embedding  │
                   │           │ cache/queue│   │ providers (abstr)│
            ┌──────▼───────┐   └─────┬─────┘   └──────────────────┘
            │ Celery worker│◀────────┘  ingestion + async work
            └──────────────┘
```

- **API gateway (FastAPI):** authentication, request validation, routing,
  rate limiting, metrics, security headers and the consistent error envelope.
- **Services layer:** all business/domain logic (auth, workspaces, documents,
  retrieval, chat, agents), independent of transport and vendor.
- **Data stores:** PostgreSQL (system of record), Redis (cache/broker/rate
  limits), Qdrant (vector index with payload filtering for tenant scoping).
- **Workers:** Celery consumes the ingestion queue (extract → chunk → embed →
  index) with dead-letter handling; runs inline when eager mode is enabled.
- **Provider abstraction:** LLM and embedding backends sit behind protocols so
  the stack runs fully offline with deterministic "mock" providers in tests.

### Ingestion data flow
1. Upload accepted, checksummed, stored; `Document` row created as `queued`.
2. Worker extracts text, cleans, chunks with overlap + structural metadata.
3. Chunks embedded in batches; vectors upserted to Qdrant with payload.
4. Status transitions to `indexed`; failures routed to a dead-letter queue.

### Query / RAG data flow
1. User message received; query embedded (and cache checked).
2. Hybrid retrieval (dense + keyword) → candidates → RRF fusion → rerank.
3. Context assembled within a token budget; prompt templated with citations.
4. LLM answer streamed to the client; message, citations and usage persisted.

---

## 4. Technology stack

| Layer | Technologies |
|---|---|
| Language / runtime | Python 3.12+ |
| Web framework | FastAPI, Starlette, Uvicorn |
| Validation / config | Pydantic v2, pydantic-settings |
| ORM / DB | SQLAlchemy 2.x (async), PostgreSQL, Alembic (migrations) |
| Async DB driver | asyncpg (prod), aiosqlite (tests) |
| Cache / queue | Redis, Celery (dead-letter handling) |
| Vector store | Qdrant (payload filtering for tenant scope); in-memory backend for offline/dev |
| Auth | JWT (PyJWT), Argon2 password hashing (argon2-cffi) |
| AI | Provider-abstracted LLM + embedding APIs, RAG, agent orchestration, semantic cache |
| Observability | Prometheus-style metrics, structured JSON logs, correlation IDs; optional OpenTelemetry + Sentry hooks |
| Testing | pytest, pytest-asyncio, httpx (ASGI transport) |
| Tooling | Ruff (lint + format), mypy (strict), pre-commit |
| Packaging | hatchling, pyproject.toml |
| Containers / IaC | Docker, docker-compose, Kubernetes manifests, Terraform (AWS) |
| CI/CD | GitHub Actions (CI + CD) |
| Load testing | Locust, k6 |

**Design choice — zero hard AI dependencies:** the LLM, embedding and vector
layers are protocols with deterministic "mock" implementations, so the entire
test suite runs offline with no API keys or external services.

---

## 5. Project structure

```
nexus/
├─ app/                       # application source
│  ├─ main.py                 # app factory: middleware, routers, error handlers
│  ├─ api/                    # HTTP layer
│  │  ├─ deps.py              # shared FastAPI dependencies (auth, db, providers)
│  │  ├─ metrics.py           # /metrics Prometheus endpoint
│  │  └─ v1/                  # versioned routers
│  │     ├─ auth.py           # register/login/refresh/logout/me
│  │     ├─ workspaces.py     # workspace CRUD + members
│  │     ├─ documents.py      # upload/list/get/status/delete/reprocess
│  │     ├─ conversations.py  # conversations + chat (sync + SSE stream)
│  │     ├─ agents.py         # agent runs
│  │     ├─ health.py         # /healthz, /readyz
│  │     └─ router.py         # aggregate v1 router
│  ├─ core/                   # cross-cutting concerns
│  │  ├─ config.py            # typed 12-factor settings
│  │  ├─ security.py          # password hashing, JWT helpers
│  │  ├─ logging.py           # JSON log formatter (+ request_id)
│  │  ├─ context.py           # request/correlation id ContextVar
│  │  ├─ metrics.py           # zero-dep metrics registry (Counter/Gauge/Histogram)
│  │  ├─ observability.py     # metrics + request-context middleware, tracing hooks
│  │  ├─ security_headers.py  # HSTS/CSP/X-Frame-Options etc.
│  │  ├─ errors.py            # consistent error envelope + handlers
│  │  └─ ratelimit.py         # fixed-window rate limiter
│  ├─ ai/                     # provider abstractions
│  │  ├─ llm/                 # LLM protocol + mock provider
│  │  ├─ embeddings/          # embedding protocol + mock + factory
│  │  └─ vectorstore/         # vector store protocol + memory/qdrant + factory
│  ├─ db/                     # SQLAlchemy base, engine, session
│  ├─ models/                 # persistence models (see §6)
│  ├─ schemas/                # Pydantic request/response models
│  ├─ services/               # domain/business logic
│  │  ├─ auth_service.py, user_service.py, token_service.py
│  │  ├─ workspace_service.py, conversation_service.py
│  │  ├─ document_service.py, retrieval.py, chat_service.py
│  │  ├─ semantic_cache.py    # workspace-scoped answer reuse
│  │  ├─ ingestion/           # extract → chunk → embed → index pipeline
│  │  └─ agent/               # orchestrator, tools, memory
│  ├─ eval/                   # offline evaluation harness + metrics
│  └─ workers/                # Celery app + tasks
├─ migrations/                # Alembic env + versioned migrations 0001–0005
├─ tests/                     # pytest suite (74 tests)
├─ deploy/
│  ├─ kubernetes/             # namespace, config, secret example, deployments,
│  │                          # service, HPA, ingress
│  └─ terraform/              # AWS skeleton: VPC, EKS, RDS, ElastiCache
├─ load/                      # locustfile.py + chat.js (k6)
├─ .github/workflows/         # ci.yml + cd.yml
├─ docker-compose.yml         # local stack (postgres, redis, qdrant, api)
├─ Dockerfile                 # API/worker image
├─ alembic.ini                # migration config
├─ pyproject.toml             # deps, tooling, pytest config
└─ README.md                  # quick start + operational notes
```

---

## 6. Data model

All tenant-owned rows carry `workspace_id` for isolation. Managed via Alembic
migrations `0001`–`0005`.

| Entity | Key fields | Notes |
|---|---|---|
| **User** | id, email, hashed_password, status, created_at | Argon2 hashes |
| **Workspace** | id, name, owner_id, plan, created_at | tenant boundary |
| **Membership** | user_id, workspace_id, role | owner/admin/member/viewer (RBAC) |
| **Document** | id, workspace_id, filename, mime_type, size, status, checksum | lifecycle status; checksum idempotency |
| **Chunk** | id, document_id, ordinal, text, token_count, metadata | page/section metadata |
| **Embedding** | chunk_id, vector_id, model, dimension | vectors live in Qdrant |
| **Conversation** | id, workspace_id, user_id, title, created_at | |
| **Message** | id, conversation_id, role, content, tokens, citations | grounded turns |
| **RefreshToken** | rotating refresh tokens with revocation | supports logout/rotation |
| **AgentRun** | id, conversation_id, status, steps, tool_calls, cost_usd, latency_ms | full audit trail |

**Migrations:** `0001_initial` (users/workspaces/memberships) → `0002_documents`
(documents/chunks/embeddings) → `0003_conversations` (conversations/messages) →
`0004_refresh_tokens` → `0005_agent_runs`.

---

## 7. API surface

Versioned under `/api/v1`; OpenAPI auto-generated at `/openapi.json` and docs at
`/docs`. Every error uses the envelope `{code, message, request_id, details}`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Workspaces | `POST /workspaces`, `GET /workspaces`, `GET /workspaces/{id}`, `POST /workspaces/{id}/members` |
| Documents | `POST /workspaces/{wid}/documents` (multipart), `GET …/documents`, `GET …/documents/{id}`, `GET …/documents/{id}/status`, `DELETE …/documents/{id}`, `POST …/documents/{id}/reprocess` |
| Conversations | `POST …/conversations`, `GET …/conversations`, `GET …/conversations/{id}`, `GET …/conversations/{id}/messages`, `POST …/conversations/{id}/messages`, `POST …/conversations/{id}/messages/stream` (SSE) |
| Agents | `POST …/conversations/{cid}/agent/runs`, `GET …/agent/runs`, `GET …/agent/runs/{run_id}` |
| Ops | `GET /healthz` (liveness), `GET /readyz` (readiness), `GET /metrics` (Prometheus) |

All tenant routes are gated by workspace/conversation ownership checks for
strict tenant isolation.

---

## 8. How it was developed — phased delivery

The project follows the design document's six phases, each with explicit exit
criteria. Testing, security and observability were built continuously, not
deferred.

| Phase | Focus | Key deliverables |
|---|---|---|
| **0 — Foundations** | Repo + skeleton | FastAPI app, health probes, docker-compose, Dockerfile, CI skeleton, tooling (ruff/mypy/pre-commit) |
| **1 — Auth & multi-tenancy** | Backend foundation | Data model + migrations, JWT with refresh rotation/revocation, RBAC, workspace CRUD, tenant isolation, rate limiting |
| **2 — Ingestion** | Async pipeline | Upload API + validation, extract→chunk→embed→index, status tracking, DLQ/replay, Celery skeleton |
| **3 — RAG & chat** | Retrieval + generation | Hybrid retrieval (dense + keyword), RRF + rerank, token-budgeted context, streaming chat with citations, semantic cache |
| **4 — Agents & memory** | Orchestration | Bounded agent orchestrator, tool registry, step/cost guards, short- + long-term memory, `AgentRun` audit trail |
| **5 — Hardening** | Production readiness | Observability (metrics, correlation IDs, structured logs), security headers, consistent error envelope, load tests, Kubernetes + Terraform, CI/CD |

### Engineering approach
- **Additive, non-breaking changes** — each phase layered on the previous
  without reverting prior architecture (e.g. the refresh-token system and
  streaming logic were preserved throughout).
- **Test-first verification** — the suite is kept green after every change
  (currently **74 passing**).
- **Clean architecture / SOLID** — transport, domain and provider layers are
  decoupled behind protocols and dependency injection.

---

## 9. Cross-cutting concerns

### Security
- Argon2 password hashing; no plaintext credentials.
- Short-lived JWT access tokens + rotating refresh tokens with revocation.
- RBAC enforced per workspace; all queries scoped by `workspace_id`.
- Pydantic input validation; strict file-type and size checks on upload.
- Security response headers (HSTS, CSP `frame-ancestors`, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`).
- Per-user / per-IP fixed-window rate limiting.

### Observability
- **Metrics:** `/metrics` exposes HTTP throughput, latency histogram, in-flight
  gauge, 5xx counter and LLM token/cost counters (Prometheus text format).
- **Correlation IDs:** each request carries an `X-Request-ID` (propagated if
  supplied), attached to structured JSON logs and echoed on responses/errors.
- **Optional tracing/error tracking:** OpenTelemetry (`OTEL_ENABLED`) and
  Sentry (`SENTRY_DSN`) initialise only when enabled and installed; no-ops
  otherwise (offline by default).

### Reliability
- Idempotency via document checksums; dead-letter queue with replay.
- Liveness/readiness probes for orchestrated rollouts.
- Independent horizontal scaling of API and worker tiers (HPA).
- Semantic cache reduces repeated LLM cost/latency.

---

## 10. Testing

- **Framework:** pytest + pytest-asyncio; httpx `ASGITransport` drives the app
  in-process; SQLite (aiosqlite) with a shared in-memory engine per test.
- **Offline by design:** deterministic mock LLM/embedding/vector providers mean
  no network or API keys are required.
- **Coverage areas:** auth, workspaces, ingestion, vector store, RAG, agents,
  agent memory, rate limiting, semantic cache, evaluation harness, and
  observability/security (`tests/test_observability.py`).
- **Status:** **74 tests passing, 0 failures/errors.**
- **Eval gate:** `tests/test_eval.py` asserts retrieval quality (recall@k /
  precision@k / MRR) and runs as a CI gate.

```bash
pytest                 # full suite
pytest tests/test_eval.py -q   # eval gate only
```

---

## 11. Deployment

- **Containers:** `Dockerfile` builds a slim image used by both the API and the
  Celery worker; `docker-compose.yml` boots postgres + redis + qdrant + api for
  local development.
- **Kubernetes (`deploy/kubernetes/`):** namespace, ConfigMap, example Secret,
  API + worker Deployments (probes, non-root, read-only rootfs, Prometheus
  scrape annotations), Service, HPA (CPU/memory) and TLS Ingress.
- **Terraform (`deploy/terraform/`):** AWS skeleton — VPC, EKS cluster, RDS
  PostgreSQL (Multi-AZ), ElastiCache Redis — with variables and outputs.
- **CI/CD (`.github/workflows/`):**
  - `ci.yml` — lint (ruff), format check, type-check (mypy), tests, eval gate.
  - `cd.yml` — build/push image to GHCR → deploy staging → smoke test →
    promote to production on version tags.

---

## 12. Local development

Requirements: Python 3.12+, Docker, and [uv](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres redis qdrant
alembic upgrade head
python -m app.main            # serves http://localhost:8000 (docs at /docs)
```

Load testing against a running stack:

```bash
locust -f load/locustfile.py --host http://localhost:8000
k6 run -e BASE_URL=http://localhost:8000 load/chat.js
```

---

## 13. Configuration (12-factor)

Settings load from environment / `.env` (case-insensitive) via
`app/core/config.py`. Notable groups:

- **App:** `ENVIRONMENT`, `DEBUG`, `API_V1_PREFIX`.
- **Data stores:** `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `VECTOR_BACKEND`.
- **Auth:** `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`.
- **AI:** `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `LLM_COST_PER_1K_TOKENS`.
- **RAG:** `RETRIEVAL_TOP_K`, `RERANK_TOP_K`, `CONTEXT_TOKEN_BUDGET`.
- **Agent:** `AGENT_MAX_STEPS`, `AGENT_MEMORY_ENABLED`.
- **Hardening:** `RATE_LIMIT_*`, `SEMANTIC_CACHE_*`, `METRICS_ENABLED`,
  `SECURITY_HEADERS_ENABLED`, `OTEL_ENABLED`, `SENTRY_DSN`.

---

## 14. Current status & known gaps

**Healthy:** the application is functionally complete across Phases 0–5 with a
green test suite (74 tests). Business logic, RAG, agents, observability,
security and deployment artifacts are all in place.

**Gaps / next steps (honest assessment):**
- **Live-stack validation:** the suite runs against SQLite + mock providers.
  Running `docker compose up` and Alembic `0001–0005` against real
  PostgreSQL/Qdrant/Redis has not been exercised in this environment.
- **Production secret:** the default `JWT_SECRET_KEY` is a dev placeholder
  (pytest emits a key-length warning). Set a ≥32-byte secret in production.
- **Multi-provider LLM fallback, circuit breakers, and Grafana dashboards**
  from the design doc are scaffolded/optional rather than fully implemented.
- **CD workflow** is authored but has not been run against a real cluster.

These are deployment/validation activities rather than missing application
functionality.
