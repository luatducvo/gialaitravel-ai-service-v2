# Gia Lai Travel REST API Contract for Backend Team

Version: 1.0  
Audience: NestJS Backend team  
Service boundary: Frontend -> NestJS Backend -> FastAPI Agent Service

---

## 1. Architecture Boundary

```text
Frontend
   |
   v
NestJS Backend
   |-- PostgreSQL: users, locations, trips, days, stops, agent runs
   |-- Public REST API for frontend
   |
   v
FastAPI Agent Service
   |-- Internal REST API only
   |-- Route optimization
   |-- LLM itinerary generation
```

Backend responsibilities:

- Authenticate user.
- Validate request payloads.
- Load and validate `Location` records from PostgreSQL.
- Build POI snapshots for Agent Service.
- Persist `Trip`, `TripDay`, `TripStop`, and `AgentRun`.

Agent Service responsibilities:

- Receive backend-validated POI snapshots.
- Optionally optimize POI order.
- Generate itinerary JSON using LLM.
- Return itinerary, route summary, and optimized POI order.

Agent Service must not:

- Query PostgreSQL.
- Query Qdrant for this REST flow.
- Resolve location names by itself.
- Add, replace, or invent user-selected locations.
- Persist trip data.

---

## 2. Public Backend API

### Generate Itinerary

```http
POST /trips/generate
```

Creates a new trip from user preferences and selected locations.

#### Request Body

```json
{
  "name": "Gia Lai 2 ngày 1 đêm",
  "startDate": "2026-07-10",
  "endDate": "2026-07-11",
  "startTime": "08:00",
  "endTime": "18:00",
  "groupType": "friends",
  "travelPace": "balanced",
  "budgetLevel": "mid_range",
  "transportType": "MOTORBIKE",
  "interests": ["nature", "coffee", "culture"],
  "selectedLocationIds": [
    "loc_bien_ho",
    "loc_minh_thanh_pagoda",
    "loc_chu_dang_ya"
  ],
  "optimizeRoute": true,
  "note": "Ưu tiên cảnh đẹp và quán cà phê."
}
```

#### Request Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | yes | Trip display name. |
| `startDate` | ISO date | no | Example: `2026-07-10`. |
| `endDate` | ISO date | no | Must be after or equal to `startDate` when provided. |
| `startTime` | string | no | `HH:mm`, default can be `08:00`. |
| `endTime` | string | no | `HH:mm`, default can be `18:00`. |
| `groupType` | string | yes | `solo`, `couple`, `family`, `friends`, `elderly`. |
| `travelPace` | string | yes | `slow`, `balanced`, `fast`. |
| `budgetLevel` | string | yes | `budget`, `mid_range`, `premium`. |
| `transportType` | string | yes | Public API may use `MOTORBIKE`, `CAR`, `BUS`; map to Agent values below. |
| `interests` | string[] | no | Used by backend for scoring or preferences. |
| `selectedLocationIds` | string[] | yes | 1-20 active Gia Lai locations, no duplicates. |
| `optimizeRoute` | boolean | no | Default `true`. |
| `note` | string | no | User preference text. |

#### Backend Validation

- `selectedLocationIds` must contain 1-20 unique IDs.
- Every selected location must exist, be active, and belong to Gia Lai.
- Each selected location sent to Agent must have valid coordinates:
  - `lat`: `13.0 <= lat <= 15.0`
  - `lng`: `107.0 <= lng <= 109.5`
- Backend should reject invalid selected locations instead of asking Agent to recover.

#### Success Response

```json
{
  "statusCode": 201,
  "message": "Itinerary generated successfully",
  "data": {
    "tripId": "trip_123",
    "status": "SUCCESS",
    "overview": "Lịch trình khám phá Gia Lai trong 2 ngày 1 đêm.",
    "itinerary": {
      "days": [
        {
          "day": 1,
          "title": "Pleiku và vùng lân cận",
          "totalKm": 42.5,
          "activities": [
            {
              "timeSlot": "08:00 - 09:30",
              "locationId": "loc_bien_ho",
              "poiName": "Biển Hồ",
              "lat": 13.997,
              "lng": 108.006,
              "durationMinutes": 90,
              "estimatedCost": 0,
              "distanceFromPrevKm": 0,
              "intensityLevel": "low",
              "note": "Tham quan và chụp ảnh buổi sáng."
            }
          ]
        }
      ],
      "totalCost": 250000,
      "totalKm": 86.2
    },
    "routeSummary": {
      "estimatedKm": 86.2,
      "optimizer": "nearest_neighbor",
      "distanceSource": "haversine_road_estimate",
      "totalPois": 3
    },
    "optimizedLocationOrder": [
      {
        "locationId": "loc_bien_ho",
        "name": "Biển Hồ",
        "lat": 13.997,
        "lng": 108.006,
        "routeOrder": 1,
        "distanceFromPrevKm": 0
      }
    ]
  }
}
```

#### Error Responses

```json
{
  "statusCode": 400,
  "message": "Invalid selected locations",
  "details": {
    "selectedLocationIds": ["Duplicate location IDs are not allowed"]
  }
}
```

```json
{
  "statusCode": 500,
  "message": "Could not generate itinerary",
  "details": {
    "tripId": "trip_123",
    "agentRunId": "agent_run_123"
  }
}
```

---

## 3. Internal Agent API

### Create Custom Itinerary From Selected POIs

```http
POST /api/v1/itineraries/custom
```

This endpoint is called by NestJS Backend only.

#### Request Body

```json
{
  "duration": "2 ngày 1 đêm",
  "group": "friends",
  "transport": "motorbike",
  "travelPace": "balanced",
  "budgetLevel": "mid_range",
  "vibe": "Ưu tiên thiên nhiên, cà phê và văn hóa",
  "constraints": ["Chỉ dùng các địa điểm trong selectedPois"],
  "optimizeRoute": true,
  "selectedPois": [
    {
      "poiId": "loc_bien_ho",
      "poiName": "Biển Hồ",
      "description": "Hồ nước nổi tiếng gần Pleiku",
      "lat": 13.997,
      "lng": 108.006,
      "category": "attraction",
      "tags": ["nature", "sightseeing"],
      "estimatedCost": 0,
      "durationMinutes": 90,
      "intensityLevel": "low",
      "imageUrl": "https://example.com/bien-ho.jpg"
    }
  ]
}
```

#### Agent Request Fields

| Field | Type | Required | Accepted values |
| --- | --- | --- | --- |
| `duration` | string | yes | Example: `1 ngày`, `2 ngày 1 đêm`, `3 ngày 2 đêm`. |
| `group` | string | no | `solo`, `couple`, `family`, `friends`, `elderly`; default `friends`. |
| `transport` | string | no | `motorbike`, `car`, `bus`; default `motorbike`. |
| `travelPace` | string | no | `slow`, `balanced`, `fast`; default `balanced`. |
| `budgetLevel` | string | no | `budget`, `mid_range`, `premium`; default `mid_range`. |
| `vibe` | string | no | Free text, max 500 characters. |
| `constraints` | string[] | no | Max 20 items. |
| `optimizeRoute` | boolean | no | Default `true`. |
| `selectedPois` | object[] | yes | 1-20 POI snapshots, no duplicate `poiId`. |

#### `selectedPois[]`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `poiId` | string | yes | Use the backend `Location.id`. |
| `poiName` | string | yes | Location display name. |
| `description` | string | no | Max 500 characters. |
| `lat` | number | yes | Must be within Gia Lai bounds. |
| `lng` | number | yes | Must be within Gia Lai bounds. |
| `category` | string | no | Example: `attraction`, `restaurant`, `cafe`, `waterfall`. |
| `tags` | string[] | no | Example: `nature`, `coffee`, `culture`. |
| `estimatedCost` | number | no | VND, default `0`. |
| `durationMinutes` | number | no | 10-480, default `60`. |
| `intensityLevel` | string | no | `low`, `medium`, `high`; default `medium`. |
| `imageUrl` | string | no | Representative image. |

#### Agent Success Response

```json
{
  "status_code": 200,
  "message": "Lich trinh da duoc tao thanh cong",
  "data": {
    "itinerary": {
      "days": [
        {
          "day": 1,
          "title": "Pleiku và vùng lân cận",
          "total_km": 42.5,
          "activities": [
            {
              "time_slot": "08:00 - 09:30",
              "poi_id": "loc_bien_ho",
              "poi_name": "Biển Hồ",
              "lat": 13.997,
              "lng": 108.006,
              "duration_minutes": 90,
              "cost": 0,
              "distance_from_prev_km": 0,
              "intensity_level": "low",
              "note": "Tham quan và chụp ảnh buổi sáng."
            }
          ]
        }
      ],
      "total_cost": 250000,
      "total_km": 86.2
    },
    "route_summary": {
      "estimated_km": 86.2,
      "optimizer": "nearest_neighbor",
      "distance_source": "haversine_road_estimate",
      "total_pois": 3
    },
    "optimized_poi_order": [
      {
        "poi_id": "loc_bien_ho",
        "poi_name": "Biển Hồ",
        "lat": 13.997,
        "lng": 108.006,
        "route_order": 1,
        "distance_from_prev_km": 0
      }
    ]
  }
}
```

#### Agent Validation Error

FastAPI returns HTTP `422` when payload validation fails.

Common validation failures:

- `selectedPois` is empty.
- More than 20 POIs.
- Duplicate `poiId`.
- `lat` outside `13.0-15.0`.
- `lng` outside `107.0-109.5`.
- Invalid enum value for `group`, `transport`, `travelPace`, `budgetLevel`, or `intensityLevel`.

#### Agent Internal Error

```json
{
  "status_code": 500,
  "message": "Khong the tao lich trinh",
  "details": "LLM or route optimizer error message"
}
```

---

## 4. Backend Integration Flow

### Generate Flow

```text
1. Frontend calls POST /trips/generate
2. Backend validates request
3. Backend loads selected Location records
4. Backend creates Trip with status PROCESSING
5. Backend creates AgentRun with status PROCESSING
6. Backend calls Agent POST /api/v1/itineraries/custom
7. Agent returns itinerary JSON
8. Backend persists TripDay and TripStop
9. Backend stores itineraryJson and route summary
10. Backend updates AgentRun SUCCESS
11. Backend updates Trip SUCCESS
12. Backend returns generated trip to frontend
```

### Failure Flow

```text
1. Backend creates Trip PROCESSING
2. Backend creates AgentRun PROCESSING
3. Agent call fails or returns invalid data
4. Backend updates AgentRun FAILED with errorMessage
5. Backend updates Trip FAILED
6. Backend returns 500 with tripId and agentRunId
```

---

## 5. Mapping Rules

### Backend `Location` -> Agent `selectedPois[]`

```ts
{
  poiId: location.id,
  poiName: location.name,
  description: location.description,
  lat: location.latitude,
  lng: location.longitude,
  category: location.category,
  tags: location.tags ?? [],
  estimatedCost: location.minPrice ?? 0,
  durationMinutes: location.estimatedVisitMinutes ?? 60,
  intensityLevel: "medium",
  imageUrl: location.imageUrl
}
```

### Backend public enum -> Agent enum

| Backend value | Agent value |
| --- | --- |
| `MOTORBIKE` | `motorbike` |
| `CAR` | `car` |
| `BUS` | `bus` |
| `UNKNOWN` | `motorbike` |

### Agent response -> Backend persisted data

| Agent field | Backend target |
| --- | --- |
| `itinerary.days[].day` | `TripDay.dayIndex` |
| `itinerary.days[].title` | `TripDay.title` |
| `activities[].poi_id` | `TripStop.locationId` |
| `activities[].poi_name` | `TripStop.title` |
| `activities[].time_slot` | Parse into `TripStop.startTime` and `TripStop.endTime` when possible. |
| `activities[].duration_minutes` | `TripStop.durationMinutes` |
| `activities[].cost` | `TripStop.estimatedCost` |
| `activities[].note` | `TripStop.note` |
| Full Agent response | `Trip.itineraryJson` and `AgentRun.output` |

---

## 6. Replan API

### Public Backend Endpoint

```http
POST /trips/:tripId/replan
```

Suggested request body:

```json
{
  "instruction": "Sắp xếp lịch trình nhẹ hơn cho gia đình có trẻ nhỏ",
  "optimizeRoute": true
}
```

Backend should:

- Load current trip, days, stops, and selected locations.
- Build `selectedPois` from current stops.
- Call Agent with the new `vibe` or `constraints`.
- Replace existing `TripDay` and `TripStop` records inside a transaction.
- Store a new `AgentRun` with type `REPLAN_ITINERARY`.

---

## 7. Acceptance Checklist

- Backend rejects invalid `selectedLocationIds` before calling Agent.
- Backend sends only backend-validated POI snapshots to Agent.
- Agent response contains only POIs from `selectedPois`.
- `optimizeRoute=false` preserves frontend/backend input order.
- `optimizeRoute=true` returns `route_summary.optimizer = "nearest_neighbor"`.
- Failed Agent calls are recorded in `AgentRun`.
- Successful Agent calls persist `TripDay`, `TripStop`, and `Trip.itineraryJson`.
