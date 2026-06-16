"""tests/test_config.py — 配置解析模块单元测试。"""
from __future__ import annotations

import pytest

from daily_news_core.config import (
    build_dailyhot_url,
    coerce_bool,
    coerce_int,
    coerce_source_tokens,
    news_config_from_mapping,
    resolve_source_token,
)
from daily_news_core.models import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_DAILYHOT_BASE_URL,
    DEFAULT_MAX_ITEMS,
    DEFAULT_TIMEOUT_SECONDS,
)


# ---------------------------------------------------------------------------
# coerce_bool 测试
# ---------------------------------------------------------------------------


class TestCoerceBool:
    @pytest.mark.parametrize("value", [True, 1, "true", "True", "TRUE", "yes", "on", "1"])
    def test_truthy(self, value):
        assert coerce_bool(value, False) is True

    @pytest.mark.parametrize("value", [False, 0, "false", "False", "no", "off", "0"])
    def test_falsy(self, value):
        assert coerce_bool(value, True) is False

    def test_none_returns_default(self):
        assert coerce_bool(None, True) is True
        assert coerce_bool(None, False) is False

    @pytest.mark.parametrize("value", ["invalid", "maybe", 42, 3.14])
    def test_invalid_returns_default(self, value):
        assert coerce_bool(value, True) is True
        assert coerce_bool(value, False) is False


# ---------------------------------------------------------------------------
# coerce_int 测试
# ---------------------------------------------------------------------------


class TestCoerceInt:
    def test_valid_int(self):
        assert coerce_int(5, 0) == 5
        assert coerce_int("10", 0) == 10
        assert coerce_int(0, 10) == 0

    def test_negative_returns_default(self):
        assert coerce_int(-1, 10) == 10
        assert coerce_int("-5", 10) == 10

    def test_invalid_returns_default(self):
        assert coerce_int(None, 10) == 10
        assert coerce_int("abc", 10) == 10
        assert coerce_int("", 10) == 10


# ---------------------------------------------------------------------------
# coerce_source_tokens 测试
# ---------------------------------------------------------------------------


class TestCoerceSourceTokens:
    def test_none_returns_empty(self):
        assert coerce_source_tokens(None) == []

    def test_string_split_by_comma(self):
        result = coerce_source_tokens("a,b,c")
        assert result == ["a", "b", "c"]

    def test_string_split_by_newline(self):
        result = coerce_source_tokens("a\nb\nc")
        assert result == ["a", "b", "c"]

    def test_list_input(self):
        result = coerce_source_tokens(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_strips_whitespace(self):
        result = coerce_source_tokens(" a , b , c ")
        assert result == ["a", "b", "c"]

    def test_filters_empty(self):
        result = coerce_source_tokens("a,,b,,c")
        assert result == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# build_dailyhot_url 测试
# ---------------------------------------------------------------------------


class TestBuildDailyhotUrl:
    def test_normal(self):
        assert build_dailyhot_url("https://api.example.com", "zhihu") == "https://api.example.com/zhihu"

    def test_trailing_slash(self):
        assert build_dailyhot_url("https://api.example.com/", "zhihu") == "https://api.example.com/zhihu"

    def test_leading_slash(self):
        assert build_dailyhot_url("https://api.example.com", "/zhihu") == "https://api.example.com/zhihu"


# ---------------------------------------------------------------------------
# resolve_source_token 测试
# ---------------------------------------------------------------------------


class TestResolveSourceToken:
    def test_builtin_source(self):
        source = resolve_source_token("36kr-newsflash", DEFAULT_DAILYHOT_BASE_URL)
        assert source.source_id == "36kr-newsflash"
        assert source.display_name == "36氪快讯"
        assert source.source_type == "rss"
        assert source.suggested_ttl > 0

    def test_builtin_dailyhot_source(self):
        source = resolve_source_token("douyin", DEFAULT_DAILYHOT_BASE_URL)
        assert source.source_id == "douyin"
        assert source.source_type == "dailyhot"
        assert "douyin" in source.endpoint

    def test_dailyhot_prefix(self):
        source = resolve_source_token("dailyhot:zhihu", "https://api.example.com")
        assert source.source_id == "dailyhot:zhihu"
        assert source.source_type == "dailyhot"
        assert "zhihu" in source.endpoint

    def test_rss_prefix(self):
        source = resolve_source_token("rss:https://example.com/feed", DEFAULT_DAILYHOT_BASE_URL)
        assert source.source_id == "rss:https://example.com/feed"
        assert source.source_type == "rss"
        assert source.endpoint == "https://example.com/feed"

    def test_raw_url(self):
        source = resolve_source_token("https://example.com/feed", DEFAULT_DAILYHOT_BASE_URL)
        assert source.source_type == "rss"
        assert source.endpoint == "https://example.com/feed"

    def test_unknown_token_raises(self):
        with pytest.raises(ValueError):
            resolve_source_token("unknown_source", DEFAULT_DAILYHOT_BASE_URL)


# ---------------------------------------------------------------------------
# news_config_from_mapping 测试
# ---------------------------------------------------------------------------


class TestNewsConfigFromMapping:
    def test_default_config(self):
        config = news_config_from_mapping({})
        assert len(config.sources) > 0
        assert config.max_items == DEFAULT_MAX_ITEMS
        assert config.request_timeout_seconds == DEFAULT_TIMEOUT_SECONDS
        assert config.cache_ttl_seconds == DEFAULT_CACHE_TTL_SECONDS

    def test_chinese_field_names(self):
        raw = {
            "新闻源": "ithome",
            "最大条数": "10",
            "请求超时": "30",
        }
        config = news_config_from_mapping(raw)
        assert len(config.sources) == 1
        assert config.sources[0].source_id == "ithome"
        assert config.max_items == 10
        assert config.request_timeout_seconds == 30

    def test_english_field_names(self):
        raw = {
            "source_ids": "ithome,cnbeta",
            "max_items": "8",
        }
        config = news_config_from_mapping(raw)
        assert len(config.sources) == 2
        assert config.max_items == 8

    def test_legacy_rss_url_fallback(self):
        raw = {"旧版RSS地址": "https://example.com/rss"}
        config = news_config_from_mapping(raw)
        assert any(s.endpoint == "https://example.com/rss" for s in config.sources)

    def test_empty_source_uses_default(self):
        raw = {"新闻源": ""}
        config = news_config_from_mapping(raw)
        assert len(config.sources) > 0  # 应使用默认源

    def test_invalid_source_skipped(self):
        raw = {"新闻源": "ithome,invalid_source,cnbeta"}
        config = news_config_from_mapping(raw)
        # invalid_source 应被跳过
        source_ids = [s.source_id for s in config.sources]
        assert "ithome" in source_ids
        assert "cnbeta" in source_ids
        assert "invalid_source" not in source_ids
