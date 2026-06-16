"""tests/test_history.py — 去重历史模块单元测试。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from daily_news_core.history import NewsHistory, _MAX_LINKS, _TTL_DAYS
from daily_news_core.models import NewsHeadline


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_history(tmp_path: Path) -> NewsHistory:
    """创建临时目录下的 NewsHistory 实例。"""
    return NewsHistory(tmp_path)


@pytest.fixture
def sample_items() -> list[NewsHeadline]:
    """返回示例新闻条目。"""
    return [
        NewsHeadline(title="新闻1", link="https://example.com/1"),
        NewsHeadline(title="新闻2", link="https://example.com/2"),
        NewsHeadline(title="新闻3", link="https://example.com/3"),
    ]


# ---------------------------------------------------------------------------
# 基本功能测试
# ---------------------------------------------------------------------------


class TestNewsHistoryBasic:
    def test_init_creates_directory(self, tmp_path: Path):
        data_dir = tmp_path / "new_dir"
        history = NewsHistory(data_dir)
        assert data_dir.exists()

    def test_is_new_for_unknown_link(self, tmp_history: NewsHistory):
        assert tmp_history.is_new("https://example.com/new") is True

    def test_is_new_for_empty_link(self, tmp_history: NewsHistory):
        assert tmp_history.is_new("") is False
        assert tmp_history.is_new(None) is False

    def test_record_snapshot_marks_links(self, tmp_history: NewsHistory, sample_items):
        tmp_history.record_snapshot(sample_items)
        assert tmp_history.is_new("https://example.com/1") is False
        assert tmp_history.is_new("https://example.com/2") is False
        assert tmp_history.is_new("https://example.com/new") is True

    def test_persistence(self, tmp_path: Path, sample_items):
        # 写入
        history1 = NewsHistory(tmp_path)
        history1.record_snapshot(sample_items)

        # 重新加载
        history2 = NewsHistory(tmp_path)
        assert history2.is_new("https://example.com/1") is False
        assert history2.is_new("https://example.com/new") is True


# ---------------------------------------------------------------------------
# v1 格式迁移测试
# ---------------------------------------------------------------------------


class TestV1Migration:
    def test_migrate_v1_format(self, tmp_path: Path):
        # 写入 v1 格式（纯 URL 列表）
        v1_data = ["https://example.com/old1", "https://example.com/old2"]
        history_file = tmp_path / "seen_links.json"
        history_file.write_text(json.dumps(v1_data), encoding="utf-8")

        # 加载应该自动迁移
        history = NewsHistory(tmp_path)
        assert history.is_new("https://example.com/old1") is False
        assert history.is_new("https://example.com/old2") is False

        # 验证已写回 v2 格式
        with history_file.open("r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["version"] == 2
        assert "https://example.com/old1" in saved["links"]


# ---------------------------------------------------------------------------
# TTL 清理测试
# ---------------------------------------------------------------------------


class TestTTLCleanup:
    def test_prune_removes_expired(self, tmp_path: Path):
        history_file = tmp_path / "seen_links.json"
        now = time.time()
        expired_ts = now - (_TTL_DAYS + 1) * 86400  # 超过 TTL

        # 写入过期数据
        data = {
            "version": 2,
            "links": {
                "https://example.com/expired": expired_ts,
                "https://example.com/valid": now,
            },
        }
        history_file.write_text(json.dumps(data), encoding="utf-8")

        # 加载后触发清理
        history = NewsHistory(tmp_path)
        history.record_snapshot([])  # 触发 _prune

        assert history.is_new("https://example.com/expired") is True  # 已过期
        assert history.is_new("https://example.com/valid") is False  # 仍有效

    def test_prune_respects_max_links(self, tmp_path: Path):
        history = NewsHistory(tmp_path)

        # 写入超过上限的条目
        items = [
            NewsHeadline(title=f"新闻{i}", link=f"https://example.com/{i}")
            for i in range(_MAX_LINKS + 100)
        ]
        history.record_snapshot(items)

        # 验证条目数不超过上限
        assert len(history._seen) <= _MAX_LINKS


# ---------------------------------------------------------------------------
# 边界情况测试
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_corrupted_json(self, tmp_path: Path):
        history_file = tmp_path / "seen_links.json"
        history_file.write_text("这不是有效的 JSON", encoding="utf-8")

        # 应该从空白状态开始，不崩溃
        history = NewsHistory(tmp_path)
        assert history.is_new("https://example.com/new") is True

    def test_empty_snapshot(self, tmp_history: NewsHistory):
        # 空快照不应崩溃
        tmp_history.record_snapshot([])
        assert tmp_history.is_new("https://example.com/new") is True

    def test_duplicate_links_in_snapshot(self, tmp_history: NewsHistory):
        items = [
            NewsHeadline(title="重复1", link="https://example.com/dup"),
            NewsHeadline(title="重复2", link="https://example.com/dup"),
        ]
        tmp_history.record_snapshot(items)
        assert tmp_history.is_new("https://example.com/dup") is False

    def test_items_without_link(self, tmp_history: NewsHistory):
        items = [
            NewsHeadline(title="无链接", link=""),
            NewsHeadline(title="有链接", link="https://example.com/1"),
        ]
        tmp_history.record_snapshot(items)
        assert tmp_history.is_new("https://example.com/1") is False
        # 空链接不应被记录
        assert tmp_history.is_new("") is False
