"""用户偏好存储：按 session_id 存储个性化配置。"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass
class UserPrefs:
    """单个用户的偏好配置。"""

    session_id: str
    preferred_sources: list[str] = field(default_factory=list)  # 空表示使用全局配置
    preferred_categories: list[str] = field(default_factory=list)
    push_time: str | None = None  # 格式：HH:MM
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容字典。"""
        return {
            "session_id": self.session_id,
            "preferred_sources": self.preferred_sources,
            "preferred_categories": self.preferred_categories,
            "push_time": self.push_time,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserPrefs:
        """从字典反序列化。"""
        return cls(
            session_id=data.get("session_id", ""),
            preferred_sources=data.get("preferred_sources", []),
            preferred_categories=data.get("preferred_categories", []),
            push_time=data.get("push_time"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


class UserPrefsStore:
    """用户偏好持久化存储。

    生命周期
    --------
    __init__ → _load()      从 JSON 文件加载
    get_prefs()             获取用户偏好（不存在则返回默认）
    update_prefs()          更新用户偏好
    reset_prefs()           重置为全局默认
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "user_prefs.json"
        self._prefs: dict[str, UserPrefs] = {}
        self._load()

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def get_prefs(self, session_id: str) -> UserPrefs:
        """获取用户偏好，不存在则返回默认值。"""
        if session_id not in self._prefs:
            return UserPrefs(session_id=session_id)
        return self._prefs[session_id]

    def update_prefs(self, prefs: UserPrefs) -> None:
        """更新用户偏好。"""
        prefs.updated_at = time.time()
        self._prefs[prefs.session_id] = prefs
        self._persist()
        _logger.info("用户偏好已更新: %s", prefs.session_id)

    def reset_prefs(self, session_id: str) -> bool:
        """重置用户偏好为全局默认，返回是否存在该用户。"""
        removed = self._prefs.pop(session_id, None)
        if removed is not None:
            self._persist()
            _logger.info("用户偏好已重置: %s", session_id)
            return True
        return False

    def get_all_prefs(self) -> list[UserPrefs]:
        """返回所有用户偏好。"""
        return list(self._prefs.values())

    @property
    def user_count(self) -> int:
        """当前用户数。"""
        return len(self._prefs)

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """从 JSON 文件加载用户偏好。"""
        if not self._file.exists():
            return
        try:
            with self._file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "session_id" in item:
                        prefs = UserPrefs.from_dict(item)
                        if prefs.session_id:
                            self._prefs[prefs.session_id] = prefs
            _logger.info("加载了 %d 条用户偏好", len(self._prefs))
        except Exception:
            _logger.warning("用户偏好加载失败，从空白状态开始", exc_info=True)

    def _persist(self) -> None:
        """原子写入用户偏好。"""
        payload = [prefs.to_dict() for prefs in self._prefs.values()]
        tmp = self._file.with_suffix(".json.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp.replace(self._file)
        except OSError:
            _logger.warning("用户偏好保存失败", exc_info=True)
            tmp.unlink(missing_ok=True)
