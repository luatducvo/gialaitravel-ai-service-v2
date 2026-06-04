"""
Pydantic schemas cho WebSocket protocol tại /ws/chat.

## Input (Frontend → Backend)

Frontend gửi JSON có cấu trúc ``WsInput``.
Trường ``payload`` thay đổi tuỳ theo ``type``:

- ``"cold_start_form"``  – Gửi kèm ``ColdStartPayload`` để khởi tạo chuyến đi.
- ``"user_message"``     – Gửi tin nhắn tự do hoặc chip value.

Ví dụ cold_start_form với optimize_route:
```json
{
  "type": "cold_start_form",
  "session_id": "abc123",
  "payload": {
    "message": "",
    "trip": {
      "duration": "2d1n",
      "group": "couple",
      "transport": "motorbike",
      "optimize_route": false
    }
  }
}
```

## Response (Backend → Frontend)

Backend stream về nhiều loại message, phân biệt qua trường ``type``:

| type                   | Schema                    | Mô tả                                      |
|------------------------|---------------------------|--------------------------------------------|
| ``cold_start_form``    | ``WsColdStartFormResponse``   | Yêu cầu Frontend hiển thị form cold-start |
| ``elicitation_question``| ``WsElicitationResponse``| Hỏi vibe chuyến đi, kèm UI chips          |
| ``itinerary``          | ``WsItineraryResponse``   | Lịch trình + tuyến đường đã tối ưu        |
| ``guardrail``          | ``WsGuardrailResponse``   | Tin nhắn bị chặn bởi guardrail            |
| ``error``              | ``WsErrorResponse``       | Lỗi xử lý                                 |
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Input schemas (Frontend → Backend)
# ---------------------------------------------------------------------------

class ColdStartTripPayload(BaseModel):
    """Thông tin chuyến đi gửi kèm khi type=cold_start_form.

    ``optimize_route``:
        - ``true``  (default): Backend tự sắp xếp thứ tự POI tối ưu theo
          thuật toán nearest-neighbor để giảm quãng đường di chuyển.
        - ``false``: Giữ nguyên thứ tự kết quả tìm kiếm (user tự kiểm soát).
    """

    duration: str = Field(..., description="Thời lượng chuyến đi, ví dụ: '1 ngày', '2d1n'")
    group: str = Field(
        ..., description="Loại nhóm: solo | couple | group | family | elderly"
    )
    transport: str = Field(..., description="Phương tiện: motorbike | car | bus")
    optimize_route: bool = Field(
        True,
        description=(
            "Tối ưu thứ tự POI (nearest-neighbor). "
            "true = để backend sắp xếp, false = giữ nguyên thứ tự tìm kiếm."
        ),
    )


class WsPayload(BaseModel):
    """Payload chung của mọi WS message.

    ``chip_value`` được ưu tiên hơn ``message`` nếu cả hai đều có.
    ``trip`` chỉ dùng khi gửi cold_start_form.
    """

    message: str = Field("", description="Tin nhắn tự do từ user")
    chip_value: Optional[str] = Field(
        None, description="Giá trị chip UI (confirm / refine / ...)"
    )
    trip: Optional[ColdStartTripPayload] = Field(
        None, description="Thông tin chuyến đi (chỉ dùng khi type=cold_start_form)"
    )


class WsInput(BaseModel):
    """Cấu trúc JSON đầy đủ mà Frontend gửi qua WebSocket."""

    type: str = Field(
        "user_message", description="Loại message: user_message | cold_start_form"
    )
    session_id: str = Field(..., description="Session ID duy nhất của phiên chat")
    payload: WsPayload


# ---------------------------------------------------------------------------
# Response schemas (Backend → Frontend)
# ---------------------------------------------------------------------------

class WsUiChip(BaseModel):
    """Một chip UI để Frontend hiển thị dưới dạng quick-reply button."""

    label: str = Field(..., description="Text hiển thị trên chip")
    value: str = Field(..., description="Giá trị gửi lại khi user click")


class WsRouteSummary(BaseModel):
    """Thông tin tóm tắt tuyến đường sau khi tối ưu.

    Frontend dùng ``optimizer`` để hiển thị badge "Đã tối ưu tuyến đường"
    và ``distance_source`` để hiển thị disclaimer độ chính xác khoảng cách.
    """

    estimated_km: float = Field(..., description="Tổng km ước tính toàn tuyến")
    optimizer: str = Field(
        ...,
        description=(
            "Thuật toán tối ưu đã dùng: "
            "'nearest_neighbor' = backend đã sắp xếp lại | "
            "'user_defined_order' = giữ nguyên thứ tự | "
            "'none' = không có POI"
        ),
    )
    distance_source: str = Field(
        ...,
        description=(
            "Nguồn dữ liệu khoảng cách: "
            "'google_maps' = chính xác theo đường thực tế | "
            "'haversine_road_estimate' = ước tính (haversine × terrain factor) | "
            "'mixed' = kết hợp cả hai | "
            "'none' = không tính được"
        ),
    )


class WsOptimizedPoiItem(BaseModel):
    """Một POI trong tuyến đường đã tối ưu — dùng để render marker + polyline trên bản đồ."""

    poi_id: str = Field(..., description="ID duy nhất của POI")
    poi_name: str = Field(..., description="Tên hiển thị")
    lat: Optional[float] = Field(None, description="Vĩ độ")
    lng: Optional[float] = Field(None, description="Kinh độ")
    route_order: int = Field(..., description="Thứ tự trong tuyến đường (bắt đầu từ 1)")
    distance_from_prev_km: float = Field(
        0.0,
        description="Khoảng cách đường bộ từ POI trước đó (km); luôn là 0 với điểm đầu tiên",
    )


class WsItineraryResponse(BaseModel):
    """Response khi ``type == 'itinerary'``.

    Đây là message chính chứa lịch trình + tuyến đường tối ưu.

    Cách Frontend sử dụng:
    - ``itinerary``: Render lịch trình theo ngày/hoạt động.
    - ``optimized_poi_order``: Render marker và polyline trên bản đồ theo thứ tự.
    - ``route_summary.optimizer``: Hiển thị badge "Đã tối ưu" nếu là
      ``nearest_neighbor``.
    - ``route_summary.distance_source``: Hiển thị disclaimer nếu là
      ``haversine_road_estimate`` hoặc ``mixed``.
    """

    type: str = Field("itinerary", description="Luôn là 'itinerary'")
    step: str = Field("plan", description="Bước hiện tại trong pipeline")
    agent_message: str = Field(..., description="Tin nhắn từ agent gửi kèm lịch trình")
    itinerary: Dict[str, Any] = Field(
        ..., description="Lịch trình chi tiết theo ngày (days → activities)"
    )
    route_summary: WsRouteSummary = Field(
        ..., description="Thống kê tuyến đường đã tối ưu"
    )
    optimized_poi_order: List[WsOptimizedPoiItem] = Field(
        ...,
        description=(
            "Danh sách POI theo thứ tự tuyến đường đã tối ưu, kèm tọa độ và khoảng cách segment. "
            "Dùng để render marker + polyline trên bản đồ. "
            "Kiểm tra route_summary.optimizer để biết có tối ưu hay không."
        ),
    )
    ui_chips: List[WsUiChip] = Field(
        ..., description="Quick-reply chips: confirm | refine"
    )


class WsColdStartFormResponse(BaseModel):
    """Response khi ``type == 'cold_start_form'``.

    Backend yêu cầu Frontend hiển thị form thu thập thông tin chuyến đi.
    """

    type: str = Field("cold_start_form", description="Luôn là 'cold_start_form'")
    step: str = Field("cold_start", description="Bước hiện tại trong pipeline")


class WsElicitationResponse(BaseModel):
    """Response khi ``type == 'elicitation_question'``.

    Backend hỏi vibe chuyến đi. Frontend hiển thị câu hỏi + chips gợi ý
    và cho phép nhập tự do nếu ``allow_free_text`` là ``True``.
    """

    type: str = Field("elicitation_question", description="Luôn là 'elicitation_question'")
    step: str = Field("elicit", description="Bước hiện tại trong pipeline")
    ui_chips: List[WsUiChip] = Field(..., description="Chips gợi ý vibe chuyến đi")
    allow_free_text: bool = Field(
        True, description="Cho phép user nhập tự do ngoài chips"
    )


class WsGuardrailResponse(BaseModel):
    """Response khi ``type == 'guardrail'``.

    Tin nhắn bị chặn vì không thuộc phạm vi du lịch Gia Lai.
    """

    type: str = Field("guardrail", description="Luôn là 'guardrail'")
    step: str = Field(..., description="Bước hiện tại lúc bị chặn")
    agent_message: str = Field(..., description="Lý do và hướng dẫn từ agent")
    reason: str = Field(..., description="Mã lý do nội bộ")


class WsErrorResponse(BaseModel):
    """Response khi ``type == 'error'``.

    Lỗi không mong muốn trong quá trình xử lý.
    """

    type: str = Field("error", description="Luôn là 'error'")
    agent_message: str = Field(..., description="Thông báo lỗi hiển thị cho user")
