"""AstrBot 新闻插件入口：仅包含 AstrBot 兼容层和插件类。

核心逻辑（数据模型、配置解析、网络抓取、解析、持久化）
均位于 daily_news_core/ 子包中。
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

_logger = logging.getLogger(__name__)

from .daily_news_core import (
    CATEGORY_NAMES,
    DEFAULT_DAILYHOT_BASE_URL,
    HeadlineRenderer,
    NewsConfig,
    NewsFeedClient,
    NewsFetchError,
    NewsHeadline,
    NewsHistory,
    NewsScheduler,
    SubscriptionRecord,
    UserPrefs,
    UserPrefsStore,
    coerce_int,
    create_cache_backend,
    default_renderer,
    news_config_from_mapping,
    resolve_source_token,
)

# 中文分类名 → 英文 ID 反向映射
_CATEGORY_ALIAS: dict[str, str] = {v: k for k, v in CATEGORY_NAMES.items()}

try:
    from astrbot.api import AstrBotConfig
    from astrbot.api.event import AstrMessageEvent, filter
    from astrbot.api.star import Context, Star, register, StarTools
except ModuleNotFoundError:  # pragma: no cover - local fallback for development-only validation
    _ASTRBOT_AVAILABLE = False
    import pathlib
    import tempfile

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


    class _DevStarTools:
        """开发/CI 环境下的 StarTools 替代品，写入系统临时目录"""

        @staticmethod
        def get_data_dir(plugin_name: str) -> pathlib.Path:
            path = pathlib.Path(tempfile.gettempdir()) / "astrbot_dev" / plugin_name
            path.mkdir(parents=True, exist_ok=True)
            return path


    StarTools = _DevStarTools

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

def _resolve_data_dir(plugin_name: str) -> str:
    """
    三层降级策略解析插件数据目录：

    Tier 1 — StarTools.get_data_dir()
        AstrBot 官方 API，返回 data/plugin_data/<name>/
        在所有正常 AstrBot 部署中均可用

    Tier 2 — CWD 相对路径
        匹配 AstrBot 默认目录结构，适用于 uv/Docker 等特殊部署
        创建后探针写入测试，失败则继续降级

    Tier 3 — 用户 home 目录
        绝对兜底，只要进程有家目录就能写
        数据在 ~/.local/share/astrbot/plugin_data/<name>/
    """
    # Tier 1：AstrBot 官方 API
    try:
        path = StarTools.get_data_dir(plugin_name)
        return str(path)
    except (AttributeError, TypeError, OSError) as exc:
        _logger.debug("StarTools.get_data_dir 失败，降级到 Tier 2: %s", exc)

    # Tier 2：CWD 相对路径（兼容 AstrBot 默认目录布局）
    cwd_candidate = os.path.join(os.getcwd(), "data", "plugin_data", plugin_name)
    try:
        os.makedirs(cwd_candidate, exist_ok=True)
        # 探针写入：验证实际可写，不只是目录存在
        _probe = os.path.join(cwd_candidate, ".write_probe")
        with open(_probe, "w") as f:
            f.write("ok")
        os.remove(_probe)
        return cwd_candidate
    except OSError:
        pass

    # Tier 3：用户 home 目录（绝对兜底）
    home_candidate = os.path.join(
        os.path.expanduser("~"),
        ".local", "share", "astrbot", "plugin_data", plugin_name,
    )
    os.makedirs(home_candidate, exist_ok=True)
    return home_candidate

@register(
    "astrbot_plugin_news",
    "YARIZM",
    "Daily News plugin for AstrBot",
    "0.4.0",
    "https://github.com/yarizm/Astrbot_plugin_news",
)
class DailyNewsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config: NewsConfig = news_config_from_mapping(config or {})
        cache_backend = create_cache_backend(self.config.redis_url or None)
        self.client = NewsFeedClient(self.config, cache_backend)
        # ✅ 改为三层降级策略
        data_dir = _resolve_data_dir("astrbot_plugin_news")
        self._history = NewsHistory(data_dir)
        # 定时推送调度器
        self._scheduler = NewsScheduler(data_dir, self._push_callback)
        self._scheduler.start()
        # 用户偏好存储
        self._user_prefs = UserPrefsStore(data_dir)
        # 渲染器
        self._renderer = default_renderer

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

        # 检查用户偏好分类
        preferred_category = self._get_user_preferred_category(event.session_id)
        safe_limit = limit if limit > 0 else None

        if preferred_category:
            yield event.plain_result(
                await self._fetch_and_render_category(preferred_category, safe_limit)
            )
        else:
            yield event.plain_result(await self._fetch_and_render(safe_limit))
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
        """按分类获取新闻。分类：tech(科技)/entertainment(娱乐)/news(综合资讯)"""
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

    @news.command("subscribe")
    async def news_subscribe(self, event: AstrMessageEvent, time_str: str = "", category: str = "", limit: int = 0):
        """订阅定时推送。用法：/news subscribe 08:00 [分类] [条数]"""
        if not self.config.enable_fallback_commands:
            yield event.plain_result("管理员已关闭 /news 命令入口。")
            event.stop_event()
            return

        if not time_str:
            yield event.plain_result(
                "请指定推送时间，格式：HH:MM\n"
                "用法：/news subscribe 08:00 [分类] [条数]\n"
                "示例：/news subscribe 09:00 tech 5"
            )
            event.stop_event()
            return

        # 解析时间
        try:
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            from datetime import time as dt_time
            push_time = dt_time(hour=hour, minute=minute)
        except (ValueError, AttributeError):
            yield event.plain_result("时间格式错误，请使用 HH:MM 格式，如 08:00")
            event.stop_event()
            return

        # 解析分类（可选）
        resolved_category = None
        if category:
            resolved_category = self._resolve_category(category)
            if resolved_category is None:
                cats = "、".join(f"{k}({v})" for k, v in CATEGORY_NAMES.items())
                yield event.plain_result(f"未知分类 {category!r}。可用：{cats}")
                event.stop_event()
                return

        # 解析条数
        safe_limit = max(1, coerce_int(limit, 5))

        # 获取会话 ID
        session_id = event.session_id

        # 创建订阅记录
        record = SubscriptionRecord(
            session_id=session_id,
            push_time=push_time,
            category=resolved_category,
            limit=safe_limit,
        )
        self._scheduler.subscribe(record)

        # 确认消息
        cat_display = CATEGORY_NAMES.get(resolved_category, "全部") if resolved_category else "全部"
        yield event.plain_result(
            f"✅ 订阅成功！\n"
            f"推送时间：{time_str}\n"
            f"新闻分类：{cat_display}\n"
            f"推送条数：{safe_limit}\n"
            f"取消订阅：/news unsubscribe"
        )
        event.stop_event()

    @news.command("unsubscribe")
    async def news_unsubscribe(self, event: AstrMessageEvent):
        """取消当前会话的定时推送订阅。"""
        session_id = event.session_id
        if self._scheduler.unsubscribe(session_id):
            yield event.plain_result("✅ 已取消定时推送订阅。")
        else:
            yield event.plain_result("当前会话没有订阅记录。")
        event.stop_event()

    @news.command("subscriptions")
    async def news_subscriptions(self, event: AstrMessageEvent):
        """查看当前会话的订阅信息。"""
        session_id = event.session_id
        record = self._scheduler.get_subscription(session_id)
        if record is None:
            yield event.plain_result("当前会话没有订阅记录。\n使用 /news subscribe <时间> 订阅定时推送。")
        else:
            cat_display = CATEGORY_NAMES.get(record.category, "全部") if record.category else "全部"
            yield event.plain_result(
                f"📰 当前订阅信息：\n"
                f"推送时间：{record.push_time.strftime('%H:%M')}\n"
                f"新闻分类：{cat_display}\n"
                f"推送条数：{record.limit}\n"
                f"取消订阅：/news unsubscribe"
            )
        event.stop_event()

    @news.command("prefer")
    async def news_prefer(self, event: AstrMessageEvent, action: str = "", *args):
        """设置个人偏好。用法：/news prefer <分类1> <分类2> ... 或 /news prefer source <源1> <源2> ..."""
        session_id = event.session_id
        prefs = self._user_prefs.get_prefs(session_id)

        if not action:
            # 显示当前偏好
            if not prefs.preferred_categories and not prefs.preferred_sources:
                yield event.plain_result(
                    "当前没有设置个人偏好，使用全局默认配置。\n\n"
                    "用法：\n"
                    "  /news prefer tech social     设置偏好分类\n"
                    "  /news prefer source zhihu weibo  设置偏好源\n"
                    "  /news prefer reset           重置为全局默认"
                )
            else:
                cats = "、".join(prefs.preferred_categories) or "（使用全局）"
                sources = "、".join(prefs.preferred_sources) or "（使用全局）"
                yield event.plain_result(
                    f"📰 个人偏好设置：\n"
                    f"偏好分类：{cats}\n"
                    f"偏好源：{sources}\n\n"
                    f"重置：/news prefer reset"
                )
            event.stop_event()
            return

        if action.lower() == "reset":
            self._user_prefs.reset_prefs(session_id)
            yield event.plain_result("✅ 已重置为全局默认配置。")
            event.stop_event()
            return

        if action.lower() == "source":
            # 设置偏好源
            if not args:
                yield event.plain_result("请指定偏好源，如：/news prefer source zhihu weibo")
                event.stop_event()
                return
            prefs.preferred_sources = list(args)
            self._user_prefs.update_prefs(prefs)
            yield event.plain_result(f"✅ 偏好源已设置：{'、'.join(args)}")
            event.stop_event()
            return

        # 设置偏好分类
        resolved_cats = []
        for cat in [action] + list(args):
            resolved = self._resolve_category(cat)
            if resolved:
                resolved_cats.append(resolved)
            else:
                cats = "、".join(f"{k}({v})" for k, v in CATEGORY_NAMES.items())
                yield event.plain_result(f"未知分类 {cat!r}。可用：{cats}")
                event.stop_event()
                return

        prefs.preferred_categories = resolved_cats
        self._user_prefs.update_prefs(prefs)
        cat_names = "、".join(CATEGORY_NAMES.get(c, c) for c in resolved_cats)
        yield event.plain_result(f"✅ 偏好分类已设置：{cat_names}")
        event.stop_event()

    @news.command("search")
    async def news_search(self, event: AstrMessageEvent, keyword: str = ""):
        """搜索新闻关键词。用法：/news search <关键词>"""
        if not self.config.enable_fallback_commands:
            yield event.plain_result("管理员已关闭 /news 命令入口。")
            event.stop_event()
            return

        if not keyword:
            yield event.plain_result("请指定搜索关键词，例：/news search 人工智能")
            event.stop_event()
            return

        # 获取所有新闻
        try:
            _, all_items = await self.client.fetch_headlines(limit=None)
        except NewsFetchError as exc:
            details = "；".join(exc.messages[:3]) if exc.messages else "获取失败。"
            yield event.plain_result(f"获取新闻失败：{details}")
            event.stop_event()
            return
        except Exception as exc:
            yield event.plain_result(f"获取新闻失败：{exc}")
            event.stop_event()
            return

        # 按用户偏好源过滤
        filtered_items = self._filter_by_preferred_sources(event.session_id, list(all_items))

        # 关键词过滤
        keyword_lower = keyword.lower()
        matched = [
            item for item in filtered_items
            if keyword_lower in item.title.lower() or
               (item.summary and keyword_lower in item.summary.lower())
        ]

        if not matched:
            yield event.plain_result(f"没有找到包含「{keyword}」的新闻。")
            event.stop_event()
            return

        # 记录历史
        self._history.record_snapshot(matched[:self.config.max_items])

        # 渲染结果
        yield event.plain_result(
            self._render_headlines(f"「{keyword}」相关新闻", matched[:self.config.max_items])
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
        Categories: tech(科技), entertainment(娱乐), news(综合资讯).
        Common requests include: 科技新闻, 娱乐热点, 有什么技术新闻.
        Args:
            category(string): Category ID. One of: tech, entertainment, news.
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

    def _get_user_preferred_sources(self, session_id: str | None) -> list[str] | None:
        """获取用户偏好源列表，未设置则返回 None。"""
        if not session_id:
            return None
        prefs = self._user_prefs.get_prefs(session_id)
        return prefs.preferred_sources if prefs.preferred_sources else None

    def _get_user_preferred_category(self, session_id: str | None) -> str | None:
        """获取用户偏好分类，未设置则返回 None。"""
        if not session_id:
            return None
        prefs = self._user_prefs.get_prefs(session_id)
        if prefs.preferred_categories:
            return prefs.preferred_categories[0]  # 使用第一个偏好分类
        return None

    def _filter_by_preferred_sources(
        self, session_id: str | None, items: list[NewsHeadline],
    ) -> list[NewsHeadline]:
        """按用户偏好源过滤新闻条目，未设置偏好则返回原列表。"""
        preferred = self._get_user_preferred_sources(session_id)
        if not preferred:
            return items
        preferred_set = {s.lower() for s in preferred}
        return [
            item for item in items
            if item.source and item.source.lower() in preferred_set
        ] or items  # 若过滤后为空则回退到原列表

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

        # AI 摘要增强
        if self.config.enable_ai_summary:
            items = await self._enrich_with_ai_summary(list(items))

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

    async def _enrich_with_ai_summary(self, items: list[NewsHeadline]) -> list[NewsHeadline]:
        """使用 LLM 为新闻标题生成 AI 摘要。"""
        if not items:
            return items

        # 获取 LLM Provider
        try:
            provider = self.context.get_using_provider()
        except Exception:
            _logger.debug("无法获取 LLM Provider，跳过 AI 摘要")
            return items

        if provider is None:
            _logger.debug("未配置 LLM Provider，跳过 AI 摘要")
            return items

        # 批量生成摘要（带并发限制）
        semaphore = asyncio.Semaphore(3)  # 最多 3 个并发请求

        async def generate_summary(item: NewsHeadline) -> NewsHeadline:
            if item.summary:  # 已有摘要则跳过
                return item
            async with semaphore:
                try:
                    prompt = f"{self.config.ai_summary_prompt}\n\n{item.title}"
                    response = await provider.text_chat(prompt)
                    summary = response.strip()
                    if summary:
                        return NewsHeadline(
                            title=item.title,
                            link=item.link,
                            published_at=item.published_at,
                            source=item.source,
                            summary=summary[:120],  # 限制长度
                        )
                except Exception:
                    _logger.debug("AI 摘要生成失败: %s", item.title)
            return item

        # 并发生成摘要
        enriched = await asyncio.gather(*[generate_summary(item) for item in items])
        return list(enriched)

    async def terminate(self) -> None:
        """插件卸载时关闭 aiohttp session 和调度器。"""
        await self._scheduler.stop()
        await self.client.close()

    # —— 定时推送回调 ——

    async def _push_callback(self, record: SubscriptionRecord) -> None:
        """定时推送回调：获取新闻并发送到订阅会话。"""
        try:
            if record.category:
                feed_title, items = await self.client.fetch_headlines_by_category(
                    record.category, limit=record.limit,
                )
            else:
                feed_title, items = await self.client.fetch_headlines(limit=record.limit)
        except Exception:
            _logger.exception("定时推送获取新闻失败: %s", record.session_id)
            return

        if not items:
            return

        # 按用户偏好源过滤
        items = self._filter_by_preferred_sources(record.session_id, list(items))
        if not items:
            return

        # 记录历史
        self._history.record_snapshot(items)

        # 渲染并发送
        output = self._render_headlines(feed_title, items)
        try:
            # 通过 AstrBot Context 发送消息到订阅会话
            await self.context.send_message(record.session_id, output)
        except Exception:
            _logger.exception("定时推送发送失败: %s", record.session_id)

    # —— 渲染 ——

    def _render_headlines(self, feed_title: str, items: list[NewsHeadline], platform: str = "plain") -> str:
        """渲染新闻标题，支持平台自适应格式。"""
        return self._renderer.render(feed_title, items, platform)

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
                "/news today [count]      获取今日新闻（使用偏好分类）",
                "/news category <分类> [count]  按分类获取",
                "/news new [count]        仅显示新条目",
                "/news sources            查看新闻源列表",
                "/news search <关键词>    搜索新闻",
                "/news subscribe <时间> [分类] [条数]  订阅定时推送",
                "/news unsubscribe        取消定时推送",
                "/news subscriptions      查看订阅信息",
                "/news prefer [分类...]    设置个人偏好",
                "/news help               显示此帮助",
                "",
                f"当前新闻源：{source_names}",
                f"可用分类：{cats}",
                "",
                "个人偏好示例：",
                "  /news prefer tech social     设置偏好分类",
                "  /news prefer source zhihu    设置偏好源",
                "  /news prefer reset           重置偏好",
                "",
                "定时推送示例：",
                "  /news subscribe 08:00        每天 8 点推送全部新闻",
                "  /news subscribe 09:00 tech   每天 9 点推送科技新闻",
                "  /news subscribe 07:30 news 10  每天 7:30 推送 10 条综合资讯",
                "",
                "自然语言示例：",
                "  今天有什么新闻",
                "  看看科技新闻",
                "  给我知乎热榜",
                "  有哪些新闻源",
            ]
        )
