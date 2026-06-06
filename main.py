"""AstrBot 新闻插件入口：仅包含 AstrBot 兼容层和插件类。

核心逻辑（数据模型、配置解析、网络抓取、解析、持久化）
均位于 daily_news_core/ 子包中。
"""
from __future__ import annotations

import os
from typing import Any

from .daily_news_core import (
    CATEGORY_NAMES,
    DEFAULT_DAILYHOT_BASE_URL,
    NewsConfig,
    NewsFeedClient,
    NewsFetchError,
    NewsHeadline,
    NewsHistory,
    coerce_int,
    news_config_from_mapping,
    resolve_source_token,
)

# 中文分类名 → 英文 ID 反向映射
_CATEGORY_ALIAS: dict[str, str] = {v: k for k, v in CATEGORY_NAMES.items()}

try:
    from astrbot.api import AstrBotConfig
    from astrbot.api.event import AstrMessageEvent, filter
    from astrbot.api.star import Context, Star, register
except ModuleNotFoundError:  # pragma: no cover - local fallback for development-only validation
    AstrBotConfig = dict[str, Any]

    class AstrMessageEvent:  # pragma: no cover
        def plain_result(self, text: str) -> str:
            return text

        def stop_event(self) -> None:
            return None

    class Context:  # pragma: no cover
        pass

    class Star:  # pragma: no cover
        def __init__(self, context: Context):
            self.context = context

    def register(*args, **kwargs):  # pragma: no cover
        def decorator(cls):
            return cls

        return decorator

    class _CommandGroupDecorator:  # pragma: no cover
        def __init__(self, func):
            self.func = func

        def __call__(self, *args, **kwargs):
            return self.func(*args, **kwargs)

        def command(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    class _FallbackFilter:  # pragma: no cover
        @staticmethod
        def command_group(*args, **kwargs):
            def decorator(fn):
                return _CommandGroupDecorator(fn)

            return decorator

        @staticmethod
        def llm_tool(*args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    filter = _FallbackFilter()


# ---------------------------------------------------------------------------
# 插件入口
# ---------------------------------------------------------------------------

@register(
    "astrbot_plugin_news",
    "YARIZM",
    "Daily News plugin for AstrBot",
    "0.4.0",
    "https://github.com/yarizm/EuxrvshPVPBOTv0.01",
)
class DailyNewsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config: NewsConfig = news_config_from_mapping(config or {})
        self.client = NewsFeedClient(self.config)
        # 数据持久化目录
        data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data",
            "astrbot_plugin_news",
        )
        self._history = NewsHistory(data_dir)

    # —— 命令 ——

    @filter.command_group("news")
    def news(self):
        """Daily news fallback commands."""

    @news.command("help")
    async def news_help(self, event: AstrMessageEvent):
        yield event.plain_result(self._help_text())
        event.stop_event()

    @news.command("today")
    async def news_today(self, event: AstrMessageEvent, limit: int = 0):
        if not self.config.enable_fallback_commands:
            yield event.plain_result("管理员已关闭 /news 命令入口。")
            event.stop_event()
            return
        yield event.plain_result(await self._fetch_and_render(limit if limit > 0 else None))
        event.stop_event()

    @news.command("sources")
    async def news_sources(self, event: AstrMessageEvent):
        """列出所有已配置的新闻源。"""
        if not self.config.enable_fallback_commands:
            yield event.plain_result("管理员已关闭 /news 命令入口。")
            event.stop_event()
            return
        yield event.plain_result(self._render_sources_list())
        event.stop_event()

    @news.command("category")
    async def news_category(self, event: AstrMessageEvent, category: str = "", limit: int = 0):
        """按分类获取新闻。分类：tech/social/entertainment/finance/news"""
        if not self.config.enable_fallback_commands:
            yield event.plain_result("管理员已关闭 /news 命令入口。")
            event.stop_event()
            return
        if not category:
            cats = "、".join(f"{k}({v})" for k, v in CATEGORY_NAMES.items())
            yield event.plain_result(f"请指定分类：{cats}\n用法：/news category <分类> [数量]")
            event.stop_event()
            return
        resolved = self._resolve_category(category)
        if resolved is None:
            cats = "、".join(f"{k}({v})" for k, v in CATEGORY_NAMES.items())
            yield event.plain_result(f"未知分类 {category!r}。可用：{cats}")
            event.stop_event()
            return
        yield event.plain_result(
            await self._fetch_and_render_category(resolved, limit if limit > 0 else None)
        )
        event.stop_event()

    @news.command("new")
    async def news_new(self, event: AstrMessageEvent, limit: int = 0):
        """仅获取自上次查询以来的新条目（去重历史）。"""
        if not self.config.enable_fallback_commands:
            yield event.plain_result("管理员已关闭 /news 命令入口。")
            event.stop_event()
            return
        yield event.plain_result(
            await self._fetch_and_render(limit if limit > 0 else None, only_new=True)
        )
        event.stop_event()

    # —— LLM Tools ——

    @filter.llm_tool(name="news_fetch_daily_headlines")
    async def llm_fetch_daily_headlines(self, event: AstrMessageEvent, limit: int = 0):
        """Fetch today's top headlines from the configured sources.
        Use when the user asks for today's news, latest headlines, daily briefing, or current affairs summary.
        Common requests include: 今日新闻, 今天有什么新闻, 给我一份今日快讯, 最新头条.
        Args:
            limit(number): Optional max number of headlines to return. Uses plugin default when omitted or 0.
        """
        safe_limit = coerce_int(limit, 0)
        return await self._fetch_and_render(safe_limit if safe_limit > 0 else None)

    @filter.llm_tool(name="news_list_available_sources")
    async def llm_list_sources(self, event: AstrMessageEvent):
        """List all currently configured news sources with their IDs, names, types, and categories.
        Use when the user asks what news sources are available, or wants to know what can be fetched.
        Common requests include: 有哪些新闻源, 可以获取哪些新闻, 支持什么平台.
        """
        sources = self.client.get_all_sources_info()
        if not sources:
            return "当前没有配置任何新闻源。"
        lines = ["当前已配置的新闻源："]
        for s in sources:
            lines.append(f"  - {s['name']}（ID: {s['id']}，类型: {s['type']}，分类: {s['category']}）")
        cats = "、".join(f"{v}({k})" for k, v in CATEGORY_NAMES.items())
        lines.append(f"\n可用分类：{cats}")
        lines.append("你可以说「看看科技新闻」或「给我知乎热榜」来查询特定分类或来源。")
        return "\n".join(lines)

    @filter.llm_tool(name="news_fetch_by_category")
    async def llm_fetch_by_category(self, event: AstrMessageEvent, category: str = "", limit: int = 0):
        """Fetch headlines filtered by a specific category.
        Use when the user asks for news in a specific topic area.
        Categories: tech(科技), social(社交), entertainment(娱乐), finance(财经), news(综合资讯).
        Common requests include: 科技新闻, 娱乐热点, 财经资讯, 有什么技术新闻.
        Args:
            category(string): Category ID. One of: tech, social, entertainment, finance, news.
            limit(number): Optional max number of headlines. Uses plugin default when omitted or 0.
        """
        if not category:
            cats = "、".join(f"{k}({v})" for k, v in CATEGORY_NAMES.items())
            return f"请指定分类。可用分类：{cats}"
        resolved = self._resolve_category(category)
        if resolved is None:
            cats = "、".join(f"{k}({v})" for k, v in CATEGORY_NAMES.items())
            return f"未知分类 {category!r}。可用：{cats}"
        safe_limit = coerce_int(limit, 0)
        return await self._fetch_and_render_category(
            resolved, safe_limit if safe_limit > 0 else None
        )

    @filter.llm_tool(name="news_fetch_from_source")
    async def llm_fetch_from_source(self, event: AstrMessageEvent, source_id: str = "", limit: int = 0):
        """Fetch headlines from a specific news source by its ID.
        Use when the user asks for news from a particular source, e.g. "看看知乎热榜" or "给我微博热搜".
        Args:
            source_id(string): The source ID (e.g. douyin, juejin, v2ex, ithome, 36kr-newsflash).
            limit(number): Optional max number of headlines. Uses plugin default when omitted or 0.
        """
        if not source_id:
            return "请指定新闻源 ID。可用源可通过 news_list_available_sources 工具查看。"

        # 查找源：先查已配置，再尝试内联解析
        source = None
        for s in self.config.sources:
            if s.source_id == source_id or s.display_name == source_id:
                source = s
                break
        if source is None:
            try:
                source = resolve_source_token(source_id, DEFAULT_DAILYHOT_BASE_URL)
            except ValueError:
                available = "、".join(s.source_id for s in self.config.sources)
                return f"未找到新闻源 {source_id!r}。可用源：{available}"

        safe_limit = coerce_int(limit, 0)
        max_items = safe_limit if safe_limit > 0 else self.config.max_items
        try:
            result, error = await self.client.fetch_source(source, max_items)
        except Exception as exc:
            return f"获取 {source.display_name} 失败：{exc}"

        if error:
            return error
        if result is None or not result.items:
            return f"{source.display_name} 没有返回可展示的头条。"

        return self._render_headlines(f"{source.display_name} 热榜", list(result.items))

    # —— 内部方法 ——

    @staticmethod
    def _resolve_category(raw: str) -> str | None:
        """将用户输入的分类名（中文或英文）解析为分类 ID。"""
        raw = raw.strip().lower()
        if raw in CATEGORY_NAMES:
            return raw
        return _CATEGORY_ALIAS.get(raw)

    async def _fetch_and_render(self, limit: int | None, only_new: bool = False) -> str:
        try:
            feed_title, items = await self.client.fetch_headlines(limit=limit)
        except NewsFetchError as exc:
            details = "；".join(exc.messages[:3]) if exc.messages else "没有可用的新闻源。"
            return f"获取新闻失败：{details}"
        except Exception as exc:
            return f"获取新闻失败：{exc}"

        if not items:
            return "当前新闻源没有返回可展示的头条。"

        if only_new:
            # 先过滤新条目，再记录快照（避免 record_snapshot 提前污染 seen_links）
            new_items = [item for item in items if self._history.is_new(item.link)]
            self._history.record_snapshot(items)
            if not new_items:
                return "自上次查询以来没有新的新闻条目。"
            items = new_items
            feed_title = feed_title.replace("今日新闻", "今日新条目")
        else:
            self._history.record_snapshot(items)

        return self._render_headlines(feed_title, items)

    async def _fetch_and_render_category(self, category: str, limit: int | None) -> str:
        try:
            feed_title, items = await self.client.fetch_headlines_by_category(
                category, limit=limit,
            )
        except NewsFetchError as exc:
            details = "；".join(exc.messages[:3]) if exc.messages else "获取失败。"
            return f"获取分类新闻失败：{details}"
        except Exception as exc:
            return f"获取分类新闻失败：{exc}"

        if not items:
            return "该分类没有返回可展示的头条。"

        self._history.record_snapshot(items)
        return self._render_headlines(feed_title, items)

    async def terminate(self) -> None:
        """插件卸载时关闭 aiohttp session。"""
        await self.client.close()

    # —— 渲染 ——

    @staticmethod
    def _render_headlines(feed_title: str, items: list[NewsHeadline]) -> str:
        lines = [feed_title]
        for index, item in enumerate(items, start=1):
            suffix = f" ({item.source})" if item.source else ""
            lines.append(f"{index}. {item.title}{suffix}")
            if item.summary:
                lines.append(f"   摘要：{item.summary}")
            if item.published_at:
                lines.append(f"   发布时间：{item.published_at}")
            if item.link:
                lines.append(f"   链接：{item.link}")
        return "\n".join(lines)

    def _render_sources_list(self) -> str:
        sources = self.client.get_all_sources_info()
        if not sources:
            return "当前没有配置任何新闻源。"
        lines = ["已配置的新闻源："]
        for s in sources:
            lines.append(
                f"  • {s['name']}（{s['id']}）"
                f"  [{s['type']}]  [{s['category']}]"
            )
        cats = "、".join(f"{v}({k})" for k, v in CATEGORY_NAMES.items())
        lines.append(f"\n可用分类：{cats}")
        lines.append("\n用法：/news category <分类ID> [数量]")
        return "\n".join(lines)

    def _help_text(self) -> str:
        source_names = "、".join(source.display_name for source in self.config.sources) or "未配置"
        cats = "、".join(f"{v}({k})" for k, v in CATEGORY_NAMES.items())
        return "\n".join(
            [
                "Daily News commands:",
                "/news today [count]      获取今日新闻",
                "/news category <分类> [count]  按分类获取",
                "/news new [count]        仅显示新条目",
                "/news sources            查看新闻源列表",
                "/news help               显示此帮助",
                "",
                f"当前新闻源：{source_names}",
                f"可用分类：{cats}",
                "",
                "自然语言示例：",
                "  今天有什么新闻",
                "  看看科技新闻",
                "  给我知乎热榜",
                "  有哪些新闻源",
            ]
        )
