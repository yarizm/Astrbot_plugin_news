from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

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


DEFAULT_RSS_URL = "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
DEFAULT_MAX_ITEMS = 5
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class NewsConfig:
    rss_url: str = DEFAULT_RSS_URL
    max_items: int = DEFAULT_MAX_ITEMS
    request_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    enable_fallback_commands: bool = True


@dataclass(frozen=True)
class NewsHeadline:
    title: str
    link: str
    published_at: str = ""
    source: str = ""


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def news_config_from_mapping(raw_config: Mapping[str, Any]) -> NewsConfig:
    rss_url = str(raw_config.get("rss_url", "") or "").strip() or DEFAULT_RSS_URL
    return NewsConfig(
        rss_url=rss_url,
        max_items=_coerce_int(raw_config.get("max_items"), DEFAULT_MAX_ITEMS),
        request_timeout_seconds=_coerce_int(raw_config.get("request_timeout_seconds"), DEFAULT_TIMEOUT_SECONDS),
        enable_fallback_commands=_coerce_bool(raw_config.get("enable_fallback_commands"), True),
    )


class NewsFeedClient:
    def __init__(self, config: NewsConfig):
        self.config = config

    def fetch_headlines(self, limit: int | None = None) -> tuple[str, list[NewsHeadline]]:
        max_items = _coerce_int(limit, self.config.max_items) if limit else self.config.max_items
        request = Request(
            self.config.rss_url,
            headers={"User-Agent": "AstrBotDailyNews/0.1"},
        )
        with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
            payload = response.read()

        root = ElementTree.fromstring(payload)
        channel = root.find("channel")
        if channel is None:
            raise ValueError("RSS feed format is not supported or contains no channel node.")

        feed_title = self._clean_text(self._child_text(channel, "title")) or "Today's Headlines"
        items = []
        for item in channel.findall("item"):
            title = self._clean_text(self._child_text(item, "title"))
            link = self._clean_text(self._child_text(item, "link"))
            published_at = self._clean_text(self._child_text(item, "pubDate"))
            source = self._clean_text(self._child_text(item, "source"))
            if not title:
                continue
            items.append(
                NewsHeadline(
                    title=title,
                    link=link,
                    published_at=published_at,
                    source=source,
                )
            )
            if len(items) >= max_items:
                break
        return feed_title, items

    @staticmethod
    def _child_text(node: ElementTree.Element, tag: str) -> str:
        child = node.find(tag)
        return child.text if child is not None and child.text else ""

    @staticmethod
    def _clean_text(value: str) -> str:
        cleaned = html.unescape(value or "").strip()
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()


@register(
    "astrbot_plugin_daily_news",
    "YARIZM",
    "Daily News plugin for AstrBot",
    "0.1.0",
    "https://github.com/yarizm/EuxrvshPVPBOTv0.01",
)
class DailyNewsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = news_config_from_mapping(config or {})
        self.client = NewsFeedClient(self.config)

    @filter.command_group("news")
    def news(self):
        """Daily news fallback commands."""

    @news.command("help")
    async def news_help(self, event: AstrMessageEvent):
        yield event.plain_result(self._help_text())
        event.stop_event()

    @news.command("today")
    async def news_today(self, event: AstrMessageEvent, limit: int = 0):
        yield event.plain_result(self._fetch_and_render(limit if limit > 0 else None))
        event.stop_event()

    @filter.llm_tool(name="news_fetch_daily_headlines")
    async def llm_fetch_daily_headlines(self, event: AstrMessageEvent, limit: int = 0):
        """Fetch today's top headlines from the configured RSS feed.
        Use when the user asks for today's news, latest headlines, daily briefing, or current affairs summary.
        Common requests include: 今日新闻, 今天有什么新闻, 给我一份今日快讯, 最新头条.
        Args:
            limit(number): Optional max number of headlines to return. Uses plugin default when omitted or 0.
        """
        return self._fetch_and_render(limit if int(limit) > 0 else None)

    def _fetch_and_render(self, limit: int | None) -> str:
        try:
            feed_title, items = self.client.fetch_headlines(limit=limit)
        except HTTPError as exc:
            return f"获取新闻失败：新闻源返回 HTTP {exc.code}。"
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            return f"获取新闻失败：无法连接新闻源（{reason}）。"
        except ElementTree.ParseError:
            return "获取新闻失败：新闻源返回了无法解析的 RSS/XML 内容。"
        except Exception as exc:
            return f"获取新闻失败：{exc}"

        if not items:
            return "当前新闻源没有返回可展示的头条。"

        return self._render_headlines(feed_title, items)

    @staticmethod
    def _render_headlines(feed_title: str, items: list[NewsHeadline]) -> str:
        lines = [f"今日新闻：{feed_title}"]
        for index, item in enumerate(items, start=1):
            suffix = f" ({item.source})" if item.source else ""
            lines.append(f"{index}. {item.title}{suffix}")
            if item.published_at:
                lines.append(f"   发布时间：{item.published_at}")
            if item.link:
                lines.append(f"   链接：{item.link}")
        return "\n".join(lines)

    @staticmethod
    def _help_text() -> str:
        return "\n".join(
            [
                "Daily News commands:",
                "/news today [count]",
                "/news help",
                "",
                "自然语言示例：",
                "今天有什么新闻",
                "给我一份今日快讯",
                "抓取 3 条头条新闻",
            ]
        )
