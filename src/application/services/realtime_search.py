from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from loguru import logger

from src.core.config import settings


def tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    api_key: Optional[str] = settings.TAVILY_API_KEY
    if not api_key:
        logger.info("TAVILY_API_KEY is not configured; skipping realtime search")
        return []

    payload = json.dumps(
        {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
        }
    ).encode("utf-8")
    request = Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    max_attempts = max(settings.TAVILY_MAX_RETRIES, 0) + 1
    timeout = max(settings.TAVILY_TIMEOUT_SECONDS, 1.0)

    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            return body.get("results", [])
        except (OSError, URLError, json.JSONDecodeError) as exc:
            if attempt >= max_attempts:
                logger.warning(f"Tavily search failed after {attempt} attempts: {exc}")
                return []
            logger.info(f"Tavily search attempt {attempt} failed, retrying: {exc}")
            time.sleep(min(attempt, 3))

    return []
