"""tests/test_scheduler.py — 定时调度器模块单元测试。"""
from __future__ import annotations

import json
import time
from datetime import time as dt_time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daily_news_core.scheduler import NewsScheduler, SubscriptionRecord


# ---------------------------------------------------------------------------
# SubscriptionRecord 测试
# ---------------------------------------------------------------------------


class TestSubscriptionRecord:
    def test_creation(self):
        record = SubscriptionRecord(
            session_id="group_123",
            push_time=dt_time(hour=8, minute=0),
        )
        assert record.session_id == "group_123"
        assert record.push_time == dt_time(hour=8, minute=0)
        assert record.category is None
        assert record.limit == 5

    def test_to_dict(self):
        record = SubscriptionRecord(
            session_id="group_123",
            push_time=dt_time(hour=8, minute=30),
            category="tech",
            limit=10,
        )
        d = record.to_dict()
        assert d["session_id"] == "group_123"
        assert d["push_time"] == "08:30"
        assert d["category"] == "tech"
        assert d["limit"] == 10

    def test_from_dict(self):
        d = {
            "session_id": "group_456",
            "push_time": "09:00",
            "category": "news",
            "limit": 8,
            "created_at": 1234567890.0,
        }
        record = SubscriptionRecord.from_dict(d)
        assert record.session_id == "group_456"
        assert record.push_time == dt_time(hour=9, minute=0)
        assert record.category == "news"
        assert record.limit == 8
        assert record.created_at == 1234567890.0

    def test_from_dict_invalid_time(self):
        d = {"session_id": "test", "push_time": "invalid"}
        record = SubscriptionRecord.from_dict(d)
        assert record.push_time == dt_time(hour=8, minute=0)  # 默认值

    def test_roundtrip(self):
        original = SubscriptionRecord(
            session_id="group_789",
            push_time=dt_time(hour=7, minute=30),
            category="tech",
            limit=5,
        )
        restored = SubscriptionRecord.from_dict(original.to_dict())
        assert restored.session_id == original.session_id
        assert restored.push_time == original.push_time
        assert restored.category == original.category
        assert restored.limit == original.limit


# ---------------------------------------------------------------------------
# NewsScheduler 基本功能测试
# ---------------------------------------------------------------------------


class TestNewsSchedulerBasic:
    @pytest.fixture
    def mock_callback(self):
        return AsyncMock()

    @pytest.fixture
    def scheduler(self, tmp_path: Path, mock_callback):
        return NewsScheduler(tmp_path, mock_callback)

    def test_initially_empty(self, scheduler):
        assert scheduler.subscription_count == 0
        assert scheduler.get_all_subscriptions() == []

    def test_subscribe(self, scheduler):
        record = SubscriptionRecord(
            session_id="group_1",
            push_time=dt_time(hour=8, minute=0),
        )
        scheduler.subscribe(record)
        assert scheduler.subscription_count == 1
        assert scheduler.get_subscription("group_1") is record

    def test_subscribe_updates_existing(self, scheduler):
        record1 = SubscriptionRecord(session_id="group_1", push_time=dt_time(hour=8))
        record2 = SubscriptionRecord(session_id="group_1", push_time=dt_time(hour=9))
        scheduler.subscribe(record1)
        scheduler.subscribe(record2)
        assert scheduler.subscription_count == 1
        assert scheduler.get_subscription("group_1").push_time == dt_time(hour=9)

    def test_unsubscribe_existing(self, scheduler):
        record = SubscriptionRecord(session_id="group_1", push_time=dt_time(hour=8))
        scheduler.subscribe(record)
        assert scheduler.unsubscribe("group_1") is True
        assert scheduler.subscription_count == 0

    def test_unsubscribe_nonexistent(self, scheduler):
        assert scheduler.unsubscribe("nonexistent") is False

    def test_get_nonexistent(self, scheduler):
        assert scheduler.get_subscription("nonexistent") is None


# ---------------------------------------------------------------------------
# 持久化测试
# ---------------------------------------------------------------------------


class TestSchedulerPersistence:
    @pytest.fixture
    def mock_callback(self):
        return AsyncMock()

    def test_persistence(self, tmp_path: Path, mock_callback):
        # 创建并写入订阅
        scheduler1 = NewsScheduler(tmp_path, mock_callback)
        record = SubscriptionRecord(
            session_id="group_1",
            push_time=dt_time(hour=8, minute=30),
            category="tech",
            limit=10,
        )
        scheduler1.subscribe(record)

        # 重新加载
        scheduler2 = NewsScheduler(tmp_path, mock_callback)
        assert scheduler2.subscription_count == 1
        loaded = scheduler2.get_subscription("group_1")
        assert loaded is not None
        assert loaded.push_time == dt_time(hour=8, minute=30)
        assert loaded.category == "tech"

    def test_corrupted_file(self, tmp_path: Path, mock_callback):
        # 写入损坏的 JSON
        subs_file = tmp_path / "subscriptions.json"
        subs_file.write_text("invalid json", encoding="utf-8")

        # 应该从空白状态开始，不崩溃
        scheduler = NewsScheduler(tmp_path, mock_callback)
        assert scheduler.subscription_count == 0


# ---------------------------------------------------------------------------
# 边界情况测试
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.fixture
    def mock_callback(self):
        return AsyncMock()

    def test_multiple_subscriptions(self, tmp_path: Path, mock_callback):
        scheduler = NewsScheduler(tmp_path, mock_callback)
        for i in range(10):
            record = SubscriptionRecord(
                session_id=f"group_{i}",
                push_time=dt_time(hour=8, minute=i),
            )
            scheduler.subscribe(record)
        assert scheduler.subscription_count == 10

    def test_unsubscribe_middle(self, tmp_path: Path, mock_callback):
        scheduler = NewsScheduler(tmp_path, mock_callback)
        for i in range(3):
            scheduler.subscribe(
                SubscriptionRecord(session_id=f"group_{i}", push_time=dt_time(hour=8))
            )
        scheduler.unsubscribe("group_1")
        assert scheduler.subscription_count == 2
        assert scheduler.get_subscription("group_0") is not None
        assert scheduler.get_subscription("group_2") is not None
