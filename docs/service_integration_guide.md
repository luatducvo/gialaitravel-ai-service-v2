# Gia Lai Travel AI Service V2 - Integration Guide

Tai lieu nay tong hop thong tin can thiet de team backend va frontend tich hop voi AI service lap lich trinh du lich Gia Lai.

## 1. Tong quan service

- Ten service: `gialaitravel-ai-service-v2`
- Vai tro: AI backend service tao lich trinh du lich Gia Lai, goi y POI, toi uu thu tu di chuyen, tinh chi phi/km uoc tinh va ho tro hoi dap/refine sau khi co lich trinh.
- Framework: FastAPI
- Python: 3.11+
- Package manager: `uv`
- Data validation: Pydantic V2
- AI orchestration: LangChain, LangGraph
- Vector database: Qdrant
- Observability: LangSmith
- Logging: Loguru

## 2. Kien truc tong the

Service di theo Clean Architecture:

```text
src/
+-- core/           # Config va logging
+-- domain/         # Entity/model nghiep vu, khong phu thuoc framework/db
+-- application/    # Use case, LangGraph pipeline, services, interfaces
+-- infrastructure/ # Qdrant, session store, database/repository
+-- presentation/   # FastAPI router, WebSocket, request/response schemas
```

Quy uoc quan trong:

- API response REST phai boc trong `BaseResponse` hoac `ErrorResponse`.
- Service/repository duoc inject qua `src/presentation/dependencies.py`.
- Domain entity va database model tach rieng.
- Them thu vien bang `uv add <package_name>`.
- Log bang `logger` tu `loguru`, khong dung `print`.

## 3. Cach chay local

```bash
uv sync
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Entry point FastAPI: `src/main.py`

Base URL local:

```text
http://localhost:8000
```

FastAPI docs:

```text
http://localhost:8000/docs
```

## 4. Cau hinh moi truong

File cau hinh: `.env`

Bien moi truong chinh:

| Bien | Bat buoc | Mo ta |
| --- | --- | --- |
| `PROJECT_NAME` | Khong | Ten service |
| `LLM_PROVIDER` | Co | Provider LLM: `openai`, `gemini`, hoac `deepseek` |
| `OPENAI_API_KEY` | Tuy provider | API key OpenAI |
| `GEMINI_API_KEY` | Tuy provider | API key Gemini |
| `DEEPSEEK_API_KEY` | Tuy provider | API key DeepSeek |
| `OPENAI_MODEL` | Tuy provider | Model OpenAI |
| `GEMINI_MODEL` | Tuy provider | Model Gemini |
| `DEEPSEEK_MODEL` | Tuy provider | Model DeepSeek |
| `QDRANT_URL` | Co | URL Qdrant local/cloud |
| `QDRANT_API_KEY` | Co | API key Qdrant |
| `QDRANT_COLLECTION_NAME` | Co | Collection POI, mac dinh `gialai-data` |
| `EMBEDDING_MODEL` | Khong | Model embedding, mac dinh `models/gemini-embedding-2` |
| `TAVILY_API_KEY` | Khong | Dung cho realtime lookup su kien/chi tiet POI |
| `TAVILY_TIMEOUT_SECONDS` | Khong | Timeout Tavily, mac dinh `15` |
| `TAVILY_MAX_RETRIES` | Khong | So lan retry Tavily, mac dinh `2` |
| `GOOGLE_MAPS_API_KEY` | Khong | Distance Matrix fallback khi tinh khoang cach |
| `LANGCHAIN_API_KEY` | Khong | LangSmith/LangChain tracing |
| `LANGCHAIN_PROJECT` | Khong | Ten project LangSmith |
| `LANGCHAIN_TRACING_V2` | Khong | Bat/tat tracing |
| `LANGCHAIN_ENDPOINT` | Khong | Endpoint LangSmith |

Luu y: `src/core/config.py` dang doc nhom bien `LANGCHAIN_*`. Neu dung `.env.example`, nen dong bo ten bien LangSmith tu `LANGSMITH_*` sang `LANGCHAIN_*` de tracing hoat dong dung.

## 5. REST API

### 5.1. Tao lich trinh tu danh sach POI frontend chon

```http
POST /api/v1/itineraries/custom
```

Muc dich:

- Frontend/gui backend gui danh sach POI da chon.
- Service toi uu thu tu tham quan bang nearest-neighbor.
- Neu co `GOOGLE_MAPS_API_KEY`, service co the dung Google Distance Matrix lam fallback tinh khoang cach.
- Goi LLM sinh lich trinh chi tiet.

Request body:

```json
{
  "pois": [
    {
      "poi_id": "poi_001",
      "poi_name": "Bien Ho Pleiku",
      "lat": 14.053,
      "lng": 108.017,
      "description": "Ho nuoc dep gan Pleiku",
      "category": "attraction",
      "estimated_cost": 50000,
      "duration_minutes": 90,
      "intensity_level": "low",
      "image_url": "https://example.com/bien-ho.jpg"
    }
  ],
  "duration": "1 ngay",
  "group": "family",
  "transport": "car",
  "note": "Di nhe nhang, uu tien canh dep va an uong dia phuong",
  "start_location": null,
  "optimize_route": true
}
```

Field request:

| Field | Type | Bat buoc | Ghi chu |
| --- | --- | --- | --- |
| `pois` | `PoiInput[]` | Co | 1-20 POI, `poi_id` khong duoc trung |
| `duration` | `string` | Co | Vi du `1 ngay`, `2 ngay 1 dem` |
| `group` | `solo`, `couple`, `family`, `friends`, `elderly` | Co | Loai nhom |
| `transport` | `motorbike`, `car`, `bus` | Co | Phuong tien |
| `note` | `string` | Khong | Gu/ghi chu them cua user |
| `start_location` | `PoiInput` | Khong | Diem xuat phat, vi du khach san |
| `optimize_route` | `boolean` | Khong | Mac dinh `true` |

Field `PoiInput`:

| Field | Type | Bat buoc | Ghi chu |
| --- | --- | --- | --- |
| `poi_id` | `string` | Co | ID POI |
| `poi_name` | `string` | Co | Ten hien thi |
| `lat` | `number` | Co | Latitude trong vung Gia Lai: `13.0` den `15.0` |
| `lng` | `number` | Co | Longitude trong vung Gia Lai: `107.0` den `109.5` |
| `description` | `string` | Khong | Toi da 500 ky tu |
| `category` | `string` | Khong | Vi du `restaurant`, `attraction`, `hotel`, `cafe` |
| `estimated_cost` | `number` | Khong | VND, mac dinh `0` |
| `duration_minutes` | `integer` | Khong | 10-480 phut, mac dinh `60` |
| `intensity_level` | `low`, `medium`, `high` | Khong | Mac dinh `medium` |
| `image_url` | `string` | Khong | Anh dai dien |

Response thanh cong:

```json
{
  "status_code": 200,
  "message": "Lich trinh da duoc tao thanh cong",
  "data": {
    "itinerary": {
      "days": [
        {
          "day": 1,
          "title": "Kham pha Pleiku",
          "total_km": 18.5,
          "activities": [
            {
              "time_slot": "08:00 - 09:30",
              "poi_id": "poi_001",
              "poi_name": "Bien Ho Pleiku",
              "lat": 14.053,
              "lng": 108.017,
              "duration_minutes": 90,
              "cost": 50000,
              "distance_from_prev_km": 0,
              "intensity_level": "low",
              "note": "Nen di buoi sang de chup anh dep."
            }
          ]
        }
      ],
      "total_cost": 50000,
      "total_km": 18.5
    },
    "route_summary": {
      "estimated_cost": 50000,
      "estimated_km": 18.5,
      "optimizer": "nearest_neighbor_haversine_with_google_maps_fallback",
      "total_pois": 1
    },
    "optimized_poi_order": ["poi_001"]
  }
}
```

Loi:

```json
{
  "status_code": 500,
  "message": "Khong the tao lich trinh",
  "details": "..."
}
```

## 6. WebSocket API

### 6.1. Endpoint

```text
ws://localhost:8000/ws/chat?session_id=<session_id>
```

`session_id` la query parameter bat buoc. Service dung `session_id` de lay/luu working memory trong in-memory session store.

Luu y production: session hien tai luu in-memory tai `src/infrastructure/session_store.py`. Khi deploy nhieu instance hoac can persist, nen thay bang Redis/shared store.

### 6.2. Client message format

Frontend gui text frame la JSON:

```json
{
  "type": "user_message",
  "session_id": "session_123",
  "payload": {
    "message": "Toi muon di 2 ngay 1 dem o Gia Lai",
    "chip_value": null
  }
}
```

Quy tac lay message:

- Service uu tien `payload.chip_value`.
- Neu khong co `chip_value`, service dung `payload.message`.

Co the gui form cold-start bang payload:

```json
{
  "type": "user_message",
  "session_id": "session_123",
  "payload": {
    "trip": {
      "duration": "2 ngay 1 dem",
      "group": "family",
      "transport": "car"
    }
  }
}
```

Alias payload cold-start service dang ho tro:

- Trip object: `trip`, `chuyen_di`
- Duration: `duration`, `trip_duration`, `chuyen_di`
- Group: `group`, `companion`, `nhom_dong_hanh`
- Transport: `transport`, `vehicle`, `phuong_tien`

Gia tri canonical:

- `group`: `solo`, `couple`, `group`, `family`
- `transport`: `motorbike`, `car`

### 6.3. Server message types

Khi frontend ket noi session moi, neu memory chua co `duration` va dang o `cold_start`, service tu dong trigger pipeline va gui form dau tien.

#### `cold_start_form`

Server yeu cau user cung cap thoi luong, nhom dong hanh va phuong tien.

```json
{
  "type": "cold_start_form",
  "step": "cold_start",
  "agent_message": "Xin chao! De goi y lich trinh Gia Lai phu hop, minh can biet thoi luong, nhom dong hanh va phuong tien."
}
```

Frontend nen render form gom:

- Thoi luong chuyen di.
- Nhom dong hanh.
- Phuong tien.

#### `elicitation_question`

Server hoi them gu/vibe du lich cua user.

```json
{
  "type": "elicitation_question",
  "step": "elicit",
  "agent_message": "Mot cau cuoi de minh hieu gu cua ban...",
  "ui_chips": [
    {
      "label": "Thien nhien, thac nuoc, trekking nhe",
      "value": "Minh muon mot lich trinh thien nhien, co thac nuoc, rung va trekking nhe."
    }
  ],
  "allow_free_text": true
}
```

Frontend nen render chip va input free text neu `allow_free_text=true`.

#### `itinerary`

Server tra lich trinh da sinh.

```json
{
  "type": "itinerary",
  "step": "plan",
  "agent_message": "Day la lich trinh minh da thiet ke cho ban.",
  "itinerary": {
    "days": [],
    "total_cost": 0,
    "total_km": 0
  },
  "route_summary": {
    "estimated_cost": 0,
    "estimated_km": 0,
    "optimizer": "nearest_neighbor_haversine_with_google_maps_fallback"
  },
  "ui_chips": [
    {
      "label": "Hai long, xac nhan lich trinh",
      "value": "confirm"
    },
    {
      "label": "Can dieu chinh",
      "value": "refine"
    }
  ]
}
```

Sau message nay, memory chuyen sang step `refine`.

#### `refinement_options`

Server hoi user muon dieu chinh phan nao.

```json
{
  "type": "refinement_options",
  "step": "refine",
  "agent_message": "Ban muon dieu chinh phan nao cua lich trinh?",
  "ui_chips": [
    {
      "label": "Thay doi diem den",
      "value": "change_poi"
    },
    {
      "label": "Giam thoi gian di chuyen",
      "value": "reduce_travel"
    },
    {
      "label": "Khac",
      "value": "custom"
    }
  ]
}
```

Neu user gui feedback tu do, service luu constraint va lap lai planner flow.

#### `poi_detail`

Server tra them thong tin realtime ve POI khi user hoi chi tiet, vi du gio mo cua, dia diem, thong tin them.

```json
{
  "type": "poi_detail",
  "step": "refine",
  "agent_message": "Minh tong hop them thong tin ve dia diem ban hoi.",
  "poi": {
    "poi_id": "poi_001",
    "poi_name": "Bien Ho Pleiku"
  },
  "results": [
    {
      "title": "Nguon thong tin",
      "url": "https://example.com",
      "content": "Tom tat thong tin",
      "score": 0.91
    }
  ]
}
```

Message nay dung Tavily neu co `TAVILY_API_KEY`. Neu Tavily cham/loi, service degrade graceful.

#### `realtime_info`

Server tra thong tin su kien/le hoi sap toi lien quan Gia Lai.

```json
{
  "type": "realtime_info",
  "step": "refine",
  "agent_message": "Cac su kien chinh sap toi o Gia Lai:",
  "results": [
    {
      "title": "Ten su kien",
      "description": "Tom tat ngan"
    }
  ]
}
```

#### `guardrail`

Server chan message ngoai pham vi du lich Gia Lai hoac prompt injection.

```json
{
  "type": "guardrail",
  "step": "refine",
  "agent_message": "Minh chi ho tro lap lich trinh, hoi dap dia diem va su kien lien quan den du lich Gia Lai...",
  "reason": "prompt_injection"
}
```

`reason` co the la:

- `prompt_injection`
- `out_of_scope`

#### `finalized`

Server xac nhan lich trinh cuoi cung.

```json
{
  "type": "finalized",
  "step": "finalized",
  "agent_message": "Lich trinh da duoc xac nhan! Chuc ban co chuyen di tuyet voi o Gia Lai!",
  "itinerary": {
    "days": [],
    "total_cost": 0,
    "total_km": 0
  }
}
```

## 7. Luong WebSocket khuyen nghi cho frontend

1. Tao `session_id` duy nhat cho moi conversation.
2. Ket noi `ws://localhost:8000/ws/chat?session_id=<session_id>`.
3. Nhan `cold_start_form`, render form thong tin co ban.
4. Gui payload `trip.duration`, `trip.group`, `trip.transport`.
5. Nhan `elicitation_question`, render chips/free text.
6. Gui `chip_value` hoac `message` ve vibe du lich.
7. Nhan `itinerary`, render lich trinh, tong chi phi, tong km, route summary.
8. Neu user hai long, gui `chip_value: "confirm"`.
9. Neu user muon sua, gui `chip_value: "refine"` hoac feedback tu nhien.
10. Sau `finalized`, khoa flow hoac cho user bat dau session moi.

Vi du gui chip:

```json
{
  "type": "user_message",
  "session_id": "session_123",
  "payload": {
    "message": "",
    "chip_value": "confirm"
  }
}
```

## 8. Data model itinerary

Model itinerary chuan:

```json
{
  "days": [
    {
      "day": 1,
      "title": "Tieu de ngay",
      "total_km": 25.4,
      "activities": [
        {
          "time_slot": "08:00 - 09:30",
          "poi_id": "poi_001",
          "poi_name": "Ten dia diem",
          "lat": 14.0,
          "lng": 108.0,
          "duration_minutes": 90,
          "cost": 50000,
          "distance_from_prev_km": 3.2,
          "intensity_level": "low",
          "note": "Ghi chu cho user"
        }
      ]
    }
  ],
  "total_cost": 250000,
  "total_km": 42.8
}
```

## 9. AI pipeline

LangGraph workflow:

```text
router
+-- cold_start
|   +-- elicit
|       +-- qdrant_search
|           +-- route_optimizer
|               +-- llm_planner
+-- refine
|   +-- critic
|       +-- finalized
|       +-- qdrant_search -> route_optimizer -> llm_planner
+-- finalized
```

Chi tiet:

- `cold_start`: thu thap `duration`, `group`, `transport`.
- `elicitation`: thu thap `vibe_query`.
- `qdrant_search`: search Qdrant theo `vibe_poi` va `logistics_poi`, filter theo intensity, transport, group.
- `route_optimizer`: sap xep POI bang nearest-neighbor; tinh cost/km; Google Distance Matrix la fallback neu co key.
- `llm_planner`: sinh itinerary structured theo model `Itinerary`.
- `critic`: xu ly confirm/refine, hoi chi tiet POI, hoi su kien realtime.
- `finalize`: tra lich trinh da xac nhan.

## 10. Guardrails va pham vi ho tro

Service chi ho tro:

- Lap lich trinh du lich Gia Lai.
- Hoi dap dia diem trong lich trinh.
- Hoi dap su kien/le hoi lien quan Gia Lai.
- Refine lich trinh da tao.

Service se chan:

- Prompt injection, vi du yeu cau bo qua system/developer prompt.
- Cau hoi ngoai pham vi du lich Gia Lai.
- Yeu cau lap trinh/code hoac noi dung khong lien quan neu khong co ngu canh du lich Gia Lai.

## 11. Luu y cho backend tich hop

- REST endpoint hien co chi include router `itineraries`; router `items` chua duoc include trong `src/main.py`.
- Tat ca REST response nen giu wrapper `BaseResponse`/`ErrorResponse`.
- Neu backend gateway proxy WebSocket, can forward query `session_id`.
- Nen tao `session_id` on backend neu frontend khong tu quan ly duoc.
- Session store hien tai la in-memory, restart service se mat session.
- Deploy multi-instance can Redis/sticky session.
- Qdrant metadata can co cac key quan trong: `poi_id`, `poi_name`, `lat`/`latitude`, `lng`/`longitude`, `cost`/`estimated_cost`, `intensity_level`, `transport_compatibility`, `suitable_for`, `aspect`.

## 12. Luu y cho frontend tich hop

- Luon xu ly response theo `type`.
- WebSocket co the tra nhieu message lien tiep cho mot request.
- `agent_message` la text hien thi cho user.
- `ui_chips` la danh sach quick actions; khi user bam chip, gui `payload.chip_value`.
- Khi `allow_free_text=true`, hien input de user tu nhap.
- Render `route_summary.estimated_cost` va `route_summary.estimated_km` nhu thong tin uoc tinh, khong phai gia cam ket.
- Sau khi nhan `itinerary`, nen cho user 2 hanh dong chinh: confirm hoac refine.
- Khi nhan `guardrail`, giu session va cho user gui lai message hop le.

## 13. Checklist test nhanh

### WebSocket

- Ket noi session moi nhan duoc `cold_start_form`.
- Gui `trip.duration/group/transport` nhan duoc `elicitation_question`.
- Gui vibe nhan duoc `itinerary`.
- Gui `confirm` nhan duoc `finalized`.
- Gui `refine` nhan duoc `refinement_options`.
- Gui cau hoi su kien Gia Lai nhan duoc `realtime_info`.
- Gui prompt injection nhan duoc `guardrail`.

### REST

- `POST /api/v1/itineraries/custom` voi 1-20 POI hop le tra `BaseResponse`.
- Lat/lng ngoai vung Gia Lai bi validation error `422`.
- `poi_id` trung bi validation error.
- `optimize_route=false` giu thu tu POI user gui.

## 14. Files tham chieu trong code

- FastAPI app: `src/main.py`
- WebSocket endpoint: `src/presentation/ws/chat.py`
- WebSocket input schema: `src/presentation/schemas_ws.py`
- REST itinerary router: `src/presentation/api/itineraries.py`
- REST itinerary schema: `src/presentation/schemas_itinerary.py`
- Response wrapper: `src/presentation/schemas.py`
- Graph pipeline: `src/application/graph/pipeline.py`
- Cold start node: `src/application/graph/nodes/cold_start.py`
- Elicitation node: `src/application/graph/nodes/elicitation.py`
- Qdrant search node: `src/application/graph/nodes/qdrant_search.py`
- Route optimizer: `src/application/graph/nodes/route_optimizer.py`
- LLM planner: `src/application/graph/nodes/llm_planner.py`
- Critic/refine node: `src/application/graph/nodes/critic.py`
- Finalize node: `src/application/graph/nodes/finalize.py`
- Working memory: `src/domain/working_memory.py`
- Itinerary domain model: `src/domain/itinerary.py`
- Config: `src/core/config.py`
