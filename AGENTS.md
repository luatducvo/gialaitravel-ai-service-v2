# AGENTS.md - Mandatory AI Onboarding For gialaitravel-ai-service-v2

## Required First Action

Every AI agent working in this repository MUST do this before any analysis,
planning, code editing, debugging, testing, or answering:

1. Open `AGENTS.md`.
2. Read the entire file from top to bottom.
3. Treat it as the project map and operating contract for this repo.
4. Only after that, inspect task-specific source files, tests, and command
   output.

If you are reading this file through a tool that truncates output, continue
reading until EOF. Do not rely on a partial read of this file.

This file exists so an AI can understand the whole codebase quickly: architecture,
runtime request paths, boundaries, contracts, verification commands, and common
failure modes.

## How To Work In This Repo

Use this order for every non-trivial task:

1. Read all of `AGENTS.md`.
2. Read the source files listed in the relevant playbook section below.
3. Read the related tests.
4. Find an existing local pattern before adding a new one.
5. Make the smallest scoped change that satisfies the task.
6. Run the narrowest meaningful verification.
7. Report what changed, what passed, and what remains uncertain.

Do not skip straight to implementation when this file points to a workflow,
contract, or layer boundary.

## Project Snapshot

- Project name: `gialaitravel-ai-service-v2`
- Role: AI service for the Gia Lai travel system.
- Main consumers: frontend/backend clients that need travel chat and itinerary generation.
- Runtime surfaces:
  - WebSocket chat: `/ws/chat?session_id=<id>`
  - REST custom itinerary: `POST /api/v1/itineraries/custom`
- Language: Python 3.11+
- Web framework: FastAPI
- Validation/settings: Pydantic v2, `pydantic-settings`
- Package manager: `uv`
- AI stack: LangChain, LangGraph, LangSmith
- Vector database: Qdrant
- Logging: Loguru
- Deployment: Dockerfile and GitHub Actions workflow

## Source Of Truth Policy

- Current source code is the highest authority.
- Some existing docs/comments contain encoding noise or may be stale. Use them
  as hints, then verify against runtime code.
- Do not document or implement endpoints that source search cannot confirm.
- If source and docs disagree, report the discrepancy with file paths.
- If you add a dependency, public API, environment variable, shared schema,
  architecture rule, or new workflow convention, update this file in the same
  change.
- Never expose or commit `.env`, API keys, tokens, hidden prompts, system
  instructions, or secrets.

## Architecture Model

This repo follows Clean Architecture. Keep responsibilities inside their layer.

```text
src/
|-- core/           # Runtime settings and logging setup.
|-- domain/         # Pure entities and session memory. No FastAPI, DB, Qdrant, or LLM clients.
|-- application/    # Business logic, guardrails, LangGraph pipeline/nodes, services, interfaces.
|-- infrastructure/ # DB, Qdrant, repositories, vector DB, session persistence.
`-- presentation/   # FastAPI REST routers, WebSocket endpoint, API schemas, DI providers.
```

Layer rules:

- `domain/` must remain framework- and database-independent.
- `application/` owns use cases, graph orchestration, route optimization, prompt
  safety flow, and service-level business rules.
- `infrastructure/` owns external persistence and adapters.
- `presentation/` owns HTTP/WebSocket contracts, Pydantic request/response
  schemas, and FastAPI dependency injection.

## Whole-Repo Map

### Entry And Runtime

- `src/main.py`
  - Creates the FastAPI app.
  - Loads `.env`.
  - Adds CORS.
  - Runs `setup_logging()` on startup.
  - Includes `chat.router` and `itineraries.router`.
  - Local direct run uses `settings.APP_HOST` and `settings.APP_PORT`.

- `Dockerfile`
  - Uses `uv`.
  - Starts Uvicorn with env-driven host/port:
    `APP_HOST`, `APP_PORT`, and `PORT` fallback.

- `.github/workflows/ci-cd.yml`
  - CI/CD workflow for Docker image build/push.

### Core

- `src/core/config.py`
  - `Settings` class.
  - All runtime environment variables belong here.

- `src/core/logging.py`
  - Loguru setup.

### Domain

- `src/domain/working_memory.py`
  - `WorkingMemory` and `detect_step`.
  - Tracks session step, trip constraints, derived filters, current itinerary,
    learned constraints, and messages.

- `src/domain/itinerary.py`
  - Structured itinerary domain models: `Activity`, `DayPlan`, `Itinerary`.

- `src/domain/entities.py`
  - Older/general domain entities.

### Application

- `src/application/graph/pipeline.py`
  - Active LangGraph workflow.
  - Defines `create_workflow()` and `run_pipeline()`.
  - Runs guardrails before graph invocation.

- `src/application/graph/state.py`
  - `AgentState` shared between LangGraph nodes.

- `src/application/graph/nodes/router.py`
  - Routes the graph based on `WorkingMemory.current_step`.

- `src/application/graph/nodes/cold_start.py`
  - Collects required trip fields and derives filters/preferences.

- `src/application/graph/nodes/elicitation.py`
  - Collects user vibe/preferences.

- `src/application/graph/nodes/qdrant_search.py`
  - Active Qdrant retrieval node for WebSocket planning.

- `src/application/graph/nodes/route_optimizer.py`
  - Route ordering, distance estimates, route summary metadata.

- `src/application/graph/nodes/llm_planner.py`
  - LLM itinerary generation.

- `src/application/graph/nodes/critic.py`
  - Refine/confirm/realtime question handling.

- `src/application/graph/nodes/finalize.py`
  - Finalized itinerary response path.

- `src/application/graph/nodes/planner.py`
  - Legacy/reference planner path. Do not assume it is active unless pipeline
    edges prove it.

- `src/application/graph/nodes/reflection.py`
  - Legacy/reference reflection path. Do not assume it is active unless pipeline
    edges prove it.

- `src/application/guardrails.py`
  - Gia Lai scope and prompt-safety guardrails.

- `src/application/services/itinerary_service.py`
  - REST custom itinerary orchestration from backend-selected POI snapshots.

- `src/application/services/distance.py`
  - Distance helpers.

- `src/application/services/realtime_search.py`
  - Tavily realtime enrichment with timeout/retry behavior.

- `src/application/interfaces.py`
  - Application-layer repository/service interfaces.

- `src/application/use_cases.py`
  - Generic/example use cases.

### Infrastructure

- `src/infrastructure/qdrant_repo.py`
  - Qdrant search implementation.
  - Must preserve payload metadata for downstream planner/validator logic.

- `src/infrastructure/session_store.py`
  - In-memory session store for WebSocket `WorkingMemory`.

- `src/infrastructure/database.py`
  - Database connection setup.

- `src/infrastructure/models.py`
  - SQLAlchemy models.

- `src/infrastructure/repositories.py`
  - Repository implementations.

- `src/infrastructure/vector_db.py`
  - Vector DB setup/helper code.

### Presentation

- `src/presentation/ws/chat.py`
  - WebSocket endpoint at `/ws/chat`.
  - Loads/saves session memory and streams `ws_responses`.

- `src/presentation/api/itineraries.py`
  - REST endpoint at `POST /api/v1/itineraries/custom`.
  - Wraps success with `BaseResponse`.

- `src/presentation/api/items.py`
  - Example/generic item API. Do not treat it as the itinerary contract.

- `src/presentation/schemas.py`
  - `BaseResponse`, `ErrorResponse`, and generic item schemas.

- `src/presentation/schemas_itinerary.py`
  - REST custom itinerary request/response schemas.

- `src/presentation/schemas_ws.py`
  - WebSocket protocol schemas and message type docs.

- `src/presentation/dependencies.py`
  - FastAPI dependency providers.

### Tests And Local Utilities

- `tests/test_guardrails_and_route_optimizer.py`
  - Main regression anchor for guardrails, route optimization, custom itinerary
    behavior, day grouping, hotel/start-location handling, and POI validation.

- `tests/test_client.html`
  - Manual WebSocket test client.

- `tests/test_search.py`, `tests/check_qdrant.py`, `tests/check_methods.py`
  - Qdrant/search diagnostic scripts/tests.

- `tests/test_langsmith.py`
  - LangSmith diagnostic test.

## Active Runtime Flows

### FastAPI Startup Flow

1. `src/main.py` loads `.env` with `load_dotenv(override=True)`.
2. Builds the `FastAPI` app.
3. Adds permissive CORS for backend/frontend integration.
4. Runs Loguru setup on startup.
5. Includes:
   - `src.presentation.ws.chat.router`
   - `src.presentation.api.itineraries.router`
6. Direct local run uses:
   - `settings.APP_HOST`
   - `settings.APP_PORT`

### WebSocket Chat Flow

Endpoint:

- URL: `/ws/chat`
- Query parameter: `session_id`
- Implementation: `src/presentation/ws/chat.py`

Flow:

1. Client connects to `/ws/chat?session_id=<id>`.
2. Endpoint accepts the socket and loads memory with `get_session(session_id)`.
3. If memory is a fresh cold-start session, it runs the pipeline once with an
   empty message so the client receives a cold-start form response.
4. For each incoming text frame:
   - Parse JSON.
   - Read `payload`.
   - Use `payload.chip_value` first, otherwise `payload.message`.
   - Reload session memory.
   - Call `run_pipeline(session_id, user_message, memory, payload=payload)`.
   - Save returned memory with `save_session(...)`.
   - Send each dict in `ws_responses` back to the client.
5. Invalid JSON produces an `error` response.
6. Unexpected processing failures are logged with Loguru and return a generic
   `error` response if the socket is still open.

Active graph in `src/application/graph/pipeline.py`:

```text
router_node
  -> cold_start
  -> elicit
  -> qdrant_search
  -> route_optimizer
  -> llm_planner
  -> END

router_node
  -> critic
  -> qdrant_search | finalized | END
```

`run_pipeline()` always checks `check_user_message_scope()` before invoking the
graph. Guardrail-blocked messages do not enter LangGraph.

### REST Custom Itinerary Flow

Endpoint:

- Method: `POST`
- URL: `/api/v1/itineraries/custom`
- Router: `src/presentation/api/itineraries.py`
- Schema: `src/presentation/schemas_itinerary.py`
- Service: `src/application/services/itinerary_service.py`

Contract:

- This endpoint is for the NestJS backend/internal Agent API.
- It receives backend-selected POI snapshots through `selectedPois`.
- It must not query Qdrant/database to resolve or replace POIs.
- It must not add, replace, or invent selected locations.
- It validates duplicate `poiId` values and Gia Lai coordinate bounds.
- `startLocation` is a route anchor, not a sightseeing activity.
- A hotel-like selected POI can be used as the start anchor and excluded from
  activity POIs.
- `optimizeRoute=false` must preserve user-selected ordering where route logic
  allows.
- LLM output must be validated against allowed selected activity POI IDs.

Service sequence:

1. Convert each `PoiInput` into planner/optimizer metadata.
2. Determine start anchor from explicit `startLocation` or hotel-like selected POI.
3. Remove that start anchor from activity POIs.
4. Split activity POIs by trip days.
5. Optimize each day's route through `optimize_route()`.
6. Add `day_number`, `day_route_order`, route order, and distance metadata.
7. Call `generate_itinerary_from_pois()`.
8. Normalize recoverable route-order IDs back to real POI IDs.
9. Raise if the LLM invented or returned unknown POI IDs.
10. Return `CustomItineraryResponse`, wrapped in `BaseResponse` by the router.

## Data And API Contracts

### REST Response Envelope

All REST routes must return:

- `BaseResponse[T]` for success.
- `ErrorResponse` for failures.

These are defined in `src/presentation/schemas.py`.

When adding a route, use `response_model=BaseResponse[YourSchema]`.

### WebSocket Message Types

Keep graph node response dicts aligned with `src/presentation/schemas_ws.py`.
Known server message types:

- `cold_start_form`
- `elicitation_question`
- `itinerary`
- `guardrail`
- `error`

### Working Memory Contract

`WorkingMemory` in `src/domain/working_memory.py` is the persistent session model.
It currently tracks:

- `session_id`
- `current_step`: `cold_start`, `elicit`, `plan`, `refine`, `finalized`
- `duration`, `group`, `transport`
- `intensity_filter`, `max_km_per_day`, `optimize_route`
- `vibe_query`
- `current_itinerary`
- `learned_constraints`
- `messages`

Do not add presentation-only fields to `WorkingMemory`. If data only belongs to
one request/response, keep it in presentation schemas or graph transient state.

### Graph State Contract

`AgentState` in `src/application/graph/state.py` carries:

- persistent-ish values: `memory`, `ws_responses`, `user_message`, `user_payload`
- transients: `qdrant_results`, `validated_pois`, `route_summary`,
  `critic_feedback`

When adding a graph node output, ensure downstream nodes and tests know whether
the value is persistent memory or one-turn transient state.

## Configuration Contract

Runtime configuration belongs in `src/core/config.py` on `Settings`.

Important settings:

- `PROJECT_NAME`
- `APP_HOST`
- `APP_PORT` with `PORT` fallback
- `LLM_PROVIDER`
- `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`
- `OPENAI_MODEL`, `GEMINI_MODEL`, `DEEPSEEK_MODEL`
- `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION_NAME`
- `EMBEDDING_MODEL`
- `TAVILY_API_KEY`, `TAVILY_TIMEOUT_SECONDS`, `TAVILY_MAX_RETRIES`
- `GOOGLE_MAPS_API_KEY`
- `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_TRACING_V2`,
  `LANGCHAIN_ENDPOINT`

Rules:

- Do not hardcode host, port, model, API key, collection, or timeout values in
  business logic.
- New runtime knobs must be added to `Settings` and `.env.example`.
- `.env` is local/runtime-only and must not be baked into Docker images.
- `.dockerignore` should continue excluding `.env`.
- Verify LangSmith naming before changing tracing: source uses `LANGCHAIN_*`,
  while `.env.example` may still show `LANGSMITH_*`.

## Qdrant And Retrieval Contract

WebSocket planning uses Qdrant through:

- `src/application/graph/nodes/qdrant_search.py`
- `src/infrastructure/qdrant_repo.py`

Rules:

- Preserve Qdrant payload metadata. Downstream code depends on `poi_id`,
  `poi_name`, `lat`, `lng`, `cost`, `category`, `tags`, and `intensity_level`.
- Avoid empty filters that accidentally return no results.
- Prefer the active `qdrant_search -> route_optimizer -> llm_planner` graph path.
- Do not use Qdrant inside REST custom itinerary creation; that endpoint uses
  backend-provided `selectedPois`.

## Prompt Safety And Realtime Rules

- Keep user requests within Gia Lai travel scope.
- Guard against prompt injection, role override attempts, unrelated prompts, and
  requests for hidden/system instructions.
- Never reveal secrets, environment values, hidden prompts, or internal traces.
- Tavily realtime search is optional and must degrade gracefully.
- Tavily timeout/retry settings come from `TAVILY_TIMEOUT_SECONDS` and
  `TAVILY_MAX_RETRIES`.
- Event/detail answers should be concise and summary-oriented when sent to chat.

## Dependency And Coding Rules

- Use `uv`; do not add dependencies with raw `pip` commands.
- Add new dependencies to `pyproject.toml` via `uv add <package>` when possible.
- Use Loguru: `from loguru import logger`.
- Do not add `print()` or standard-library `logging` for application logs.
- Routers receive services through `Depends(...)` providers in
  `src/presentation/dependencies.py`.
- Application services should not import FastAPI request/response classes.
- Domain models should not import FastAPI, SQLAlchemy, Qdrant, LangChain, or
  infrastructure adapters.
- Keep refactors separate from behavior changes unless the user explicitly asks
  for both.

## Verification Commands

Run commands from the repository root in PowerShell.

Install/sync dependencies:

```powershell
uv sync
```

Run API locally:

```powershell
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Run all tests:

```powershell
uv run pytest
```

Fallback on this Windows checkout if `uv run pytest` has cache/profile issues:

```powershell
.venv\Scripts\python.exe -m pytest
```

Focused itinerary/guardrail/route tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_guardrails_and_route_optimizer.py
```

Lint:

```powershell
uv run ruff check src tests
```

Syntax compile check:

```powershell
.venv\Scripts\python.exe -m compileall src tests
```

For docs-only edits, tests are usually not required. Still inspect the diff and
state that the change was docs-only.

## Change Playbooks

### REST Itinerary Contract

Read first:

- `src/presentation/schemas_itinerary.py`
- `src/presentation/api/itineraries.py`
- `src/application/services/itinerary_service.py`
- `tests/test_guardrails_and_route_optimizer.py`

Verify:

- Focused pytest file above.
- Confirm response is still wrapped in `BaseResponse`.
- Confirm no Qdrant/database POI replacement was introduced.

### WebSocket Chat Or Graph Behavior

Read first:

- `src/presentation/ws/chat.py`
- `src/presentation/schemas_ws.py`
- `src/application/graph/pipeline.py`
- `src/application/graph/state.py`
- relevant node under `src/application/graph/nodes/`
- `src/domain/working_memory.py` if session state changes

Verify:

- Focused tests if behavior is covered.
- Manual reasoning over `ws_responses` shape.
- `tests/test_client.html` can be used for manual WebSocket checks.

### Qdrant Retrieval

Read first:

- `src/application/graph/nodes/qdrant_search.py`
- `src/infrastructure/qdrant_repo.py`
- `src/core/config.py`
- `tests/test_search.py` or Qdrant diagnostic scripts if relevant

Verify:

- Preserve payload metadata.
- Avoid empty filter behavior.
- Do not mix this path into REST custom itinerary.

### Route Optimization Or Distances

Read first:

- `src/application/graph/nodes/route_optimizer.py`
- `src/application/services/distance.py`
- `src/application/services/itinerary_service.py`
- `tests/test_guardrails_and_route_optimizer.py`

Verify:

- Focused pytest file.
- Confirm `optimizeRoute=false` and start/hotel anchor behavior if touched.

### LLM Planner Or Critic

Read first:

- `src/application/graph/nodes/llm_planner.py`
- `src/application/graph/nodes/critic.py`
- `src/application/services/realtime_search.py`
- `src/application/guardrails.py`
- relevant tests

Verify:

- Prompt safety still runs before graph invocation.
- POI IDs are validated when itinerary output is generated from selected POIs.
- Tavily failure degrades gracefully.

### Config, Docker, Or CI/CD

Read first:

- `src/core/config.py`
- `.env.example`
- `Dockerfile`
- `.dockerignore`
- `.github/workflows/ci-cd.yml`
- `src/main.py`

Verify:

- New env vars are present in `Settings` and `.env.example`.
- Docker startup remains env-driven.
- `.env` remains excluded.

### Documentation

Read first:

- `AGENTS.md`
- relevant source files for the thing being documented
- existing docs under `docs/`, if present

Rules:

- Keep docs source-backed.
- Put team-shareable integration docs under `docs/`.
- Do not document imagined endpoints or stale architecture.
- If updating architecture or contracts, update `AGENTS.md`.

## Red Flags

Stop and inspect more carefully if any of these appear:

- A task claims WebSocket was replaced while source still exposes `/ws/chat`.
- Docs mention SSE/chat-stream endpoints but `rg` cannot find implementations.
- REST custom itinerary code tries to query Qdrant/database for selected POIs.
- LLM itinerary output is accepted without checking selected POI IDs.
- Qdrant results lose payload metadata such as `poi_id`.
- New env values are used without `Settings` and `.env.example` updates.
- New logging uses `print()` or standard `logging`.
- A bug fix includes broad unrelated refactors.
- `.env`, keys, prompts, or internal instructions are exposed.

## Final Response Contract

When finishing work:

- Summarize what changed.
- List files touched.
- List verification commands run and whether they passed.
- If no tests were run, say why.
- Mention unrelated dirty worktree files only if they affect the task.
- Be explicit about uncertainty and source-vs-doc discrepancies.
