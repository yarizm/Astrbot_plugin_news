"""tests/test_models.py — 数据模型单元测试。"""
from __future__ import annotations

import pytest

from daily_news_core.models import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_DAILYHOT_BASE_URL,
    DEFAULT_MAX_ITEMS,
    DEFAULT_SOURCE_IDS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_RETRIES,
    SOURCE_HEALTH_THRESHOLD,
    SOURCE_RECOVERY_SECONDS,
    NewsConfig,
    NewsFetchError,
    NewsHeadline,
    NewsSource,
    NewsSourceResult,
)


# ---------------------------------------------------------------------------
# 常量测试
# ---------------------------------------------------------------------------


class TestConstants:
    def test_default_source_ids_not_empty(self):
        assert len(DEFAULT_SOURCE_IDS) > 0

    def test_default_values_positive(self):
        assert DEFAULT_MAX_ITEMS > 0
        assert DEFAULT_TIMEOUT_SECONDS > 0
        assert DEFAULT_CACHE_TTL_SECONDS > 0
        assert MAX_RETRIES >= 0
        assert SOURCE_HEALTH_THRESHOLD > 0
        assert SOURCE_RECOVERY_SECONDS > 0

    def test_dailyhot_base_url_valid(self):
        assert DEFAULT_DAILYHOT_BASE_URL.startswith("http")


# ---------------------------------------------------------------------------
# NewsSource 测试
# ---------------------------------------------------------------------------


class TestNewsSource:
    def test_creation(self):
        source = NewsSource(
            source_id="test",
            display_name="测试源",
            source_type="rss",
            endpoint="https://example.com/feed",
        )
        assert source.source_id == "test"
        assert source.display_name == "测试源"
        assert source.source_type == "rss"
        assert source.endpoint == "https://example.com/feed"
        assert source.description == ""
        assert source.category == ""
        assert source.suggested_ttl == 0

    def test_frozen(self):
        source = NewsSource(
            source_id="test",
            display_name="测试源",
            source_type="rss",
            endpoint="https://example.com/feed",
        )
        with pytest.raises(AttributeError):
            source.source_id = "changed"

    def test_with_category_and_ttl(self):
        source = NewsSource(
            source_id="test",
            display_name="测试源",
            source_type="dailyhot",
            endpoint="https://api.example.com/zhihu",
            category="tech",
            suggested_ttl=300,
        )
        assert source.category == "tech"
        assert source.suggested_ttl == 300


# ---------------------------------------------------------------------------
# NewsHeadline 测试
# ---------------------------------------------------------------------------


class TestNewsHeadline:
    def test_creation_minimal(self):
        headline = NewsHeadline(title="标题", link="https://example.com/1")
        assert headline.title == "标题"
        assert headline.link == "https://example.com/1"
        assert headline.published_at == ""
        assert headline.source == ""
        assert headline.summary == ""

    def test_creation_full(self):
        headline = NewsHeadline(
            title="完整标题",
            link="https://example.com/2",
            published_at="2026-06-16",
            source="测试源",
            summary="这是摘要",
        )
        assert headline.title == "完整标题"
        assert headline.published_at == "2026-06-16"
        assert headline.source == "测试源"
        assert headline.summary == "这是摘要"

    def test_frozen(self):
        headline = NewsHeadline(title="标题", link="https://example.com/1")
        with pytest.raises(AttributeError):
            headline.title = "修改"


# ---------------------------------------------------------------------------
# NewsSourceResult 测试
# ---------------------------------------------------------------------------


class TestNewsSourceResult:
    def test_creation(self):
        items = (
            NewsHeadline(title="标题1", link="https://example.com/1"),
            NewsHeadline(title="标题2", link="https://example.com/2"),
        )
        result = NewsSourceResult(feed_title="测试源", items=items)
        assert result.feed_title == "测试源"
        assert len(result.items) == 2

    def test_empty_items(self):
        result = NewsSourceResult(feed_title="空源", items=())
        assert len(result.items) == 0


# ---------------------------------------------------------------------------
# NewsConfig 测试
# ---------------------------------------------------------------------------


class TestNewsConfig:
    def test_defaults(self):
        config = NewsConfig(sources=())
        assert config.max_items == DEFAULT_MAX_ITEMS
        assert config.request_timeout_seconds == DEFAULT_TIMEOUT_SECONDS
        assert config.enable_fallback_commands is True
        assert config.cache_ttl_seconds == DEFAULT_CACHE_TTL_SECONDS

    def test_custom_values(self):
        config = NewsConfig(
            sources=(),
            max_items=10,
            request_timeout_seconds=30,
            enable_fallback_commands=False,
            cache_ttl_seconds=600,
        )
        assert config.max_items == 10
        assert config.request_timeout_seconds == 30
        assert config.enable_fallback_commands is False
        assert config.cache_ttl_seconds == 600


# ---------------------------------------------------------------------------
# NewsFetchError 测试
# ---------------------------------------------------------------------------


class TestNewsFetchError:
    def test_single_message(self):
        exc = NewsFetchError(["错误信息"])
        assert exc.messages == ["错误信息"]
        assert str(exc) == "错误信息"

    def test_multiple_messages(self):
        exc = NewsFetchError(["错误1", "错误2", "错误3"])
        assert len(exc.messages) == 3
        assert str(exc) == "错误1；错误2；错误3"

    def test_is_runtime_error(self):
        exc = NewsFetchError(["test"])
        assert isinstance(exc, RuntimeError)
