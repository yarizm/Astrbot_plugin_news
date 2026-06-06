"""核心新闻抓取客户端：异步 + 缓存 + 重试 + 并发。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from xml.etree import ElementTree

import aiohttp

from .config import coerce_int
from .models import (
    MAX_RETRIES,
    SOURCE_HEALTH_THRESHOLD,
    SOURCE_RECOVERY_SECONDS,
    NewsConfig,
    NewsFetchError,
    NewsHeadline,
    NewsSource,
    NewsSourceResult,
)
from .parsers import parse_dailyhot_source, parse_feed_source
from .sources import CATEGORY_NAMES

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部状态数据类
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    result: NewsSourceResult
    fetched_at: float  # time.monotonic()


@dataclass
class _SourceHealth:
    consecutive_failures: int = 0
    last_failure_time: float = 0.0


class NewsFeedClient:
    def __init__(self, config: NewsConfig):
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, _CacheEntry] = {}
        self._source_health: dict[str, _SourceHealth] = {}

    # —— aiohttp session 生命周期 ——

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    # —— 带重试的 HTTP 读取 ——

    async def _read(self, url: str) -> bytes:
        """异步读取 URL 内容，带指数退避重试。"""
        session = await self._get_session()
        last_exc: Exception | None = None

        for attempt in range(1 + MAX_RETRIES):
            try:
                timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
                async with session.get(
                    url,
                    headers={"User-Agent": "AstrBotDailyNews/0.4"},
                    timeout=timeout,
                ) as response:
                    if response.status >= 500:
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=f"Server error: HTTP {response.status}",
                        )
                    return await response.read()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)  # 指数退避: 1s, 2s
                else:
                    break
            except Exception:
                break

        if last_exc is not None:
            raise last_exc
        raise aiohttp.ClientError(f"Failed to fetch {url} after {MAX_RETRIES + 1} attempts")

    # —— 源健康检查 ——

    def _is_source_healthy(self, source_id: str) -> bool:
        health = self._source_health.get(source_id)
        if health is None:
            return True
        if health.consecutive_failures < SOURCE_HEALTH_THRESHOLD:
            return True
        return (time.monotonic() - health.last_failure_time) > SOURCE_RECOVERY_SECONDS

    def _record_source_failure(self, source_id: str) -> None:
        health = self._source_health.get(source_id)
        if health is None:
            health = _SourceHealth()
            self._source_health[source_id] = health
        health.consecutive_failures += 1
        health.last_failure_time = time.monotonic()

    def _record_source_success(self, source_id: str) -> None:
        health = self._source_health.get(source_id)
        if health is not None:
            health.consecutive_failures = 0

    # —— 单源抓取 ——

    async def _fetch_single_source(
        self,
        source: NewsSource,
        limit: int,
    ) -> tuple[NewsSource, NewsSourceResult | None, str | None]:
        """抓取单个源，带缓存 → 健康检查 → 重试。返回 (source, result, error)。"""
        # 健康检查
        if not self._is_source_healthy(source.source_id):
            return source, None, f"{source.display_name} 连续失败 {SOURCE_HEALTH_THRESHOLD} 次，已被临时跳过。"

        # 缓存检查
        if self.config.cache_ttl_seconds > 0:
            cached = self._cache.get(source.source_id)
            if cached is not None:
                if time.monotonic() - cached.fetched_at < self.config.cache_ttl_seconds:
                    return source, cached.result, None

        # 抓取
        try:
            payload = await self._read(source.endpoint)
            if source.source_type == "dailyhot":
                result = parse_dailyhot_source(source, payload, limit)
            else:
                result = parse_feed_source(source, payload, limit)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError,
                json.JSONDecodeError, ElementTree.ParseError) as exc:
            self._record_source_failure(source.source_id)
            error = f"{source.display_name} 失败：{self._format_exception(exc)}"
            return source, None, error
        except Exception as exc:
            self._record_source_failure(source.source_id)
            error = f"{source.display_name} 失败：{exc}"
            return source, None, error

        # 成功 → 缓存 + 重置健康
        self._record_source_success(source.source_id)
        self._cache[source.source_id] = _CacheEntry(
            result=result,
            fetched_at=time.monotonic(),
        )
        return source, result, None

    # —— 主入口 ——

    async def fetch_headlines(self, limit: int | None = None) -> tuple[str, list[NewsHeadline]]:
        """异步获取新闻，支持缓存和并发。"""
        max_items = coerce_int(limit, self.config.max_items) if limit else self.config.max_items
        if not self.config.sources:
            raise NewsFetchError(["未配置可用的新闻源。"])

        source_limit = max(1, (max_items + len(self.config.sources) - 1) // len(self.config.sources))

        # 并发抓取所有源
        tasks = [
            self._fetch_single_source(source, source_limit)
            for source in self.config.sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # 收集结果
        per_source_results: list[tuple[NewsSource, NewsSourceResult]] = []
        errors: list[str] = []

        for source, result, error in results:
            if result is not None and result.items:
                per_source_results.append((source, result))
            elif error is not None:
                errors.append(error)
            else:
                errors.append(f"{source.display_name} 没有返回可展示的头条。")

        merged_items, used_titles = self._merge_results(per_source_results, max_items)

        # 降级：使用陈旧缓存
        if not merged_items and self.config.cache_ttl_seconds > 0:
            stale_results: list[tuple[NewsSource, NewsSourceResult]] = []
            for source in self.config.sources:
                cached = self._cache.get(source.source_id)
                if cached is not None and cached.result.items:
                    stale_results.append((source, cached.result))
            if stale_results:
                merged_items, used_titles = self._merge_results(stale_results, max_items)
                if merged_items:
                    _logger.info("使用过期缓存数据作为降级")

        if merged_items:
            feed_title = "今日新闻（来源：" + "、".join(used_titles) + "）"
            return feed_title, merged_items

        raise NewsFetchError(errors or ["所有新闻源都没有返回可展示内容。"])

    # —— 分类查询 ——

    async def fetch_headlines_by_category(
        self, category: str, limit: int | None = None,
    ) -> tuple[str, list[NewsHeadline]]:
        """按分类获取新闻。"""
        category = category.strip().lower()
        if category not in CATEGORY_NAMES:
            available = "、".join(f"{k}({v})" for k, v in CATEGORY_NAMES.items())
            raise NewsFetchError([f"未知分类 {category!r}，可用分类：{available}"])

        filtered = [s for s in self.config.sources if s.category == category]
        if not filtered:
            cat_display = CATEGORY_NAMES.get(category, category)
            raise NewsFetchError([f"当前配置中没有 {cat_display} 类别的新闻源。"])

        max_items = coerce_int(limit, self.config.max_items) if limit else self.config.max_items
        source_limit = max(1, (max_items + len(filtered) - 1) // len(filtered))

        tasks = [self._fetch_single_source(source, source_limit) for source in filtered]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        per_source_results: list[tuple[NewsSource, NewsSourceResult]] = []
        errors: list[str] = []
        for source, result, error in results:
            if result is not None and result.items:
                per_source_results.append((source, result))
            elif error is not None:
                errors.append(error)

        merged_items, used_titles = self._merge_results(per_source_results, max_items)

        if merged_items:
            cat_display = CATEGORY_NAMES.get(category, category)
            feed_title = f"今日{cat_display}新闻（来源：" + "、".join(used_titles) + "）"
            return feed_title, merged_items

        raise NewsFetchError(errors or [f"{CATEGORY_NAMES.get(category, category)}类别没有返回可展示内容。"])

    # —— 可用源列表 ——

    async def fetch_source(
        self, source: NewsSource, limit: int | None = None,
    ) -> tuple[NewsSourceResult | None, str | None]:
        """公共 API：抓取单个源，返回 (result, error)。"""
        max_items = limit if limit and limit > 0 else self.config.max_items
        _src, result, error = await self._fetch_single_source(source, max_items)
        return result, error

    def get_all_sources_info(self) -> list[dict]:
        """返回所有可用源的描述信息（含分类）。"""
        result = []
        for source in self.config.sources:
            cat_display = CATEGORY_NAMES.get(source.category, source.category or "未分类")
            result.append({
                "id": source.source_id,
                "name": source.display_name,
                "type": source.source_type,
                "category": cat_display,
            })
        return result

    # —— 合并去重 ——

    @staticmethod
    def _merge_results(
        per_source_results: list[tuple[NewsSource, NewsSourceResult]],
        max_items: int,
    ) -> tuple[list[NewsHeadline], list[str]]:
        merged_items: list[NewsHeadline] = []
        used_titles: list[str] = []
        seen: set[str] = set()
        item_lists = [list(result.items) for _, result in per_source_results]

        while len(merged_items) < max_items and any(item_lists):
            for index, items in enumerate(item_lists):
                if not items:
                    continue
                item = items.pop(0)
                dedupe_key = (item.link or item.title).strip().lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                merged_items.append(item)
                source_title = per_source_results[index][1].feed_title or per_source_results[index][0].display_name
                if source_title not in used_titles:
                    used_titles.append(source_title)
                if len(merged_items) >= max_items:
                    break
        return merged_items, used_titles

    # —— 异常格式化 ——

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        if isinstance(exc, aiohttp.ClientResponseError):
            return f"HTTP {exc.status}"
        if isinstance(exc, aiohttp.ClientError):
            return str(exc)
        if isinstance(exc, asyncio.TimeoutError):
            return "请求超时"
        return str(exc)
