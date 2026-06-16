"""配置解析：将 AstrBot 原始 dict 配置转换为 NewsConfig。"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .models import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_DAILYHOT_BASE_URL,
    DEFAULT_MAX_ITEMS,
    DEFAULT_SOURCE_IDS,
    DEFAULT_TIMEOUT_SECONDS,
    LEGACY_GOOGLE_RSS_URL,
    NewsConfig,
    NewsSource,
)
from .sources import BUILTIN_SOURCES

_logger = logging.getLogger(__name__)

# 默认 AI 摘要提示词
DEFAULT_AI_SUMMARY_PROMPT = "请用不超过30字概括以下新闻标题的核心内容："

# 中文字段名 → 旧英文字段名，用于向后兼容
_FIELD_COMPAT: dict[str, str] = {
    "新闻源": "source_ids",
    "自定义源": "custom_sources",
    "每日热榜地址": "dailyhot_base_url",
    "旧版RSS地址": "rss_url",
    "最大条数": "max_items",
    "请求超时": "request_timeout_seconds",
    "启用命令": "enable_fallback_commands",
    "缓存有效期": "cache_ttl_seconds",
    "启用AI摘要": "enable_ai_summary",
    "AI摘要提示词": "ai_summary_prompt",
    "Redis地址": "redis_url",
}


# ---------------------------------------------------------------------------
# 类型转换辅助函数
# ---------------------------------------------------------------------------

def coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def coerce_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def coerce_source_tokens(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = re.split(r"[\r\n,;]+", value)
        return [item.strip() for item in raw_items if item.strip()]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, str)):
        tokens = []
        for item in value:
            token = str(item).strip()
            if token:
                tokens.append(token)
        return tokens
    token = str(value).strip()
    return [token] if token else []


# ---------------------------------------------------------------------------
# URL 构建 & 源解析
# ---------------------------------------------------------------------------

def build_dailyhot_url(base_url: str, route: str) -> str:
    return f"{base_url.rstrip('/')}/{route.lstrip('/')}"


def parse_custom_sources(value: Any, dailyhot_base_url: str) -> dict[str, NewsSource]:
    if not value:
        return {}
    try:
        items = json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError) as exc:
        _logger.warning("自定义源 JSON 解析失败: %s", exc)
        return {}
    if not isinstance(items, list):
        _logger.warning("自定义源不是 JSON 数组，已忽略")
        return {}

    registry: dict[str, NewsSource] = {}
    for item in items:
        if not isinstance(item, Mapping):
            _logger.warning("自定义源条目不是对象，已跳过: %r", item)
            continue
        source_id = str(item.get("id") or "").strip()
        display_name = str(item.get("name") or "").strip()
        source_type = str(item.get("type") or "").strip().lower()
        endpoint = str(item.get("endpoint") or "").strip()
        if not source_id or not endpoint or source_type not in {"rss", "dailyhot"}:
            _logger.warning("自定义源条目缺少必填字段或 type 无效，已跳过: %r", item)
            continue
        if source_id in BUILTIN_SOURCES:
            _logger.warning("自定义源 ID %r 与内置源冲突，已跳过", source_id)
            continue
        if not display_name:
            display_name = source_id
        if source_type == "dailyhot":
            endpoint = build_dailyhot_url(dailyhot_base_url, endpoint)
        registry[source_id] = NewsSource(
            source_id=source_id,
            display_name=display_name,
            source_type=source_type,
            endpoint=endpoint,
        )
    return registry


def resolve_source_token(
    token: str,
    dailyhot_base_url: str,
    custom_registry: dict[str, NewsSource] | None = None,
) -> NewsSource:
    """将用户配置的 source token 解析为 NewsSource 实例。"""
    builtin = BUILTIN_SOURCES.get(token)
    if builtin is not None:
        source_id, display_name, source_type, endpoint, category, suggested_ttl = builtin
        if source_type == "dailyhot":
            endpoint = build_dailyhot_url(dailyhot_base_url, endpoint)
        return NewsSource(
            source_id=source_id,
            display_name=display_name,
            source_type=source_type,
            endpoint=endpoint,
            category=category,
            suggested_ttl=suggested_ttl,
        )

    if custom_registry:
        custom = custom_registry.get(token)
        if custom is not None:
            return custom

    if token.startswith("dailyhot:"):
        route = token.split(":", 1)[1].strip()
        if not route:
            raise ValueError("dailyhot source is missing a route.")
        return NewsSource(
            source_id=token,
            display_name=f"DailyHot/{route}",
            source_type="dailyhot",
            endpoint=build_dailyhot_url(dailyhot_base_url, route),
            category="",
        )

    if token.startswith("rss:"):
        url = token.split(":", 1)[1].strip()
        if not url:
            raise ValueError("rss source is missing a URL.")
        return NewsSource(
            source_id=token,
            display_name=url,
            source_type="rss",
            endpoint=url,
            category="",
        )

    if token.startswith(("http://", "https://")):
        return NewsSource(
            source_id=token,
            display_name=token,
            source_type="rss",
            endpoint=token,
            category="",
        )

    raise ValueError(f"Unsupported news source token: {token}")


# ---------------------------------------------------------------------------
# 主配置解析入口
# ---------------------------------------------------------------------------

def _cfg(raw_config: Mapping[str, Any], cn_key: str, default: Any = "") -> Any:
    """读取中文字段，若为空则回退到旧英文字段名。"""
    value = raw_config.get(cn_key)
    if value is not None:
        return value
    old_key = _FIELD_COMPAT.get(cn_key)
    if old_key:
        return raw_config.get(old_key, default)
    return default


def news_config_from_mapping(raw_config: Mapping[str, Any]) -> NewsConfig:
    """将 AstrBot 传入的原始 dict 配置解析为 NewsConfig。"""
    dailyhot_base_url = (
        str(_cfg(raw_config, "每日热榜地址") or "").strip() or DEFAULT_DAILYHOT_BASE_URL
    )
    custom_registry = parse_custom_sources(_cfg(raw_config, "自定义源"), dailyhot_base_url)
    source_tokens = coerce_source_tokens(_cfg(raw_config, "新闻源"))

    legacy_rss_url = str(_cfg(raw_config, "旧版RSS地址") or "").strip()
    if not source_tokens and legacy_rss_url and legacy_rss_url != LEGACY_GOOGLE_RSS_URL:
        source_tokens = [legacy_rss_url]

    if not source_tokens:
        source_tokens = list(DEFAULT_SOURCE_IDS)

    sources_list: list[NewsSource] = []
    for token in source_tokens:
        try:
            sources_list.append(resolve_source_token(token, dailyhot_base_url, custom_registry))
        except ValueError as exc:
            _logger.warning("跳过无效新闻源 token %r: %s", token, exc)
    sources = tuple(sources_list)

    # AI 摘要配置
    enable_ai_summary = coerce_bool(_cfg(raw_config, "启用AI摘要", False), False)
    ai_summary_prompt = str(
        _cfg(raw_config, "AI摘要提示词", DEFAULT_AI_SUMMARY_PROMPT) or DEFAULT_AI_SUMMARY_PROMPT
    )

    # Redis 配置
    redis_url = str(_cfg(raw_config, "Redis地址", "") or "").strip()

    return NewsConfig(
        sources=sources,
        max_items=coerce_int(_cfg(raw_config, "最大条数"), DEFAULT_MAX_ITEMS),
        request_timeout_seconds=coerce_int(_cfg(raw_config, "请求超时"), DEFAULT_TIMEOUT_SECONDS),
        enable_fallback_commands=coerce_bool(_cfg(raw_config, "启用命令", True), True),
        cache_ttl_seconds=coerce_int(_cfg(raw_config, "缓存有效期"), DEFAULT_CACHE_TTL_SECONDS),
        enable_ai_summary=enable_ai_summary,
        ai_summary_prompt=ai_summary_prompt,
        redis_url=redis_url,
    )
