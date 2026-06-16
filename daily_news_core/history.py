"""新闻历史持久化：JSON 文件存储已推送链接，用于去重。"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from .models import NewsHeadline

_logger = logging.getLogger(__name__)

# ── 可调参数 ──────────────────────────────────────────────────────────────────

# 内存 + 磁盘保留链接的最大条数
# 5 000 × ~80 字节 ≈ 400 KB，在任何设备上都可忽略不计
_MAX_LINKS: int = 5_000

# 超过多少天的记录视为过期并删除
# 30 天覆盖任何现实的热榜去重窗口
_TTL_DAYS: int = 30


class NewsHistory:
    """JSON 持久化的已见新闻链接集合。

    生命周期
    --------
    __init__ → _load()      读取并迁移 JSON 文件
    is_new()                纯内存检查，O(1)
    record_snapshot()       更新内存字典 → _prune() → _persist()
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "seen_links.json"
        # 内部存储：链接 → Unix 时间戳（首次见到时刻）
        self._seen: dict[str, float] = self._load()

    # ── 公开接口（与 v0.4.0 完全相同，main.py 无需改动）─────────────────────

    def is_new(self, link: str | None) -> bool:
        """若 link 未被记录过则返回 True。"""
        return bool(link) and link not in self._seen

    def record_snapshot(self, items: list[NewsHeadline]) -> None:
        """记录 items 为已见，然后清理过期条目并持久化。"""
        now = time.time()
        for item in items:
            if item.link and item.link not in self._seen:
                self._seen[item.link] = now   # 仅记录首次出现时间
        self._prune()
        self._persist()

    # ── 内部实现 ──────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, float]:
        """加载并迁移 JSON 文件，返回 link→timestamp 字典。"""
        if not self._file.exists():
            return {}
        try:
            with self._file.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            # 文件损坏或不可读：从空白状态重新开始，不崩溃
            _logger.warning("历史文件加载失败，从空白状态开始: %s", exc)
            return {}

        # v1 格式：纯 URL 列表（v0.4.0 及以前）
        if isinstance(raw, list):
            now = time.time()
            # 赋予当前时间戳：旧记录再活 TTL_DAYS 天后自然过期
            migrated = {url: now for url in raw if isinstance(url, str)}
            # 立即以 v2 格式写回，下次加载不再需要迁移
            self._file_write({"version": 2, "links": migrated})
            return migrated

        # v2 格式：{"version": 2, "links": {url: timestamp, ...}}
        if isinstance(raw, dict) and "links" in raw:
            links = raw["links"]
            if isinstance(links, dict):
                return {
                    url: float(ts)
                    for url, ts in links.items()
                    if isinstance(url, str) and isinstance(ts, (int, float))
                }

        # 无法识别的格式：从空白开始
        return {}

    def _prune(self) -> None:
        """两阶段清理：先按 TTL 过期，再按容量上限截断。"""
        cutoff = time.time() - _TTL_DAYS * 86_400

        # 阶段 1：删除超过 TTL 天的记录
        before = len(self._seen)
        self._seen = {
            url: ts for url, ts in self._seen.items() if ts > cutoff
        }
        after_ttl = len(self._seen)

        # 阶段 2：超出容量上限时，保留最新的 _MAX_LINKS 条
        if len(self._seen) > _MAX_LINKS:
            sorted_pairs = sorted(
                self._seen.items(), key=lambda kv: kv[1], reverse=True
            )
            self._seen = dict(sorted_pairs[:_MAX_LINKS])

        # 调试日志（仅在有实际清理时输出，避免噪音）
        removed = before - after_ttl
        capped = after_ttl - len(self._seen)
        if removed or capped:
            _logger.debug(
                "history pruned: ttl_removed=%d cap_removed=%d remaining=%d",
                removed, capped, len(self._seen),
            )

    def _persist(self) -> None:
        """原子写入：先写临时文件，再用 os.replace() 替换目标文件。"""
        payload: dict = {"version": 2, "links": self._seen}
        self._file_write(payload)

    def _file_write(self, payload: dict) -> None:
        """将 payload 原子写入 self._file。"""
        tmp = self._file.with_suffix(".json.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                # separators 去掉空格，文件体积减少约 20%
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            # POSIX 上原子，Windows 上比直接覆写更安全（旧文件在替换成功前始终存在）
            os.replace(tmp, self._file)
        except OSError as exc:
            # 写入失败是非致命错误：内存状态仍然正确，下次重启会重新加载
            _logger.warning("历史文件写入失败: %s", exc)
            tmp.unlink(missing_ok=True)
