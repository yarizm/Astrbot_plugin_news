"""tests/test_client.py — 新闻客户端模块单元测试（mock aiohttp）。"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily_news_core.client import NewsFeedClient, _CacheEntry, _SourceHealth
from daily_news_core.models import (
    NewsConfig,
    NewsFetchError,
    NewsHeadline,
    NewsSource,
    NewsSourceResult,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_source() -> NewsSource:
    return NewsSource(
        source_id="test-source",
        display_name="测试源",
        source_type="rss",
        endpoint="https://example.com/feed",
        category="tech",
        suggested_ttl=600,
    )


@pytest.fixture
def config_with_sources(sample_source) -> NewsConfig:
    return NewsConfig(
        sources=(sample_source,),
        max_items=5,
        request_timeout_seconds=10,
        cache_ttl_seconds=900,
    )


@pytest.fixture
def client(config_with_sources) -> NewsFeedClient:
    return NewsFeedClient(config_with_sources)


@pytest.fixture
def rss_payload() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Test Title</title>
      <link>https://example.com/1</link>
      <description>Test description</description>
    </item>
  </channel>
</rss>"""


# ---------------------------------------------------------------------------
# _CacheEntry 测试
# ---------------------------------------------------------------------------


class TestCacheEntry:
    def test_creation(self):
        result = NewsSourceResult(feed_title="test", items=())
        entry = _CacheEntry(result=result, fetched_at=100.0, ttl=600)
        assert entry.result is result
        assert entry.fetched_at == 100.0
        assert entry.ttl == 600


# ---------------------------------------------------------------------------
# _SourceHealth 测试
# ---------------------------------------------------------------------------


class TestSourceHealth:
    def test_defaults(self):
        health = _SourceHealth()
        assert health.consecutive_failures == 0
        assert health.last_failure_time == 0.0


# ---------------------------------------------------------------------------
# NewsFeedClient 初始化测试
# ---------------------------------------------------------------------------


class TestClientInit:
    def test_init(self, config_with_sources):
        client = NewsFeedClient(config_with_sources)
        assert client.config is config_with_sources
        assert client._session is None
        assert client._cache_backend is not None
        assert client._source_health == {}


# ---------------------------------------------------------------------------
# 源健康检查测试
# ---------------------------------------------------------------------------


class TestSourceHealthCheck:
    def test_healthy_when_no_history(self, client, sample_source):
        assert client._is_source_healthy(sample_source.source_id) is True

    def test_healthy_below_threshold(self, client, sample_source):
        client._source_health[sample_source.source_id] = _SourceHealth(
            consecutive_failures=2,
            last_failure_time=time.monotonic(),
        )
        assert client._is_source_healthy(sample_source.source_id) is True

    def test_unhealthy_above_threshold(self, client, sample_source):
        client._source_health[sample_source.source_id] = _SourceHealth(
            consecutive_failures=3,
            last_failure_time=time.monotonic(),
        )
        assert client._is_source_healthy(sample_source.source_id) is False

    def test_recovery_after_timeout(self, client, sample_source):
        client._source_health[sample_source.source_id] = _SourceHealth(
            consecutive_failures=3,
            last_failure_time=time.monotonic() - 2000,  # 超过恢复时间
        )
        assert client._is_source_healthy(sample_source.source_id) is True

    def test_record_failure(self, client, sample_source):
        client._record_source_failure(sample_source.source_id)
        health = client._source_health[sample_source.source_id]
        assert health.consecutive_failures == 1

    def test_record_success_resets(self, client, sample_source):
        client._source_health[sample_source.source_id] = _SourceHealth(
            consecutive_failures=3,
        )
        client._record_source_success(sample_source.source_id)
        assert client._source_health[sample_source.source_id].consecutive_failures == 0


# ---------------------------------------------------------------------------
# 格式化异常测试
# ---------------------------------------------------------------------------


class TestFormatException:
    def test_timeout(self, client):
        exc = asyncio.TimeoutError()
        assert client._format_exception(exc) == "请求超时"

    def test_generic(self, client):
        exc = ValueError("test error")
        assert client._format_exception(exc) == "test error"


# ---------------------------------------------------------------------------
# 合并去重测试
# ---------------------------------------------------------------------------


class TestMergeResults:
    def test_merge_basic(self, client):
        source = NewsSource(
            source_id="test", display_name="Test", source_type="rss",
            endpoint="https://example.com",
        )
        result = NewsSourceResult(
            feed_title="Test",
            items=(
                NewsHeadline(title="A", link="https://a.com"),
                NewsHeadline(title="B", link="https://b.com"),
            ),
        )
        merged, titles = client._merge_results([(source, result)], 10)
        assert len(merged) == 2
        assert "Test" in titles

    def test_merge_dedup(self, client):
        source = NewsSource(
            source_id="test", display_name="Test", source_type="rss",
            endpoint="https://example.com",
        )
        result = NewsSourceResult(
            feed_title="Test",
            items=(
                NewsHeadline(title="Same", link="https://same.com"),
                NewsHeadline(title="Same", link="https://same.com"),
            ),
        )
        merged, _ = client._merge_results([(source, result)], 10)
        assert len(merged) == 1

    def test_merge_limit(self, client):
        source = NewsSource(
            source_id="test", display_name="Test", source_type="rss",
            endpoint="https://example.com",
        )
        items = tuple(
            NewsHeadline(title=f"Item {i}", link=f"https://example.com/{i}")
            for i in range(10)
        )
        result = NewsSourceResult(feed_title="Test", items=items)
        merged, _ = client._merge_results([(source, result)], 3)
        assert len(merged) == 3


# ---------------------------------------------------------------------------
# 获取源信息测试
# ---------------------------------------------------------------------------


class TestGetSourcesInfo:
    def test_get_all_sources_info(self, client, sample_source):
        info = client.get_all_sources_info()
        assert len(info) == 1
        assert info[0]["id"] == sample_source.source_id
        assert info[0]["name"] == sample_source.display_name
        assert info[0]["type"] == sample_source.source_type
        assert info[0]["category"] == "科技"


# ---------------------------------------------------------------------------
# 缓存测试
# ---------------------------------------------------------------------------


class TestCache:
    def test_cache_hit(self, client, sample_source, rss_payload):
        # 模拟缓存命中
        from daily_news_core.cache_backend import CacheEntry
        result = NewsSourceResult(
            feed_title="Cached",
            items=(NewsHeadline(title="Cached", link="https://cached.com"),),
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            client._cache_backend.set(
                sample_source.source_id,
                CacheEntry(data=result, fetched_at=time.time(), ttl=600),
            )
        )

        # 应该返回缓存，不需要网络请求
        src, cached_result, error = loop.run_until_complete(
            client._fetch_single_source(sample_source, 5)
        )
        loop.close()

        assert cached_result is result
        assert error is None

    def test_cache_miss_expired(self, client, sample_source, rss_payload):
        # MemoryCache 会自动过期，所以不设置缓存即为 miss
        with patch.object(client, "_read", new_callable=AsyncMock) as mock_read:
            mock_read.return_value = rss_payload
            loop = asyncio.new_event_loop()
            src, cached_result, error = loop.run_until_complete(
                client._fetch_single_source(sample_source, 5)
            )
            loop.close()
            mock_read.assert_called_once()


# ---------------------------------------------------------------------------
# 单源抓取测试
# ---------------------------------------------------------------------------


class TestFetchSingleSource:
    def test_unhealthy_source_skipped(self, client, sample_source):
        # 标记为不健康
        client._source_health[sample_source.source_id] = _SourceHealth(
            consecutive_failures=5,
            last_failure_time=time.monotonic(),
        )

        loop = asyncio.new_event_loop()
        src, result, error = loop.run_until_complete(
            client._fetch_single_source(sample_source, 5)
        )
        loop.close()

        assert result is None
        assert "已被临时跳过" in error

    def test_fetch_success(self, client, sample_source, rss_payload):
        with patch.object(client, "_read", new_callable=AsyncMock) as mock_read:
            mock_read.return_value = rss_payload
            loop = asyncio.new_event_loop()
            src, result, error = loop.run_until_complete(
                client._fetch_single_source(sample_source, 5)
            )
            loop.close()

            assert result is not None
            assert len(result.items) > 0
            assert error is None
            # 验证缓存已写入
            loop2 = asyncio.new_event_loop()
            cached = loop2.run_until_complete(
                client._cache_backend.get(sample_source.source_id)
            )
            loop2.close()
            assert cached is not None

    def test_fetch_failure(self, client, sample_source):
        with patch.object(client, "_read", new_callable=AsyncMock) as mock_read:
            mock_read.side_effect = Exception("Network error")
            loop = asyncio.new_event_loop()
            src, result, error = loop.run_until_complete(
                client._fetch_single_source(sample_source, 5)
            )
            loop.close()

            assert result is None
            assert "Network error" in error
            # 验证健康状态已记录
            assert client._source_health[sample_source.source_id].consecutive_failures == 1


# ---------------------------------------------------------------------------
# 主入口测试
# ---------------------------------------------------------------------------


class TestFetchHeadlines:
    def test_no_sources_raises(self):
        config = NewsConfig(sources=())
        client = NewsFeedClient(config)
        with pytest.raises(NewsFetchError):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(client.fetch_headlines())
            loop.close()

    def test_fetch_headlines_success(self, client, sample_source, rss_payload):
        with patch.object(client, "_read", new_callable=AsyncMock) as mock_read:
            mock_read.return_value = rss_payload
            loop = asyncio.new_event_loop()
            title, items = loop.run_until_complete(client.fetch_headlines(limit=5))
            loop.close()

            # RSS feed title is "Test Feed", so it should be in the title
            assert len(items) > 0
            assert title  # title should not be empty


# ---------------------------------------------------------------------------
# 关闭测试
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_without_session(self, client):
        # 不应该崩溃
        loop = asyncio.new_event_loop()
        loop.run_until_complete(client.close())
        loop.close()
        assert client._session is None
