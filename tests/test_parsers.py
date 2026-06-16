"""tests/test_parsers.py — 解析器模块单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from daily_news_core.models import NewsSource
from daily_news_core.parsers import (
    clean_text,
    truncate_summary,
    parse_dailyhot_source,
    parse_feed_source,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def rss_source() -> NewsSource:
    return NewsSource(
        source_id="test-rss",
        display_name="测试RSS源",
        source_type="rss",
        endpoint="https://example.com/feed",
    )


@pytest.fixture
def dailyhot_source() -> NewsSource:
    return NewsSource(
        source_id="test-dailyhot",
        display_name="测试DailyHot源",
        source_type="dailyhot",
        endpoint="https://api.example.com/zhihu",
    )


# ---------------------------------------------------------------------------
# 工具函数测试
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_removes_html_tags(self):
        assert clean_text("<p>Hello</p>") == "Hello"

    def test_unescapes_entities(self):
        result = clean_text("&amp;&lt;&gt;")
        assert result == "&<>"

    def test_collapses_whitespace(self):
        assert clean_text("  hello   world  ") == "hello world"

    def test_empty_string(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""


class TestTruncateSummary:
    def test_short_text_unchanged(self):
        assert truncate_summary("短文本", 10) == "短文本"

    def test_long_text_truncated(self):
        result = truncate_summary("这是一段很长的文本内容", 10)
        assert len(result) <= 10
        assert result.endswith("…")

    def test_empty_text(self):
        assert truncate_summary("", 10) == ""
        assert truncate_summary(None, 10) is None


# ---------------------------------------------------------------------------
# RSS 解析测试
# ---------------------------------------------------------------------------


class TestParseRssFeed:
    def test_parse_rss_feed(self, rss_source):
        payload = (FIXTURES_DIR / "rss_feed.xml").read_bytes()
        result = parse_feed_source(rss_source, payload, limit=10)

        assert result.feed_title == "测试 RSS 源"
        assert len(result.items) == 3
        assert result.items[0].title == "第一条新闻标题"
        assert result.items[0].link == "https://example.com/news/1"
        assert "摘要" in result.items[0].summary

    def test_rss_limit(self, rss_source):
        payload = (FIXTURES_DIR / "rss_feed.xml").read_bytes()
        result = parse_feed_source(rss_source, payload, limit=2)
        assert len(result.items) == 2


# ---------------------------------------------------------------------------
# Atom 解析测试
# ---------------------------------------------------------------------------


class TestParseAtomFeed:
    def test_parse_atom_feed(self, rss_source):
        payload = (FIXTURES_DIR / "atom_feed.xml").read_bytes()
        result = parse_feed_source(rss_source, payload, limit=10)

        assert result.feed_title == "测试 Atom 源"
        assert len(result.items) == 2
        assert result.items[0].title == "Atom 第一条新闻"
        assert result.items[0].link == "https://example.com/atom/1"


# ---------------------------------------------------------------------------
# DailyHot 解析测试
# ---------------------------------------------------------------------------


class TestParseDailyhotSource:
    def test_parse_dailyhot(self, dailyhot_source):
        payload = (FIXTURES_DIR / "dailyhot_zhihu.json").read_bytes()
        result = parse_dailyhot_source(dailyhot_source, payload, limit=10)

        assert len(result.items) == 3
        assert "如何看待" in result.items[0].title
        assert result.items[0].link == "https://www.zhihu.com/question/123456"

    def test_dailyhot_limit(self, dailyhot_source):
        payload = (FIXTURES_DIR / "dailyhot_zhihu.json").read_bytes()
        result = parse_dailyhot_source(dailyhot_source, payload, limit=2)
        assert len(result.items) == 2

    def test_dailyhot_missing_title_skipped(self, dailyhot_source):
        data = {
            "code": 200,
            "data": [
                {"title": "有效标题", "url": "https://example.com/1"},
                {"url": "https://example.com/2"},  # 缺少 title
            ],
        }
        payload = json.dumps(data).encode()
        result = parse_dailyhot_source(dailyhot_source, payload, limit=10)
        assert len(result.items) == 1


# ---------------------------------------------------------------------------
# 边界情况测试
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_invalid_xml_raises(self, rss_source):
        with pytest.raises(Exception):
            parse_feed_source(rss_source, b"not xml", limit=10)

    def test_invalid_json_raises(self, dailyhot_source):
        with pytest.raises(Exception):
            parse_dailyhot_source(dailyhot_source, b"not json", limit=10)

    def test_empty_data(self, dailyhot_source):
        data = {"code": 200, "data": []}
        payload = json.dumps(data).encode()
        result = parse_dailyhot_source(dailyhot_source, payload, limit=10)
        assert len(result.items) == 0
