# AGENTS.md - Gia Lai Travel AI Service V2

This file is the first context an AI agent should read before touching this
repository. It is written as an operating manual: it tells you what the service
does, where the real runtime paths live, which patterns to follow, and how to
verify changes.

## 0. Global Agent Skills

Agent skills are installed globally in:

`C:\Users\BIT\.codex\skills`

Before any non-trivial task, check whether a skill applies. If it does, read the
full `SKILL.md` first and follow that workflow.

Slash aliases:

- `/spec` -> `spec-driven-development`
- `/plan` -> `planning-and-task-breakdown`
- `/build` -> `incremental-implementation` + `test-driven-development`
- `/build auto` -> `planning-and-task-breakdown` -> `incremental-implementation` + `test-driven-development`
- `/test` -> `test-driven-development`
- `/review` -> `code-review-and-quality`
- `/code-simplify` -> `code-simplification`
- `/ship` -> `shipping-and-launch`
- `/webperf` -> `browser-testing-with-devtools` when working on a web app

Default intent mapping:

- Feature or new behavior -> use a spec/plan first, then incremental implementation and tests.
- Bug or unexpected behavior -> use debugging workflow and reproduce/trace before editing.
- API/interface work -> use API/interface design workflow.
- Refactor/simplification -> preserve behavior and use focused tests.
- Security, prompt safety, secrets, external input -> use security hardening workflow.
- Docs or architecture notes -> update this file or docs in the same change.

## 1. Project Identity

- Project: `gialaitravel-ai-service-v2`
- Purpose: FastAPI AI service for the Gia Lai travel system.
- Runtime role: Receives chat or itinerary requests from frontend/backend, plans
  Gia Lai travel itineraries with LangGraph/LLMs, Qdrant retrieval, route
  optimization, and optional realtime enrichment.
- Language/runtime: Python 3.11+
- Package manager: `uv`
- Web framework: FastAPI
- Validation/settings: Pydantic v2 and `pydantic-settings`
- AI stack: LangChain, LangGraph, LangSmith
- Vector DB: Qdrant
- Logging: Loguru

## 2. Source Of Truth Rules

- Trust current source code over older docs. Some existing docs/comments may be
  stale or have encoding noise.
- Read the file you will edit, its tests, and one nearby pattern before changing
  behavior.
- Keep changes scoped. Do not refactor unrelated layers while fixing a narrow
  bug.
- Do not commit or expose `.env`, API keys, tokens, system prompts, or hidden
  instructions.
- If you introduce a new dependency, shared schema, public API, environment
  variable, or architectural rule, update this `AGENTS.md` in the same change.
- If requirements conflict with runtime evidence, report the discrepancy with
  file paths and ask only when the safe behavior is not inferable.

## 3. Clean Architecture Map

The service follows Clean Architecture. Do not mix responsibilities across
layers.

```text
src/
|-- core/           # Runtime settings and logging setup.
|-- domain/         # Pure entities and working memory. No FastAPI, DB, or LLM clients.
|-- application/    # Business logic, guardrails, LangGraph nodes, services, interfaces.
|-- infrastructure/ # DB/Qdrant/session persistence and external repository adapters.
`-- presentation/   # FastAPI routers, WebSocket endpoint, API schemas, dependencies.
```

Important files:

- `src/main.py`: FastAPI app, CORS, logging startup, router registration.
- `src/core/config.py`: `Settings`; all runtime env knobs belong here.
- `src/core/logging.py`: Loguru setup.
- `src/domain/working_memory.py`: session state and step detection.
- `src/domain/itinerary.py`: structured itinerary domain model.
- `src/application/graph/pipeline.py`: active LangGraph workflow and `run_pipeline`.
- `src/application/guardrails.py`: Gia Lai scope and prompt-safety checks.
- `src/application/services/itinerary_service.py`: REST custom itinerary orchestration.
- `src/application/services/distance.py`: distance helpers.
- `src/application/services/realtime_search.py`: Tavily realtime enrichment.
- `src/infrastructure/qdrant_repo.py`: Qdrant access and payload mapping.
- `src/infrastructure/session_store.py`: in-memory WebSocket session store.
- `src/presentation/ws/chat.py`: `/ws/chat` WebSocket endpoint.
- `src/presentation/api/itineraries.py`: `/api/v1/itineraries/custom` REST endpoint.
- `src/presentation/schemas.py`: `BaseResponse` and `ErrorResponse`.
- `src/presentation/schemas_itinerary.py`: REST itinerary request/response schemas.
- `src/presentation/schemas_ws.py`: WebSocket protocol schemas.
- `tests/test_guardrails_and_route_optimizer.py`: main regression anchor for
  guardrails, custom itinerary, day grouping, hotel/start location, and route behavior.

## 4. Active Runtime Paths

### 4.1 FastAPI Startup

`src/main.py`:

1. Loads `.env` with `load_dotenv(override=True)`.
2. Creates `FastAPI(title=settings.PROJECT_NAME)`.
3. Adds permissive CORS for the backend proxy path.
4. Calls `setup_logging()` on startup.
5. Includes WebSocket and itinerary routers:
   - `chat.router`
   - `itineraries.router`
6. Local direct run uses `settings.APP_HOST` and `settings.APP_PORT`.

Docker startup is env-driven in `Dockerfile` and must remain compatible with
`APP_HOST`, `APP_PORT`, and `PORT`.

### 4.2 WebSocket Chat Flow

Endpoint:

- URL: `/ws/chat`
- Query: `session_id=<id>`
- Implementation: `src/presentation/ws/chat.py`

Runtime flow:

1. Client connects to `/ws/chat?session_id=<id>`.
2. `get_session(session_id)` loads `WorkingMemory` from the in-memory session store.
3. Empty cold-start sessions auto-run `run_pipeline(session_id, "", memory)` so
   the client receives a cold-start form message.
4. Incoming WebSocket text must be JSON. The endpoint reads:
   - `payload`
   - `payload.chip_value` first, otherwise `payload.message`
5. `run_pipeline(session_id, user_message, memory, payload=payload)` runs the graph.
6. `save_session(final_state["memory"])` persists session memory.
7. Each item in `final_state["ws_responses"]` is sent back as JSON.

Active graph path:

```text
router_node
  -> cold_start
  -> elicit
  -> qdrant_search
  -> route_optimizer
  -> llm_planner
  -> END

refine path:
router_node -> critic -> qdrant_search | finalized | END
```

`run_pipeline` always calls `check_user_message_scope()` before invoking the
graph. If the guardrail blocks the message, it returns a `guardrail` WebSocket
response and does not invoke LangGraph.

### 4.3 REST Custom Itinerary Flow

Endpoint:

- Method: `POST`
- URL: `/api/v1/itineraries/custom`
- Router: `src/presentation/api/itineraries.py`
- Request/response schemas: `src/presentation/schemas_itinerary.py`
- Service: `src/application/services/itinerary_service.py`

Purpose:

This is an internal Agent API for the NestJS backend. The backend sends
already-selected, already-validated POI snapshots in `selectedPois`.

Hard contract:

- Do not query Qdrant or the database to resolve POIs for this endpoint.
- Do not add, replace, or invent selected locations.
- Validate duplicate `poiId` values and Gia Lai coordinate bounds in schemas.
- `optimizeRoute=false` must preserve user-selected order where route logic allows.
- `startLocation` is an optional route anchor, not a sightseeing POI.
- A hotel-like selected POI may be used as the route start anchor and excluded
  from activity POIs.
- The service validates the LLM output and raises if the itinerary contains POIs
  outside the allowed selected activity POIs.

Current service behavior:

1. Map `PoiInput` snapshots to planner dictionaries.
2. Determine `start_location` from explicit `startLocation` or a hotel-like POI.
3. Remove the start/hotel anchor from activity POIs.
4. Split activity POIs by trip days.
5. Optimize each day through `optimize_route()`.
6. Attach `day_number`, `day_route_order`, route order, and distance metadata.
7. Call `generate_itinerary_from_pois()`.
8. Normalize recoverable route-order IDs from the LLM back to real POI IDs.
9. Reject invented/unknown POI IDs.
10. Return `CustomItineraryResponse` wrapped by `BaseResponse`.

## 5. Data Contracts

### 5.1 REST Envelope

All REST responses must use:

- `BaseResponse[T]` for success.
- `ErrorResponse` for errors.

Defined in `src/presentation/schemas.py`.

When adding a REST route, use `response_model=BaseResponse[YourDataSchema]`.

### 5.2 WebSocket Message Types

WebSocket responses are listed in `src/presentation/schemas_ws.py`.
Expected server message types include:

- `cold_start_form`
- `elicitation_question`
- `itinerary`
- `guardrail`
- `error`

The WebSocket endpoint currently sends raw dicts from graph nodes; keep those
dicts aligned with schema names and fields.

### 5.3 Working Memory

`WorkingMemory` in `src/domain/working_memory.py` tracks:

- `session_id`
- `current_step`: `cold_start`, `elicit`, `plan`, `refine`, `finalized`
- cold-start fields: `duration`, `group`, `transport`
- derived route/search settings: `intensity_filter`, `max_km_per_day`, `optimize_route`
- elicitation: `vibe_query`
- itinerary: `current_itinerary`
- reflection: `learned_constraints`
- chat history: `messages`

Do not add presentation-specific fields to domain memory unless the state is
truly part of the domain/session model.

## 6. Configuration And Environment

Runtime configuration belongs in `src/core/config.py` on `Settings`.

Current important settings:

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
- `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_TRACING_V2`, `LANGCHAIN_ENDPOINT`

Rules:

- Add new runtime knobs to `Settings`, `.env.example`, and deployment docs/config.
- Do not hardcode host, port, API keys, model names, collection names, or timeout
  values inside business logic.
- `.env` is local/runtime-only and must not be baked into Docker images.
- `.dockerignore` should continue excluding `.env`.
- Note current naming drift: `src/core/config.py` uses `LANGCHAIN_*`, while
  `.env.example` may still contain `LANGSMITH_*`. Verify tracing env names before
  changing LangSmith behavior.

## 7. Qdrant And Retrieval Rules

Active retrieval code lives in `src/application/graph/nodes/qdrant_search.py`
and `src/infrastructure/qdrant_repo.py`.

Rules:

- Preserve payload metadata from Qdrant. Downstream planner/validator logic
  depends on fields such as `poi_id`, `poi_name`, coordinates, cost, category,
  tags, and intensity.
- Avoid empty filters that zero out retrieval results.
- Do not use REST custom itinerary to fetch/replace backend-selected POIs.
  REST custom itinerary gets its POIs from `selectedPois`; WebSocket planning
  uses Qdrant.
- Treat `src/application/graph/nodes/planner.py` and `reflection.py` as legacy
  references unless current pipeline edges prove otherwise.

## 8. LLM, Prompt Safety, And Realtime Enrichment

- User messages must stay within Gia Lai travel scope.
- Guard against prompt injection, role/system prompt override attempts,
  unrelated prompts, and requests for hidden instructions.
- Do not expose system prompts, secrets, environment values, or internal traces.
- Tavily realtime search is optional and must degrade gracefully.
- Tavily timeouts/retries are controlled by `TAVILY_TIMEOUT_SECONDS` and
  `TAVILY_MAX_RETRIES`.
- Event/detail answers should be concise and summary-oriented when used in chat.
- Route ordering belongs to route optimization logic, not to ad hoc LLM-only
  assumptions.

## 9. Dependency Injection And Layer Boundaries

- Dependency providers live in `src/presentation/dependencies.py`.
- Routers should receive services through `Depends(...)`.
- Application services should not import FastAPI request/response objects.
- Domain models should not import infrastructure, FastAPI, LangChain, or Qdrant.
- Infrastructure should implement repository/external-service details and map
  raw data into domain/application-friendly structures.
- Presentation schemas are API contracts; keep them separate from domain models
  unless the domain model is intentionally part of the contract.

## 10. Commands And Verification

Use PowerShell-friendly commands from the repository root.

Install/sync dependencies:

```powershell
uv sync
```

Run the API locally:

```powershell
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Run tests:

```powershell
uv run pytest
```

Fallback on this Windows checkout if `uv run pytest` hits cache/profile issues:

```powershell
.venv\Scripts\python.exe -m pytest
```

Run focused tests for itinerary/guardrail/route behavior:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_guardrails_and_route_optimizer.py
```

Run lint if available:

```powershell
uv run ruff check src tests
```

Compile-check Python when a narrow syntax check is enough:

```powershell
.venv\Scripts\python.exe -m compileall src tests
```

Before reporting completion:

- State exactly which commands passed.
- If a command was not run, say why.
- Separate failures caused by touched files from unrelated existing repo debt.

## 11. Task Routing Guide

- Change REST itinerary contract:
  - `src/presentation/schemas_itinerary.py`
  - `src/presentation/api/itineraries.py`
  - `src/application/services/itinerary_service.py`
  - tests in `tests/test_guardrails_and_route_optimizer.py`

- Change WebSocket behavior:
  - `src/presentation/ws/chat.py`
  - `src/presentation/schemas_ws.py`
  - `src/application/graph/pipeline.py`
  - relevant node in `src/application/graph/nodes/`
  - `src/domain/working_memory.py` if session state changes

- Change graph planning:
  - `src/application/graph/pipeline.py`
  - `src/application/graph/state.py`
  - `src/application/graph/nodes/qdrant_search.py`
  - `src/application/graph/nodes/route_optimizer.py`
  - `src/application/graph/nodes/llm_planner.py`

- Change route distance/ordering:
  - `src/application/graph/nodes/route_optimizer.py`
  - `src/application/services/distance.py`
  - tests in `tests/test_guardrails_and_route_optimizer.py`

- Change realtime/event behavior:
  - `src/application/graph/nodes/critic.py`
  - `src/application/services/realtime_search.py`
  - `src/core/config.py` for env knobs

- Change Qdrant retrieval:
  - `src/application/graph/nodes/qdrant_search.py`
  - `src/infrastructure/qdrant_repo.py`
  - `src/core/config.py` for collection/model/env knobs

- Change app startup/deployment:
  - `src/main.py`
  - `src/core/config.py`
  - `Dockerfile`
  - `.env.example`
  - `.github/workflows/ci-cd.yml`

## 12. Documentation Rules

- Keep docs short, source-backed, and integration-oriented.
- Put team-shareable Markdown docs under `docs/`.
- If code and docs disagree, update docs or call out the drift.
- Do not document imagined endpoints. Search the source first.
- When documenting mobile/frontend/backend integration, include the real REST and
  WebSocket contracts and the envelope/message types.
- `README.md` is currently not a reliable onboarding source; use this file and
  source inspection first.

## 13. Red Flags For Agents

Stop and inspect more carefully when you see:

- A request to "replace WebSocket with SSE" while source still exposes `/ws/chat`.
- Docs mentioning endpoints that `rg` cannot find in source.
- A REST custom itinerary change that tries to query Qdrant or invent locations.
- Empty Qdrant filters or metadata missing `poi_id`.
- LLM output accepted without validating selected POI IDs.
- New env vars used in code but missing from `Settings` or `.env.example`.
- `print()` or standard `logging` added instead of Loguru.
- Broad refactors mixed into a bug fix.
- Changes to `.env` or secrets.

## 14. Final Response Expectations

When finishing work in this repo:

- Summarize files changed and behavior changed.
- Mention tests/commands run.
- Mention any existing unrelated dirty files only if they affect the task.
- Be clear about uncertainty. If something was inferred from memory or old docs,
  say it may be stale and prefer source verification.
