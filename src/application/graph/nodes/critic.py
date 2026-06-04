"""
Node critic: Xử lý phản hồi của người dùng sau khi xem itinerary.

Node này đảm nhiệm toàn bộ pha "refine" trong pipeline và xử lý 6 luồng riêng biệt:

1. **confirm** – Người dùng hài lòng: chuyển ``current_step = "finalized"``.

2. **refine** (menu) – Hiển thị UI chips tuỳ chọn điều chỉnh:
   thay đổi điểm đến, giảm di chuyển, hoặc nhập tự do.

3. **Câu hỏi sự kiện / realtime** – Phát hiện qua ``EVENT_MARKERS``:
   Gọi Tavily để tìm sự kiện, lễ hội sắp tới ở Gia Lai.
   Trả về ``ws_response`` type ``"realtime_info"``.

4. **Câu hỏi review / đánh giá** – Phát hiện qua ``REVIEW_MARKERS``:
   Tìm POI trong itinerary khớp với message, gọi Tavily với query review.
   Trả về ``ws_response`` type ``"poi_review"``.

5. **Câu hỏi chi tiết / mô tả** – Phát hiện qua ``DETAIL_MARKERS``:
   Tương tự trên nhưng query chi tiết địa chỉ, giờ mở cửa.
   Trả về ``ws_response`` type ``"poi_detail"``.

6. **Phản hồi điều chỉnh lịch trình** – Mọi message còn lại:
   Phân loại ``reason_tag`` (distance_overload / user_preference),
   ghi vào ``memory.learned_constraints``, reset itinerary và
   chuyển ``current_step = "plan"`` để tạo lại.

Cả ba luồng 3-5 đều **không** tạo lại itinerary – chỉ trả về thông tin
bổ sung mà không thay đổi lịch trình hiện tại.
"""

from __future__ import annotations

import unicodedata

from loguru import logger

from src.application.graph.state import AgentState
from src.application.services.realtime_search import tavily_search

# ---------------------------------------------------------------------------
# Intent marker groups
# ---------------------------------------------------------------------------
DETAIL_MARKERS = (
    "chi tiet", "chi tiết",
    "thong tin", "thông tin",
    "o dau", "ở đâu",
    "gio mo cua", "giờ mở cửa",
    "mo cua", "mở cửa",
    "dia chi", "địa chỉ",
    "ve dep", "vẻ đẹp",
    "mo ta", "mô tả",
    "nhu the nao", "như thế nào",
    "the nao", "thế nào",
    "co gi", "có gì",
    "dep khong", "đẹp không",
    "vui khong", "vui không",
    "thu vi khong", "thú vị không",
)

REVIEW_MARKERS = (
    "review",
    "danh gia", "đánh giá",
    "trai nghiem", "trải nghiệm",
    "nhan xet", "nhận xét",
    "cam nhan", "cảm nhận",
    "co dang di khong", "có đáng đi không",
    "dang di khong", "đáng đi không",
    "co tot khong", "có tốt không",
    "nguoi ta noi gi", "người ta nói gì",
    "moi nguoi noi gi", "mọi người nói gì",
    "rating",
    "xep hang", "xếp hạng",
    "sao",
    "tot khong", "tốt không",
    "nen di khong", "nên đi không",
)

EVENT_MARKERS = (
    "su kien", "sự kiện",
    "le hoi", "lễ hội",
    "sap toi", "sắp tới",
    "realtime",
    "hom nay", "hôm nay",
    "tuan nay", "tuần này",
    "thang nay", "tháng này",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Chuyển chuỗi tiếng Việt về ASCII không dấu để so sánh mờ (fuzzy).

    Dùng chuẩn hóa NFKD để tách dấu khỏi ký tự cơ sở, sau đó loại bỏ
    các combining characters (dấu).

    Args:
        text: Chuỗi tiếng Việt có dấu.

    Returns:
        Chuỗi ASCII thường, không dấu.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _find_poi_in_itinerary(memory, message: str) -> dict | None:
    """Tìm activity trong itinerary khớp với tên POI được đề cập trong message.

    So sánh theo 3 cấp độ giảm dần về độ chính xác:
        1. **Exact substring có dấu** – tên POI là substring của message (lower).
           → Trả về ngay lập tức nếu khớp.
        2. **Exact substring không dấu** – sau khi strip accents cả hai.
           → Ghi nhận score=2.
        3. **Partial word matching** – split tên POI thành từ ≥4 ký tự,
           tính tỷ lệ từ khớp. Nếu ≥50% và cao hơn best_score hiện tại
           → cập nhật best_match.

    Args:
        memory (WorkingMemory): Bộ nhớ chứa ``current_itinerary``.
        message (str): Tin nhắn của người dùng.

    Returns:
        Dict activity đầu tiên khớp tốt nhất, hoặc ``None`` nếu không tìm thấy.
    """
    itinerary = memory.current_itinerary or {}
    msg_normalized = message.lower()
    msg_stripped = _strip_accents(message)

    best_match: dict | None = None
    best_score = 0

    for day in itinerary.get("days", []):
        for activity in day.get("activities", []):
            poi_name = str(activity.get("poi_name", ""))
            if not poi_name:
                continue

            name_lower = poi_name.lower()
            name_stripped = _strip_accents(poi_name)

            # Level 1: exact substring (with accents)
            if name_lower in msg_normalized:
                return activity  # perfect match, return immediately

            # Level 2: exact substring (without accents)
            if name_stripped in msg_stripped:
                best_match = activity
                best_score = max(best_score, 2)
                continue

            # Level 3: partial word matching
            words = [w for w in name_stripped.split() if len(w) >= 4]
            if words:
                matches = sum(1 for w in words if w in msg_stripped)
                score = matches / len(words)
                if score >= 0.5 and score > best_score:
                    best_score = score
                    best_match = activity

    return best_match


def _build_tavily_query(poi_activity: dict | None, user_msg: str, intent: str) -> str:
    """Xây dựng query tối ưu cho Tavily search.

    Ưu tiên dùng tên POI thực từ itinerary thay vì câu hỏi thô của người dùng
    để tăng độ chính xác kết quả tìm kiếm.

    Args:
        poi_activity: Activity dict từ itinerary (có ``poi_name``), hoặc ``None``.
        user_msg: Tin nhắn gốc của người dùng (fallback khi không có POI).
        intent: Mục đích tìm kiếm – ``"review"`` hoặc ``"detail"``.

    Returns:
        Chuỗi query Tavily đã được tối ưu theo intent.
    """
    poi_name = (poi_activity or {}).get("poi_name", "")

    if poi_name:
        base = f"{poi_name} Gia Lai"
    else:
        base = f"Gia Lai {user_msg}"

    if intent == "review":
        return f"review đánh giá trải nghiệm {base}"
    if intent == "detail":
        return f"thông tin chi tiết địa chỉ giờ mở cửa {base}"
    return base


def _collect_all_poi_names(memory) -> list[str]:
    """Lấy danh sách tên tất cả POI trong itinerary hiện tại.

    Args:
        memory (WorkingMemory): Bộ nhớ chứa ``current_itinerary``.

    Returns:
        List tên POI (str) theo thứ tự xuất hiện trong itinerary.
        Trả về list rỗng nếu chưa có itinerary.
    """
    itinerary = memory.current_itinerary or {}
    names = []
    for day in itinerary.get("days", []):
        for activity in day.get("activities", []):
            name = activity.get("poi_name")
            if name:
                names.append(name)
    return names


def _format_tavily_results(results: list[dict]) -> list[dict]:
    """Chuẩn hoá kết quả Tavily về format tối giản để gửi về client.

    Args:
        results: Danh sách result dict từ Tavily API.

    Returns:
        List dict chỉ chứa ``title``, ``url``, ``content``, ``score``.
    """
    return [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "content": r.get("content"),
            "score": r.get("score"),
        }
        for r in results
    ]


def _format_event_summaries(results: list[dict]) -> list[dict]:
    """Rút gọn nội dung sự kiện để hiển thị dạng card trên UI.

    Mỗi kết quả được truncate ở 220 ký tự và thêm "..." nếu dài hơn.

    Args:
        results: Danh sách result dict từ Tavily API.

    Returns:
        List dict gồm ``title`` và ``description`` (≤220 ký tự).
    """
    summaries = []
    for r in results:
        content = (r.get("content") or "").strip()
        description = content[:220].rstrip()
        if len(content) > 220:
            description += "..."
        summaries.append({"title": r.get("title"), "description": description})
    return summaries


def _is_detail_question(message: str) -> bool:
    normalized = message.lower()
    stripped = _strip_accents(message)
    return any(m in normalized or m in stripped for m in DETAIL_MARKERS)


def _is_review_question(message: str) -> bool:
    normalized = message.lower()
    stripped = _strip_accents(message)
    return any(m in normalized or m in stripped for m in REVIEW_MARKERS)


def _is_event_question(message: str) -> bool:
    normalized = message.lower()
    stripped = _strip_accents(message)
    return any(m in normalized or m in stripped for m in EVENT_MARKERS)


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

def critic_node(state: AgentState) -> dict:
    """LangGraph node – xử lý toàn bộ pha refine/critic.

    Phân loại tin nhắn người dùng và xử lý theo 6 luồng (xem module docstring).
    Node này **không** tạo lại itinerary trực tiếp; chỉ luồng 6 mới reset
    itinerary và chuyển step về ``"plan"`` để trigger lại pipeline.

    Args:
        state (AgentState): State hiện tại của LangGraph.

    Returns:
        dict: Partial state update tuỳ theo luồng:
            - Luồng 1 (confirm): ``memory`` với ``current_step="finalized"``.
            - Luồng 2 (refine menu): ``ws_responses`` chứa refinement_options.
            - Luồng 3–5 (realtime/review/detail): ``ws_responses`` chứa kết quả
              Tavily, ``memory`` không thay đổi.
            - Luồng 6 (điều chỉnh): ``memory`` với itinerary=None,
              ``current_step="plan"``, ``critic_feedback`` dict.
            - Fallback: chỉ ``memory``.
    """
    memory = state["memory"]
    user_msg = state.get("user_message", "")
    normalized_msg = user_msg.strip().lower()
    logger.info("Entering critic node")

    # --- 1. Confirm ---
    if normalized_msg == "confirm":
        logger.success("User confirmed the itinerary")
        memory.current_step = "finalized"
        return {"memory": memory, "user_message": ""}

    # --- 2. Refine menu ---
    if normalized_msg == "refine":
        return {
            "ws_responses": [{
                "type": "refinement_options",
                "step": "refine",
                "agent_message": "Bạn muốn điều chỉnh phần nào của lịch trình?",
                "ui_chips": [
                    {"label": "Thay đổi điểm đến", "value": "change_poi"},
                    {"label": "Giảm thời gian di chuyển", "value": "reduce_travel"},
                    {"label": "Khác", "value": "custom"},
                ],
            }],
            "memory": memory,
            "user_message": "",
        }

    # --- 3. Event / realtime question ---
    if user_msg and _is_event_question(user_msg):
        results = tavily_search(
            f"sự kiện lễ hội du lịch Gia Lai {user_msg} 2026",
            max_results=5,
        )
        return {
            "ws_responses": [{
                "type": "realtime_info",
                "step": "refine",
                "agent_message": (
                    "Các sự kiện chính sắp tới ở Gia Lai:"
                    if results
                    else "Chưa tìm thấy sự kiện sắp tới phù hợp ở Gia Lai."
                ),
                "results": _format_event_summaries(results),
            }],
            "memory": memory,
            "user_message": "",
        }

    # --- 4. Review question ---
    if user_msg and _is_review_question(user_msg):
        poi = _find_poi_in_itinerary(memory, user_msg)
        query = _build_tavily_query(poi, user_msg, intent="review")
        logger.info(f"POI review query: {query!r} (matched poi: {(poi or {}).get('poi_name')})")
        results = tavily_search(query, max_results=5)
        return {
            "ws_responses": [{
                "type": "poi_review",
                "step": "refine",
                "agent_message": (
                    f"Mình tổng hợp review và đánh giá về {(poi or {}).get('poi_name', 'địa điểm')} nhé."
                    if results
                    else "Chưa tìm thấy review nào cho địa điểm này. Bạn có thể thử hỏi về địa điểm khác trong lịch trình nhé."
                ),
                "poi": poi,
                "results": _format_tavily_results(results),
            }],
            "memory": memory,
            "user_message": "",
        }

    # --- 5. Detail / description question ---
    if user_msg and _is_detail_question(user_msg):
        poi = _find_poi_in_itinerary(memory, user_msg)
        query = _build_tavily_query(poi, user_msg, intent="detail")
        logger.info(f"POI detail query: {query!r} (matched poi: {(poi or {}).get('poi_name')})")
        results = tavily_search(query, max_results=3)
        return {
            "ws_responses": [{
                "type": "poi_detail",
                "step": "refine",
                "agent_message": (
                    f"Đây là thông tin chi tiết về {(poi or {}).get('poi_name', 'địa điểm')} mình tổng hợp được."
                    if results
                    else "Chưa tìm thấy thông tin chi tiết về địa điểm này."
                ),
                "poi": poi,
                "results": _format_tavily_results(results),
            }],
            "memory": memory,
            "user_message": "",
        }

    # --- 6. Itinerary refinement / rejection ---
    if user_msg:
        logger.info(f"Received refinement feedback: {user_msg}")

        reason_tag = "user_preference"
        if any(marker in normalized_msg for marker in ("xa", "km", "met", "mệt", "duong", "đường")):
            reason_tag = "distance_overload"

        critic_feedback = {
            "event": "user_rejected_itinerary",
            "reason_tag": reason_tag,
            "rejected_segment": user_msg,
        }

        memory.learned_constraints.append(f"[{reason_tag}] {user_msg}")
        memory.current_step = "plan"
        memory.current_itinerary = None

        return {"memory": memory, "user_message": "", "critic_feedback": critic_feedback}

    return {"memory": memory}
