from __future__ import annotations

from dataclasses import dataclass, field

from langchain_google_genai import ChatGoogleGenerativeAI
from loguru import logger
from pydantic import BaseModel

from src.core.config import settings

# ---------------------------------------------------------------------------
# Prompt-injection markers (keyword-based, always applied first)
# ---------------------------------------------------------------------------
INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "bỏ qua hướng dẫn",
    "bo qua huong dan",
    "quên chỉ dẫn",
    "quen chi dan",
    "system prompt",
    "developer message",
    "jailbreak",
    "prompt injection",
    "act as",
    "đóng vai",
    "dong vai",
    "pretend you are",
    "roleplay as",
    "you are now",
    "bây giờ bạn là",
    "bay gio ban la",
    "forget your instructions",
    "override instructions",
)

# ---------------------------------------------------------------------------
# Quick-pass travel markers – skip LLM call if clearly in scope
# ---------------------------------------------------------------------------
TRAVEL_CONTEXT_MARKERS = (
    "gia lai",
    "pleiku",
    "biển hồ",
    "bien ho",
    "chư đăng ya",
    "chu dang ya",
    "măng đen",
    "mang den",
    "du lịch",
    "du lich",
    "lịch trình",
    "lich trinh",
    "địa điểm",
    "dia diem",
    "sự kiện",
    "su kien",
    "ăn",
    "ở đâu",
    "o dau",
    "đi chơi",
    "di choi",
    "khách sạn",
    "khach san",
    "nhà nghỉ",
    "nha nghi",
    "quán ăn",
    "quan an",
    "trekking",
    "dã ngoại",
    "da ngoai",
    "thác",
    "thac",
    "núi",
    "nui",
    "rừng",
    "rung",
    "hồ",
    "lễ hội",
    "le hoi",
    "bản địa",
    "ban dia",
    "cà phê",
    "ca phe",
    "phượt",
    "phuot",
    "confirm",
    "refine",
)

# ---------------------------------------------------------------------------
# Hard out-of-scope markers – skip LLM call if clearly off-topic
# ---------------------------------------------------------------------------
HARD_OOS_MARKERS = (
    "viết code",
    "viet code",
    "lập trình",
    "lap trinh",
    "debug",
    "fix bug",
    "python",
    "javascript",
    "typescript",
    "react",
    "thuật toán",
    "thuat toan",
    "bài toán",
    "bai toan",
    "chứng khoán",
    "chung khoan",
    "bitcoin",
    "crypto",
    "tiền điện tử",
    "tien dien tu",
    "đầu tư tài chính",
    "dau tu tai chinh",
    "hướng dẫn cách nấu",
    "huong dan cach nau",
    "công thức nấu",
    "cong thuc nau",
    "bóng đá",
    "bong da",
    "thể thao",
    "the thao",
    "tin tức",
    "tin tuc",
    "chính trị",
    "chinh tri",
    "hà nội",
    "ha noi",
    "đà nẵng",
    "da nang",
    "nha trang",
    "đà lạt",
    "da lat",
    "hội an",
    "hoi an",
    "sài gòn",
    "sai gon",
    "hcm",
    "hồ chí minh",
    "ho chi minh",
    "vịnh hạ long",
    "vinh ha long",
    "phú quốc",
    "phu quoc",
    "thuốc",
    "thuoc",
    "bệnh",
    "benh",
    "triệu chứng",
    "trieu chung",
    "chẩn đoán",
    "chan doan",
    "luật",
    "luat",
    "pháp lý",
    "phap ly",
    "ly hôn",
    "ly hon",
    "kiện tụng",
    "kien tung",
    "toán học",
    "toan hoc",
    "vật lý",
    "vat ly",
    "hóa học",
    "hoa hoc",
    "lịch sử thế giới",
    "lich su the gioi",
    "dịch văn bản",
    "dich van ban",
    "translate",
    "weather",
    "thời tiết",
    "thoi tiet",
)


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    reason: str = ""
    message: str = ""


class _ScopeClassification(BaseModel):
    is_in_scope: bool
    reason: str


def _llm_classify(message: str, current_step: str, has_itinerary: bool) -> GuardrailResult:
    """Use a small LLM call to decide scope when keyword heuristics are inconclusive."""
    try:
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            temperature=0,
            google_api_key=settings.GEMINI_API_KEY,
        )
        structured_llm = llm.with_structured_output(_ScopeClassification)

        context_hint = ""
        if has_itinerary:
            context_hint = (
                "The user already has a Gia Lai travel itinerary generated. "
                "Questions about destinations, activities, timing, or refinements of that itinerary are in scope. "
            )

        prompt = (
            "You are a scope-checker for a Gia Lai (Vietnam) travel planning assistant. "
            "Decide whether the user message is IN SCOPE for this service.\n\n"
            "IN SCOPE examples:\n"
            "- Planning or adjusting a trip to Gia Lai\n"
            "- Asking about places, food, events, hotels, transport in Gia Lai\n"
            "- Confirming or refining a generated itinerary\n"
            "- General travel questions that clearly relate to Gia Lai\n\n"
            "OUT OF SCOPE examples:\n"
            "- Coding, programming, algorithms\n"
            "- Medical advice, legal advice, financial advice\n"
            "- Travel to other destinations not related to Gia Lai\n"
            "- News, politics, entertainment unrelated to Gia Lai travel\n"
            "- Cooking recipes unrelated to Gia Lai cuisine\n\n"
            f"{context_hint}"
            f"Current pipeline step: {current_step}\n"
            f"User message: {message}\n\n"
            "Return is_in_scope=true if the message is about Gia Lai travel or the user's current itinerary."
        )

        result: _ScopeClassification = structured_llm.invoke(prompt)
        if result.is_in_scope:
            return GuardrailResult(True)
        return GuardrailResult(
            False,
            "out_of_scope",
            _oos_reply(),
        )
    except Exception as exc:
        # Fail open: if LLM classification fails, let the pipeline handle it
        logger.warning(f"Guardrail LLM classification failed, failing open: {exc}")
        return GuardrailResult(True)


def _oos_reply() -> str:
    return (
        "Mình chỉ hỗ trợ lập lịch trình, tư vấn địa điểm, ẩm thực và sự kiện "
        "du lịch tại Gia Lai. Bạn có thể hỏi mình về:\n"
        "• Lịch trình tham quan Gia Lai\n"
        "• Địa điểm nổi tiếng như Biển Hồ, Chư Đăng Ya, Măng Đen\n"
        "• Ẩm thực và văn hóa bản địa Gia Lai\n"
        "• Sự kiện, lễ hội tại Gia Lai\n\n"
        "Bạn gửi lại yêu cầu liên quan đến du lịch Gia Lai giúp mình nhé 🙏"
    )


def _injection_reply() -> str:
    return (
        "Mình không thể xử lý yêu cầu đó. "
        "Hãy hỏi mình về lịch trình hay địa điểm du lịch Gia Lai nhé!"
    )


def check_user_message_scope(
    message: str,
    *,
    current_step: str = "cold_start",
    has_itinerary: bool = False,
) -> GuardrailResult:
    """
    Three-tier scope check:
      1. Prompt-injection → always block, no LLM needed.
      2. Keyword quick-pass → clearly in scope, skip LLM.
      3. Keyword hard-OOS  → clearly out of scope, skip LLM.
      4. Ambiguous         → LLM classification.
    """
    normalized = (message or "").strip().lower()

    if not normalized:
        # Empty message – let the pipeline decide (e.g. cold_start form)
        return GuardrailResult(True)

    # --- Tier 1: Prompt injection ---
    if any(marker in normalized for marker in INJECTION_MARKERS):
        logger.warning("Guardrail blocked: prompt_injection")
        return GuardrailResult(False, "prompt_injection", _injection_reply())

    # --- Tier 2: Clearly in scope (fast pass) ---
    if any(marker in normalized for marker in TRAVEL_CONTEXT_MARKERS):
        return GuardrailResult(True)

    # --- Tier 3: Clearly out of scope (fast block) ---
    hard_oos = any(marker in normalized for marker in HARD_OOS_MARKERS)
    if hard_oos:
        # But if user already has an itinerary being refined, be more lenient
        if not has_itinerary:
            logger.warning("Guardrail blocked: out_of_scope (keyword)")
            return GuardrailResult(False, "out_of_scope", _oos_reply())

    # --- Tier 4: LLM classification for ambiguous cases ---
    return _llm_classify(normalized, current_step, has_itinerary)
