# Gia Lai AI Itinerary Planner

## Phase 1 MVP Design

Version: 1.0

---

# 1. Project Scope

## Mục tiêu

Xây dựng hệ thống AI hỗ trợ tạo lịch trình du lịch tại Gia Lai.

User có thể:

* Chọn sở thích du lịch
* Chọn địa điểm yêu thích
* Sinh itinerary bằng AI
* Chỉnh sửa itinerary
* Re-plan itinerary bằng AI

## Chưa làm trong MVP

Không sử dụng:

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

## Trách nhiệm

### Frontend

* Thu thập thông tin từ user
* Hiển thị itinerary
* Cho phép chỉnh sửa itinerary

### Backend

* Quản lý dữ liệu
* Validate request
* Tính điểm location
* Gọi Agent
* Lưu itinerary

### Agent

* Hiểu sở thích user
* Tạo lịch trình
* Giải thích recommendation
* Re-plan itinerary

Agent không được:

* Truy cập database
* Query PostgreSQL
* Tự tạo địa điểm mới

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

Nguồn dữ liệu địa điểm chính.

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

Một kế hoạch du lịch.

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

Lưu lịch sử Agent.

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

### Thời gian du lịch

```text
Bạn dự định đi trong bao lâu?
```

Options:

* 1 ngày
* 2 ngày 1 đêm
* 3 ngày 2 đêm
* 4 ngày 3 đêm
* Tùy chỉnh

---

## Step 2

### Sở thích

```text
Bạn thích trải nghiệm nào?
```

Multi Select:

* Thiên nhiên
* Thác nước
* Núi đồi
* Biển hồ
* Cafe
* Ẩm thực
* Văn hóa
* Lịch sử
* Tâm linh
* Check-in
* Thư giãn
* Khám phá
* Gia đình
* Cặp đôi

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

### Địa điểm yêu thích

Optional

```text
Có địa điểm nào bạn muốn đi không?
```

Ví dụ:

* Biển Hồ
* Chùa Minh Thành
* Chư Đăng Ya
* Thác Phú Cường

---

## Step 4

### Đi cùng ai?

* Một mình
* Cặp đôi
* Gia đình
* Bạn bè

---

## Step 5

### Nhịp độ

* Nhẹ nhàng
* Cân bằng
* Khám phá nhiều

---

## Step 6

### Ngân sách

* Tiết kiệm
* Vừa phải
* Thoải mái

---

## Step 7 (Optional)

### Phương tiện

* Xe máy
* Ô tô
* Không quan trọng

Default:

```text
MOTORBIKE
```

---

## Step 8

Generate Itinerary

---

# 6. Recommendation Logic MVP

Không dùng AI ở bước tìm candidate.

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

Ví dụ:

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
Tối ưu lại lịch trình
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

---

# 10. Phase 2 Roadmap

Sau MVP:

* Embedding
* Qdrant
* Retrieval
* Semantic Search
* User Behavior Tracking
* Personalized Recommendation
* Collaborative Filtering
* Route Optimization
* Maps API Integration

```
```
