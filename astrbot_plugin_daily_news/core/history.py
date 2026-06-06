"""新闻历史持久化：JSON 文件存储已推送链接，用于去重。"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from .models import NewsHeadline

_logger = logging.getLogger(__name__)


class NewsHistory:
    """简单的 JSON 文件持久化，记录已推送的新闻链接用于去重。"""

    def __init__(self, data_dir: str, max_entries: int = 300):
        self._file = os.path.join(data_dir, "news_history.json")
        self._max_entries = max_entries
        self._seen_links: set[str] = set()
        self._snapshots: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._seen_links = set(data.get("seen_links", []))
            self._snapshots = list(data.get("snapshots", []))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._seen_links = set()
            self._snapshots = []

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._file), exist_ok=True)
            data = {
                "seen_links": list(self._seen_links)[-self._max_entries :],
                "snapshots": self._snapshots[-10:],
            }
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            _logger.warning("保存新闻历史失败: %s", exc)

    def is_new(self, link: str) -> bool:
        """判断链接是否为自上次记录以来的新条目。"""
        return bool(link) and link not in self._seen_links

    def record_snapshot(self, items: list[NewsHeadline]) -> None:
        """记录一次抓取的快照并更新已见链接集合。"""
        new_links = [item.link for item in items if item.link]
        self._seen_links.update(new_links)
        # 控制集合大小
        if len(self._seen_links) > self._max_entries * 2:
            self._seen_links = set(list(self._seen_links)[-self._max_entries :])

        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(items),
            "links": new_links,
        }
        self._snapshots.append(snapshot)
        self._snapshots = self._snapshots[-10:]
        self._save()
