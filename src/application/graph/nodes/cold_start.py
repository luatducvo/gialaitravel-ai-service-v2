"""
Node cold_start: Thu thập thông tin cơ bản cho chuyến đi.

Node này là bước đầu tiên trong pipeline khi ``memory.current_step == "cold_start"``.
Nó cố gắng thu thập ba trường bắt buộc:

- **duration**: Thời gian chuyến đi (ví dụ: "2d1n", "3d2n").
- **group**: Loại nhóm đồng hành (solo / couple / group / family).
- **transport**: Phương tiện di chuyển (motorbike / car).

Chiến lược trích xuất theo thứ tự ưu tiên:
    1. ``user_payload`` – dữ liệu từ form cold-start gửi kèm theo request.
    2. ``user_message`` – dùng LLM (Gemini) với structured output để parse
       câu tiếng Việt/Anh tự do.
    3. Nếu thiếu dữ liệu: trả về ``ws_response`` type ``"cold_start_form"``
       để frontend hiển thị form thu thập.

Sau khi đủ ba trường, node tính các filter phái sinh qua ``_apply_derived_filters``:
- ``intensity_filter``: ["low"] cho family/elderly, ["low","medium","high"] cho các nhóm khác.
- ``max_km_per_day``: 35 km (motorbike) hoặc 80 km (car).

Rồi chuyển ``memory.current_step`` sang ``"elicit"``.
"""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI
from loguru import logger
from pydantic import BaseModel, Field

from src.application.graph.state import AgentState
from src.core.config import settings


class ColdStartExtraction(BaseModel):
    """Schema structured-output cho LLM khi parse câu tiếng Việt/Anh.

    Được dùng với ``llm.with_structured_output(ColdStartExtraction)`` để đảm bảo
    LLM trả về đúng ba trường cần thiết cho cold-start.
    """

    duration: str = Field(description="Trip duration, for example 2d1n, 3d2n, 4d3n, or free text")
    group: str = Field(description="Companion group: solo, couple, group, family")
    transport: str = Field(description="Transport: motorbike or car")


GROUP_MAP = {
    "mot minh": "solo",
    "một mình": "solo",
    "solo": "solo",
    "cap doi": "couple",
    "cặp đôi": "couple",
    "couple": "couple",
    "nhom ban": "group",
    "nhóm bạn": "group",
    "group": "group",
    "gia dinh": "family",
    "gia đình": "family",
    "family": "family",
}

TRANSPORT_MAP = {
    "xe may": "motorbike",
    "xe máy": "motorbike",
    "motorbike": "motorbike",
    "o to": "car",
    "ô tô": "car",
    "car": "car",
}


def _normalize_choice(value: str | None, mapping: dict[str, str]) -> str | None:
    """Chuẩn hoá giá trị tiếng Việt/Anh về canonical English value.

    Args:
        value: Chuỗi cần chuẩn hoá (strip + lower).
        mapping: Dict ánh xạ từ tiếng Việt/alias → canonical value.

    Returns:
        Canonical value nếu tìm thấy trong mapping, ngược lại trả về
        chính ``value`` đã strip/lower. ``None`` nếu input là None/rỗng.
    """
    if not value:
        return None
    normalized = str(value).strip().lower()
    return mapping.get(normalized, normalized)


def _extract_from_payload(payload: dict) -> dict:
    """Trích xuất duration, group và transport từ ``user_payload``.

    Hỗ trợ nhiều key convention khác nhau từ phía client (camelCase, snake_case,
    tiếng Việt). Ưu tiên tìm trong sub-object ``trip`` / ``chuyen_di`` trước,
    sau đó fallback về root payload.

    Args:
        payload: Dict dữ liệu JSON gửi kèm từ client.

    Returns:
        Dict với ba key ``duration``, ``group``, ``transport``.
        Giá trị có thể là ``None`` nếu không tìm thấy.
    """
    trip = payload.get("trip") or payload.get("chuyen_di") or payload.get("chuyến đi của bạn") or {}
    source = trip if isinstance(trip, dict) else payload
    return {
        "duration": source.get("duration")
        or source.get("trip_duration")
        or source.get("chuyen_di")
        or source.get("chuyến đi của bạn"),
        "group": _normalize_choice(
            source.get("group") or source.get("companion") or source.get("nhom_dong_hanh"),
            GROUP_MAP,
        ),
        "transport": _normalize_choice(
            source.get("transport") or source.get("vehicle") or source.get("phuong_tien"),
            TRANSPORT_MAP,
        ),
        "optimize_route": source.get("optimize_route"),
    }


def _apply_derived_filters(memory) -> None:
    """Tính toán và ghi các filter phái sinh vào memory.

    Được gọi sau khi đã có đủ ``group`` và ``transport``.

    Quy tắc:
        - ``intensity_filter``: ["low"] nếu group là family hoặc elderly;
          ["low", "medium", "high"] cho các nhóm còn lại.
        - ``max_km_per_day``: 35.0 km cho motorbike; 80.0 km cho car.

    Args:
        memory (WorkingMemory): Bộ nhớ làm việc sẽ được cập nhật in-place.
    """
    if memory.group in ["family", "elderly"]:
        memory.intensity_filter = ["low"]
    else:
        memory.intensity_filter = ["low", "medium", "high"]

    memory.max_km_per_day = 35.0 if memory.transport == "motorbike" else 80.0


def cold_start_node(state: AgentState) -> dict:
    """LangGraph node – thu thập thông tin cơ bản cho chuyến đi.

    Luồng xử lý:
        1. Nếu thiếu bất kỳ trường nào trong {duration, group, transport}:
           a. Thử trích xuất từ ``user_payload`` qua ``_extract_from_payload``.
           b. Nếu ``user_payload`` không đủ, dùng LLM parse ``user_message``.
           c. Nếu cả hai đều thất bại: trả về ``ws_response`` type
              ``"cold_start_form"`` để frontend hiển thị form nhập liệu.
        2. Sau khi đủ dữ liệu: gọi ``_apply_derived_filters``, đặt
           ``memory.current_step = "elicit"`` và xoá ``user_message``.
        3. Nếu memory đã đủ ba trường ngay từ đầu (resume session):
           chỉ chuyển step sang ``"elicit"``.

    Args:
        state (AgentState): State hiện tại của LangGraph.

    Returns:
        dict: Partial state update với ``memory`` (và tuỳ trường hợp
        ``ws_responses``, ``user_message``).
    """
    memory = state["memory"]
    user_msg = state.get("user_message", "")
    payload = state.get("user_payload", {})
    logger.info("Entering cold-start node")

    if not memory.duration or not memory.group or not memory.transport:
        payload_values = _extract_from_payload(payload)
        if any(payload_values.values()):
            memory.duration = payload_values.get("duration") or memory.duration
            memory.group = payload_values.get("group") or memory.group
            memory.transport = payload_values.get("transport") or memory.transport

            # optimize_route mặc định True; chỉ ghi đè khi payload chỉ định rõ
            if payload_values.get("optimize_route") is not None:
                memory.optimize_route = bool(payload_values["optimize_route"])

            if memory.duration and memory.group and memory.transport:
                logger.success(
                    f"Cold-start extracted from payload: duration={memory.duration}, "
                    f"group={memory.group}, transport={memory.transport}"
                )
                _apply_derived_filters(memory)
                memory.current_step = "elicit"
                return {"memory": memory, "user_message": ""}

        if user_msg:
            logger.info(f"Extracting cold-start from user_msg: {user_msg}")
            llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                temperature=0,
                google_api_key=settings.GEMINI_API_KEY,
            )
            structured_llm = llm.with_structured_output(ColdStartExtraction)

            prompt = (
                "Extract trip planning fields from the user sentence for Gia Lai travel only. "
                "Map Vietnamese values to canonical English values: "
                "'Mot minh'/'Một mình' -> solo, 'Cap doi'/'Cặp đôi' -> couple, "
                "'Nhom ban'/'Nhóm bạn' -> group, 'Gia dinh'/'Gia đình' -> family, "
                "'Xe may'/'Xe máy' -> motorbike, 'O to'/'Ô tô' -> car. "
                f"User sentence: {user_msg}"
            )
            extracted = structured_llm.invoke(prompt)

            memory.duration = extracted.duration
            memory.group = extracted.group
            memory.transport = extracted.transport

            logger.success(
                f"Cold-start extracted: duration={memory.duration}, "
                f"group={memory.group}, transport={memory.transport}"
            )

            _apply_derived_filters(memory)
            memory.current_step = "elicit"
            return {"memory": memory, "user_message": ""}

        return {
            "ws_responses": [{
                "type": "cold_start_form",
                "step": "cold_start",
            }],
            "memory": memory,
            "user_message": user_msg,
        }

    memory.current_step = "elicit"
    return {"memory": memory, "user_message": ""}
