"""定时推送调度器：管理订阅记录、持久化、定时触发推送。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, Awaitable, Callable

_logger = logging.getLogger(__name__)


@dataclass
class SubscriptionRecord:
    """单条订阅记录。"""

    session_id: str  # 会话唯一 ID（群号 / 私聊 ID）
    push_time: dt_time  # 推送时间，如 08:00
    category: str | None = None  # 可选：指定分类，None 表示全部
    limit: int = 5  # 推送条数上限
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容字典。"""
        return {
            "session_id": self.session_id,
            "push_time": self.push_time.strftime("%H:%M"),
            "category": self.category,
            "limit": self.limit,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubscriptionRecord:
        """从字典反序列化。"""
        push_time_str = data.get("push_time", "08:00")
        try:
            hour, minute = map(int, push_time_str.split(":"))
            push_time = dt_time(hour=hour, minute=minute)
        except (ValueError, AttributeError):
            push_time = dt_time(hour=8, minute=0)
        return cls(
            session_id=data.get("session_id", ""),
            push_time=push_time,
            category=data.get("category"),
            limit=data.get("limit", 5),
            created_at=data.get("created_at", time.time()),
        )


class NewsScheduler:
    """定时推送调度器。

    生命周期
    --------
    __init__ → load()       从 JSON 文件加载订阅记录
    subscribe()             添加/更新订阅
    unsubscribe()           删除订阅
    start()                 启动后台定时任务
    stop()                  停止后台任务并持久化
    """

    def __init__(
        self,
        data_dir: str | Path,
        push_callback: Callable[[SubscriptionRecord], Awaitable[None]],
    ) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "subscriptions.json"
        self._push_callback = push_callback
        self._subscriptions: dict[str, SubscriptionRecord] = {}
        self._task: asyncio.Task[None] | None = None
        self._load()

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def subscribe(self, record: SubscriptionRecord) -> None:
        """添加或更新订阅（按 session_id 去重）。"""
        self._subscriptions[record.session_id] = record
        self._persist()
        _logger.info("订阅已更新: %s → %s", record.session_id, record.push_time.strftime("%H:%M"))

    def unsubscribe(self, session_id: str) -> bool:
        """删除订阅，返回是否存在该订阅。"""
        removed = self._subscriptions.pop(session_id, None)
        if removed is not None:
            self._persist()
            _logger.info("订阅已删除: %s", session_id)
            return True
        return False

    def get_subscription(self, session_id: str) -> SubscriptionRecord | None:
        """查询指定会话的订阅。"""
        return self._subscriptions.get(session_id)

    def get_all_subscriptions(self) -> list[SubscriptionRecord]:
        """返回所有订阅记录。"""
        return list(self._subscriptions.values())

    @property
    def subscription_count(self) -> int:
        """当前订阅总数。"""
        return len(self._subscriptions)

    # ── 调度控制 ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """启动后台定时任务。"""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._tick_loop())
        _logger.info("定时推送调度器已启动")

    async def stop(self) -> None:
        """停止后台任务并持久化。"""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._persist()
        _logger.info("定时推送调度器已停止")

    # ── 内部实现 ──────────────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        """主循环：每分钟检查一次，触发到期推送。"""
        while True:
            try:
                await self._check_and_push()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("定时推送检查异常")
            await asyncio.sleep(60)

    async def _check_and_push(self) -> None:
        """检查当前时间是否匹配任何订阅的推送时间。"""
        now = datetime.now()
        current_time = now.time().replace(second=0, microsecond=0)
        today = now.date()
        for record in list(self._subscriptions.values()):
            if record.push_time != current_time:
                continue
            # 每天每个订阅只触发一次
            last_push = getattr(record, "_last_push_date", None)
            if last_push == today:
                continue
            record._last_push_date = today
            _logger.info("触发定时推送: %s", record.session_id)
            try:
                await self._push_callback(record)
            except Exception:
                _logger.exception("推送回调异常: %s", record.session_id)

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """从 JSON 文件加载订阅记录。"""
        if not self._file.exists():
            return
        try:
            with self._file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "session_id" in item:
                        record = SubscriptionRecord.from_dict(item)
                        if record.session_id:
                            self._subscriptions[record.session_id] = record
            _logger.info("加载了 %d 条订阅记录", len(self._subscriptions))
        except Exception:
            _logger.warning("订阅记录加载失败，从空白状态开始", exc_info=True)

    def _persist(self) -> None:
        """原子写入订阅记录。"""
        payload = [record.to_dict() for record in self._subscriptions.values()]
        tmp = self._file.with_suffix(".json.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp.replace(self._file)
        except OSError:
            _logger.warning("订阅记录保存失败", exc_info=True)
            tmp.unlink(missing_ok=True)
