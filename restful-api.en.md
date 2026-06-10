# Gia Lai AI Itinerary Planner

## Phase 1 MVP Design

Version: 1.0

---

# 1. Project Scope

## Objectives

Build an AI-powered travel itinerary planner system for Gia Lai.

Users can:

* Select travel preferences
* Select favorite locations
* Generate itinerary using AI
* Edit itinerary
* Re-plan itinerary using AI

## Out of Scope for MVP

Do not use:

* Embedding
* Vector Database
* Qdrant
* Semantic Search
* Personalized Recommendation
* Collaborative Filtering
* Google Maps Route Optimization

---

# 2. System Architecture

```text
React + Vite
      |
      v
NestJS Backend
      |
      +------------------+
      |                  |
      v                  v
PostgreSQL         Agent Service
                        |
                        v
                 LangGraph + LLM
```

## Responsibilities

### Frontend

* Collect user preferences
* Display itinerary
* Allow editing the itinerary

### Backend

* Manage data
* Validate requests
* Score locations
* Call Agent
* Save itineraries

### Agent

* Understand user preferences
* Generate itineraries
* Explain recommendations
* Re-plan itineraries

Agent is not allowed to:

* Access database
* Query PostgreSQL
* Query Qdrant or resolve selected locations by itself
* Create new locations on its own
* Add, replace, or invent user-selected locations

---

# 3. Database Design

---

## User

```prisma
model User {
  id          String   @id @default(uuid())
  email       String   @unique
  name        String?

  role        Role     @default(USER)

  trips       Trip[]

  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
}
```

---

## Location

Main location data source.

```prisma
model Location {
  id                    String   @id @default(uuid())

  name                  String

  description           String?

  city                  String

  region                String?

  address               String?

  latitude              Float?
  longitude             Float?

  category              LocationCategory

  tags                  String[]

  amenities             String[]

  openingHours          Json?

  priceRange            PriceRange?
  minPrice              Int?
  maxPrice              Int?
  currency              String   @default("VND")

  rating                Float?

  estimatedVisitMinutes Int?

  imageUrl              String?

  isActive              Boolean  @default(true)

  createdAt             DateTime @default(now())
  updatedAt             DateTime @updatedAt

  tripStops             TripStop[]

  @@index([city])
  @@index([region])
  @@index([category])
}
```

---

## Trip

A travel plan.

```prisma
model Trip {
  id            String   @id @default(uuid())

  userId        String

  name          String

  overview      String?

  status        TripStatus @default(DRAFT)

  startDate     DateTime?
  endDate       DateTime?

  startTime     String?
  endTime       String?

  groupSize     Int?

  transportType TransportType?

  preferences   Json?

  itineraryJson Json?

  user          User @relation(fields: [userId], references: [id])

  days          TripDay[]

  agentRuns     AgentRun[]

  createdAt     DateTime @default(now())
  updatedAt     DateTime @updatedAt

  @@index([userId])
}
```

---

## TripDay

```prisma
model TripDay {
  id         String   @id @default(uuid())

  tripId     String

  dayIndex   Int

  date       DateTime?

  title      String?

  summary    String?

  trip       Trip @relation(fields: [tripId], references: [id])

  stops      TripStop[]

  createdAt  DateTime @default(now())
  updatedAt  DateTime @updatedAt

  @@unique([tripId, dayIndex])
}
```

---

## TripStop

```prisma
model TripStop {
  id                  String @id @default(uuid())

  tripDayId           String

  locationId          String?

  order               Int

  title               String?

  description         String?

  startTime           String?
  endTime             String?

  durationMinutes     Int?

  estimatedCost       Int?

  reason              String?

  note                String?

  tripDay             TripDay @relation(fields: [tripDayId], references: [id])

  location            Location? @relation(fields: [locationId], references: [id])

  createdAt           DateTime @default(now())
  updatedAt           DateTime @updatedAt

  @@unique([tripDayId, order])
}
```

---

## AgentRun

Save Agent run history.

```prisma
model AgentRun {
  id             String @id @default(uuid())

  tripId         String

  userId         String

  type           AgentRunType

  status         AgentRunStatus

  input          Json

  output         Json?

  errorMessage   String?

  modelName      String?

  promptVersion  String?

  trip           Trip @relation(fields: [tripId], references: [id])

  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt
}
```

---

# 4. Enums

```prisma
enum Role {
  USER
  ADMIN
}

enum TripStatus {
  DRAFT
  PROCESSING
  SUCCESS
  FAILED
}

enum AgentRunType {
  GENERATE_ITINERARY
  REPLAN_ITINERARY
  CLARIFY_PREFERENCES
}

enum AgentRunStatus {
  PROCESSING
  SUCCESS
  FAILED
}

enum TransportType {
  MOTORBIKE
  CAR
  UNKNOWN
}

enum PriceRange {
  FREE
  LOW
  MEDIUM
  HIGH
}
```

---

# 5. Frontend Business Flow

## Step 1

### Trip Duration

```text
How long do you plan to travel?
```

Options:

* 1 day
* 2 days 1 night
* 3 days 2 nights
* 4 days 3 nights
* Custom

---

## Step 2

### Preferences

```text
Which experiences do you prefer?
```

Multi Select:

* Nature
* Waterfalls
* Hills & Mountains
* Lakes & Seas
* Coffee
* Cuisine
* Culture
* History
* Spirituality
* Sightseeing / Check-in
* Relaxation
* Exploration
* Family
* Couples

Frontend:

```json
{
  "interests": [
    "nature",
    "coffee",
    "photography"
  ]
}
```

---

## Step 3

### Favorite Locations

Optional

```text
Are there any specific locations you want to visit?
```

Examples:

* Bien Ho (Lake)
* Minh Thanh Pagoda
* Chu Dang Ya (Volcano)
* Phu Cuong Waterfall

---

## Step 4

### Traveling with?

* Solo
* Couple
* Family
* Friends

---

## Step 5

### Travel Pace

* Slow / Relaxed
* Balanced
* Fast-paced / Active

---

## Step 6

### Budget

* Budget / Economic
* Mid-range
* Premium / Comfortable

---

## Step 7 (Optional)

### Transportation

* Motorbike
* Car
* Doesn't matter

Default:

```text
MOTORBIKE
```

---

## Step 8

Generate Itinerary

---

# 6. Recommendation Logic MVP

Do not use AI for the candidate discovery step.

Backend:

```text
Load Locations
      |
Tag Matching
      |
Category Matching
      |
Rating Score
      |
Budget Match
      |
Selected Location Boost
      |
Top Candidate Locations
```

Example:

```text
+30 Selected Location
+10 Interest Match
+10 Category Match
+5 Rating >= 4.5
+5 Budget Match
-10 Avoid Match
```

---

# 7. Agent Generate Flow

Backend:

```text
Create Trip
      |
Load Locations
      |
Score Locations
      |
Top Candidate Locations
      |
Call Agent
```

Agent:

```text
Understand Preferences
      |
Build Daily Plan
      |
Generate Overview
      |
Generate Reasons
      |
Return JSON
```

Backend:

```text
Persist TripDay
Persist TripStop
Persist AgentRun
```

---

# 8. Replan Flow

User:

```text
Optimize/Replan the itinerary
```

Backend:

```text
Load Current Trip
      |
Call Agent
      |
Receive New Plan
      |
Replace TripDay
      |
Replace TripStop
```

---

# 9. API MVP

## Location

```http
GET /locations
GET /locations/:id
```

## Trip

```http
POST /trips/generate

GET /trips

GET /trips/:id

PATCH /trips/:id

DELETE /trips/:id
```

## Trip Stop

```http
POST /trips/:tripId/days/:dayId/stops

PATCH /trips/:tripId/stops/:stopId

DELETE /trips/:tripId/stops/:stopId

PATCH /trips/:tripId/days/:dayId/stops/reorder
```

## Agent

```http
POST /trips/:tripId/replan
```

## Internal Agent API

NestJS Backend calls the FastAPI Agent Service after it validates locations and
loads POI snapshots from PostgreSQL.

```http
POST /api/v1/itineraries/custom
```

Request:

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

Response:

```json
{
  "status_code": 200,
  "message": "Lich trinh da duoc tao thanh cong",
  "data": {
    "itinerary": {},
    "route_summary": {
      "estimated_km": 86.2,
      "optimizer": "nearest_neighbor",
      "distance_source": "haversine_road_estimate",
      "total_pois": 3
    },
    "optimized_poi_order": []
  }
}
```

Rules:

* Agent Service must only use `selectedPois`.
* Agent Service must not query Qdrant or PostgreSQL for this REST flow.
* Agent Service must not replace missing POIs with random fallback locations.
* `optimizeRoute=false` keeps the user-provided POI order.

---

# 10. Phase 2 Roadmap

Post MVP / Phase 2:

* Embedding
* Qdrant
* Retrieval
* Semantic Search
* User Behavior Tracking
* Personalized Recommendation
* Collaborative Filtering
* Route Optimization
* Maps API Integration
