# Guidelines for AI Agents (AGENTS.md)

> [!IMPORTANT]
> **CORE RULES:**
> 1. **READ FIRST:** Every AI Agent joining the project MUST read this entire document before analyzing or writing any code.
> 2. **ALWAYS UPDATE:** If you introduce a new library, a new coding standard (e.g., a shared schema), or change the architecture, you MUST automatically update this `AGENTS.md` file to reflect the change. This file must always serve as the latest "Source of Truth" for the entire project.

This document is specifically designed for AI coding agents to help them clearly understand the context, architecture, and development rules of the `gialaitravel-ai-service-v2` project.

## 1. Project Overview
- **Project Name:** Gia Lai Travel AI Service V2
- **Purpose:** AI backend service for a travel system.
- **Tech Stack:**
  - Language: Python 3.11+
  - Web Framework: FastAPI
  - Data Validation: Pydantic V2
  - Package Manager: `uv` (uses `pyproject.toml` per PEP 621)
  - AI Framework: LangChain & LangGraph
  - Vector Database: Qdrant

## 2. Project Architecture (Clean Architecture)
The project strictly follows the **Clean Architecture** pattern. Absolutely do not mix processing logic across layers. The source code is divided into 4 main layers, located in the `src/` directory:

```text
src/
├── core/           # General configurations (config.py, logging.py)
├── domain/         # [Layer 1] Core Entities (dataclasses/Pydantic, working_memory.py, itinerary.py). 
│                   # -> MUST NOT depend on any framework or database.
├── application/    # [Layer 2] Business Logic (Use Cases), LangGraph Nodes, Pipeline, and Interfaces.
│                   # -> Contains the AI Pipeline Graph (router, cold_start, elicit, plan, refine, finalize).
├── infrastructure/ # [Layer 3] Database connections, ORM Models, Qdrant Repository, Session Store.
└── presentation/   # [Layer 4] API Routers, WebSocket endpoint (`ws/chat.py`), Pydantic Schemas.
```

## 3. Coding Conventions

### 3.1. API Request & Response
- **Response Standard:** ALL API responses must be wrapped in the `BaseResponse` or `ErrorResponse` classes defined in `src/presentation/schemas.py`. 
- **Example:** If a route returns a list of `ItemResponse`, the type hint in the router must be `response_model=BaseResponse[List[ItemResponse]]`.
- Request/Response schemas should be placed in the respective module's `schemas.py` file.

### 3.2. Dependency Injection
- Services (Use Cases) and repositories must be instantiated and injected via the `src/presentation/dependencies.py` file.
- API Routers get instances using `Depends(get_some_service)`.

### 3.3. Database & ORM
- Database models (SQLAlchemy) are located in `src/infrastructure/models.py`.
- Keep a clear separation between Domain Entities (`src/domain/entities.py`) and Database Models (`src/infrastructure/models.py`). 
- The Repository's role is to map data from DB Models to Domain Entities before returning them to the Use Case.

### 3.4. Dependency Management
- Use `uv` instead of `pip`.
- To add a new library, preferably use the command: `uv add <package_name>`
- The file containing the standard list of libraries for the entire system is `pyproject.toml`.

## 4. Navigation Guide (How to find files quickly)
- Need to modify an API endpoint? Go to `src/presentation/api/` (REST) or `src/presentation/ws/` (WebSocket)
- Need to add calculation or business logic? Go to `src/application/` (services or graph nodes)
- Need to query the Database (e.g., add a new filter)?
  1. Add the definition in `src/application/interfaces.py`.
  2. Implement the actual query in `src/infrastructure/repositories.py` or `qdrant_repo.py`.
- Need to change the Response Schema returned to the client? Go to `src/presentation/schemas_ws.py`
- Need to configure environment variables? Go to `src/core/config.py` and `.env`

## 5. AI Service Pipeline & Conventions
- **WebSocket Protocol:** The service communicates with the frontend/backend via WebSocket at `/ws/chat`. It expects JSON input and streams back intermediate states and itineraries.
- **LangGraph Workflow:** The logic is handled by a LangGraph StateGraph (in `src/application/graph/pipeline.py`) consisting of 4 main phases: `cold_start`, `elicitation`, `planner`, and `reflection`. The planner path is `qdrant_search -> route_optimizer -> llm_planner`; do not reintroduce budget-based validator filtering. Estimated cost should be surfaced to the UI, while route ordering is optimized by coordinates using haversine/road-distance estimates with optional Google Maps Distance Matrix fallback.
- **Realtime enrichment:** Critic/refinement can answer Gia Lai POI detail and upcoming-event questions without regenerating the itinerary. Use `TAVILY_API_KEY` for Tavily realtime lookup when available. Tavily calls must tolerate slow TLS/network handshakes with `TAVILY_TIMEOUT_SECONDS` and `TAVILY_MAX_RETRIES`, then degrade gracefully to an empty event result.
- **Prompt safety:** User messages must stay within Gia Lai travel scope. Guard against prompt-injection attempts, role/system prompt override requests, and unrelated prompts before invoking the graph.
- **Observability:** We use **LangSmith** to trace the LLM execution pipeline.
- **Logging:** We use **Loguru** for structured logging instead of standard `print` or `logging`. Please import `logger` from `loguru`.

## 6. Deployment & CI/CD
- **Dockerization:** We use a `uv`-based slim Dockerfile (`Dockerfile`) that leverages cache mounts to build fast and lightweight Docker images. It runs with the virtual environment activated on the PATH and exposes port 8000.
- **CI/CD Pipeline:** GitHub Actions (`.github/workflows/ci-cd.yml`) automates checks on every push and pull request to `main`, `master`, and `develop`. It runs lint checking using Ruff, unit testing via pytest, and builds/pushes the Docker image to GitHub Container Registry (GHCR) on pushes to `main` or `master`.

---
**Note for AI Agents:** By maintaining this structure, the source code will be highly testable (via mocking repository interfaces) and easy to maintain. Ensure that any code changes or additions respect this separation of concerns.

