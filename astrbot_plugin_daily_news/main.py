from __future__ import annotations

from collections.abc import Iterable, Mapping
import html
import json
import re
from dataclasses import dataclass
from typing import Any
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


LEGACY_GOOGLE_RSS_URL = "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
DEFAULT_SOURCE_IDS = (
    "36kr-newsflash",
    "ithome",
    "cnbeta",
)
DEFAULT_DAILYHOT_BASE_URL = "https://api-hot.imsyy.top"
DEFAULT_MAX_ITEMS = 5
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class NewsSource:
    source_id: str
    display_name: str
    source_type: str
    endpoint: str
    description: str = ""


@dataclass(frozen=True)
class NewsConfig:
    sources: tuple[NewsSource, ...]
    max_items: int = DEFAULT_MAX_ITEMS
    request_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    enable_fallback_commands: bool = True


@dataclass(frozen=True)
class NewsHeadline:
    title: str
    link: str
    published_at: str = ""
    source: str = ""


@dataclass(frozen=True)
class NewsSourceResult:
    feed_title: str
    items: tuple[NewsHeadline, ...]


class NewsFetchError(RuntimeError):
    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("；".join(messages))


BUILTIN_SOURCES: dict[str, tuple[str, str, str, str]] = {
    "36kr-newsflash": (
        "36kr-newsflash",
        "36氪快讯",
        "rss",
        "https://36kr.com/feed-newsflash",
    ),
    "36kr": (
        "36kr",
        "36氪综合资讯",
        "rss",
        "https://36kr.com/feed",
    ),
    "ithome": (
        "ithome",
        "IT之家",
        "rss",
        "https://www.ithome.com/rss/",
    ),
    "cnbeta": (
        "cnbeta",
        "cnBeta",
        "rss",
        "http://rss.cnbeta.com/",
    ),
    "qq-news-hot": (
        "qq-news-hot",
        "腾讯新闻热榜",
        "dailyhot",
        "qq-news",
    ),
    "thepaper-hot": (
        "thepaper-hot",
        "澎湃新闻热榜",
        "dailyhot",
        "thepaper",
    ),
}


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


def _coerce_source_tokens(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = re.split(r"[\r\n,;]+", value)
        return [item.strip() for item in raw_items if item.strip()]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, str)):
        tokens = []
        for item in value:
            token = str(item).strip()
            if token:
                tokens.append(token)
        return tokens
    token = str(value).strip()
    return [token] if token else []


def _build_dailyhot_url(base_url: str, route: str) -> str:
    return f"{base_url.rstrip('/')}/{route.lstrip('/')}"


def _resolve_source_token(token: str, dailyhot_base_url: str) -> NewsSource:
    builtin = BUILTIN_SOURCES.get(token)
    if builtin is not None:
        source_id, display_name, source_type, endpoint = builtin
        if source_type == "dailyhot":
            endpoint = _build_dailyhot_url(dailyhot_base_url, endpoint)
        return NewsSource(
            source_id=source_id,
            display_name=display_name,
            source_type=source_type,
            endpoint=endpoint,
        )

    if token.startswith("dailyhot:"):
        route = token.split(":", 1)[1].strip()
        if not route:
            raise ValueError("dailyhot source is missing a route.")
        return NewsSource(
            source_id=token,
            display_name=f"DailyHot/{route}",
            source_type="dailyhot",
            endpoint=_build_dailyhot_url(dailyhot_base_url, route),
        )

    if token.startswith("rss:"):
        url = token.split(":", 1)[1].strip()
        if not url:
            raise ValueError("rss source is missing a URL.")
        return NewsSource(
            source_id=token,
            display_name=url,
            source_type="rss",
            endpoint=url,
        )

    if token.startswith(("http://", "https://")):
        return NewsSource(
            source_id=token,
            display_name=token,
            source_type="rss",
            endpoint=token,
        )

    raise ValueError(f"Unsupported news source token: {token}")


def _default_source_tokens() -> list[str]:
    return list(DEFAULT_SOURCE_IDS)


def news_config_from_mapping(raw_config: Mapping[str, Any]) -> NewsConfig:
    dailyhot_base_url = (
        str(raw_config.get("dailyhot_base_url", "") or "").strip() or DEFAULT_DAILYHOT_BASE_URL
    )
    source_tokens = _coerce_source_tokens(raw_config.get("source_ids"))

    legacy_rss_url = str(raw_config.get("rss_url", "") or "").strip()
    if not source_tokens and legacy_rss_url and legacy_rss_url != LEGACY_GOOGLE_RSS_URL:
        source_tokens = [legacy_rss_url]

    if not source_tokens:
        source_tokens = _default_source_tokens()

    sources = tuple(_resolve_source_token(token, dailyhot_base_url) for token in source_tokens)
    return NewsConfig(
        sources=sources,
        max_items=_coerce_int(raw_config.get("max_items"), DEFAULT_MAX_ITEMS),
        request_timeout_seconds=_coerce_int(raw_config.get("request_timeout_seconds"), DEFAULT_TIMEOUT_SECONDS),
        enable_fallback_commands=_coerce_bool(raw_config.get("enable_fallback_commands"), True),
    )


class NewsFeedClient:
    def __init__(self, config: NewsConfig):
        self.config = config

    def fetch_headlines(self, limit: int | None = None) -> tuple[str, list[NewsHeadline]]:
        max_items = _coerce_int(limit, self.config.max_items) if limit else self.config.max_items
        if not self.config.sources:
            raise NewsFetchError(["未配置可用的新闻源。"])

        source_limit = max(1, (max_items + len(self.config.sources) - 1) // len(self.config.sources))
        per_source_results: list[tuple[NewsSource, NewsSourceResult]] = []
        errors: list[str] = []

        for source in self.config.sources:
            try:
                result = self._fetch_from_source(source, source_limit)
            except (HTTPError, URLError, ValueError, json.JSONDecodeError, ElementTree.ParseError) as exc:
                errors.append(f"{source.display_name} 失败：{self._format_exception(exc)}")
                continue
            except Exception as exc:
                errors.append(f"{source.display_name} 失败：{exc}")
                continue

            if result.items:
                per_source_results.append((source, result))
            else:
                errors.append(f"{source.display_name} 没有返回可展示的头条。")

        merged_items, used_titles = self._merge_results(per_source_results, max_items)
        if merged_items:
            feed_title = "今日新闻（来源：" + "、".join(used_titles) + "）"
            return feed_title, merged_items

        raise NewsFetchError(errors or ["所有新闻源都没有返回可展示内容。"])

    def _fetch_from_source(self, source: NewsSource, limit: int) -> NewsSourceResult:
        payload = self._read(source.endpoint)
        if source.source_type == "dailyhot":
            return self._parse_dailyhot_source(source, payload, limit)
        return self._parse_feed_source(source, payload, limit)

    def _read(self, url: str) -> bytes:
        request = Request(url, headers={"User-Agent": "AstrBotDailyNews/0.2"})
        with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
            return response.read()

    def _parse_dailyhot_source(self, source: NewsSource, payload: bytes, limit: int) -> NewsSourceResult:
        data = json.loads(payload.decode("utf-8", errors="replace"))
        feed_title = self._clean_text(str(data.get("title") or source.display_name))
        update_time = self._clean_text(str(data.get("updateTime") or ""))

        items: list[NewsHeadline] = []
        for entry in data.get("data") or []:
            if not isinstance(entry, Mapping):
                continue
            title = self._clean_text(str(entry.get("title") or ""))
            link = self._clean_text(str(entry.get("url") or entry.get("mobileUrl") or ""))
            if not title:
                continue
            items.append(
                NewsHeadline(
                    title=title,
                    link=link,
                    published_at=update_time,
                    source=feed_title,
                )
            )
            if len(items) >= limit:
                break
        return NewsSourceResult(feed_title=feed_title, items=tuple(items))

    def _parse_feed_source(self, source: NewsSource, payload: bytes, limit: int) -> NewsSourceResult:
        root = ElementTree.fromstring(payload)
        if self._local_name(root.tag) == "feed":
            return self._parse_atom_feed(source, root, limit)
        return self._parse_rss_feed(source, root, limit)

    def _parse_rss_feed(self, source: NewsSource, root: ElementTree.Element, limit: int) -> NewsSourceResult:
        channel = self._find_child(root, "channel")
        if channel is None and self._local_name(root.tag) == "channel":
            channel = root
        if channel is None:
            raise ValueError("RSS feed format is not supported or contains no channel node.")

        feed_title = self._clean_text(self._child_text(channel, "title")) or source.display_name
        items: list[NewsHeadline] = []
        for item in self._iter_children(channel, "item"):
            title = self._clean_text(self._child_text(item, "title"))
            link = self._clean_text(self._child_text(item, "link"))
            published_at = self._clean_text(self._child_text(item, "pubDate", "published"))
            source_name = self._clean_text(self._child_text(item, "source")) or source.display_name
            if not title:
                continue
            items.append(
                NewsHeadline(
                    title=title,
                    link=link,
                    published_at=published_at,
                    source=source_name,
                )
            )
            if len(items) >= limit:
                break
        return NewsSourceResult(feed_title=feed_title, items=tuple(items))

    def _parse_atom_feed(self, source: NewsSource, root: ElementTree.Element, limit: int) -> NewsSourceResult:
        feed_title = self._clean_text(self._child_text(root, "title")) or source.display_name
        items: list[NewsHeadline] = []
        for entry in self._iter_children(root, "entry"):
            title = self._clean_text(self._child_text(entry, "title"))
            link = self._extract_atom_link(entry)
            published_at = self._clean_text(self._child_text(entry, "updated", "published"))
            if not title:
                continue
            items.append(
                NewsHeadline(
                    title=title,
                    link=link,
                    published_at=published_at,
                    source=source.display_name,
                )
            )
            if len(items) >= limit:
                break
        return NewsSourceResult(feed_title=feed_title, items=tuple(items))

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

    @staticmethod
    def _iter_children(node: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
        return [child for child in list(node) if NewsFeedClient._local_name(child.tag) == local_name]

    @staticmethod
    def _find_child(node: ElementTree.Element, local_name: str) -> ElementTree.Element | None:
        for child in list(node):
            if NewsFeedClient._local_name(child.tag) == local_name:
                return child
        return None

    @staticmethod
    def _child_text(node: ElementTree.Element, *names: str) -> str:
        for child in list(node):
            if NewsFeedClient._local_name(child.tag) in names and child.text:
                return child.text
        return ""

    @staticmethod
    def _extract_atom_link(node: ElementTree.Element) -> str:
        for child in list(node):
            if NewsFeedClient._local_name(child.tag) != "link":
                continue
            href = child.attrib.get("href", "")
            rel = child.attrib.get("rel", "")
            if href and rel in {"", "alternate"}:
                return href
        return ""

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _clean_text(value: str) -> str:
        cleaned = html.unescape(value or "").strip()
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        if isinstance(exc, HTTPError):
            return f"HTTP {exc.code}"
        if isinstance(exc, URLError):
            return str(getattr(exc, "reason", exc))
        return str(exc)


@register(
    "astrbot_plugin_daily_news",
    "YARIZM",
    "Daily News plugin for AstrBot",
    "0.2.0",
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
        if not self.config.enable_fallback_commands:
            yield event.plain_result("管理员已关闭 /news 命令入口。")
            event.stop_event()
            return
        yield event.plain_result(self._fetch_and_render(limit if limit > 0 else None))
        event.stop_event()

    @filter.llm_tool(name="news_fetch_daily_headlines")
    async def llm_fetch_daily_headlines(self, event: AstrMessageEvent, limit: int = 0):
        """Fetch today's top headlines from the configured sources.
        Use when the user asks for today's news, latest headlines, daily briefing, or current affairs summary.
        Common requests include: 今日新闻, 今天有什么新闻, 给我一份今日快讯, 最新头条.
        Args:
            limit(number): Optional max number of headlines to return. Uses plugin default when omitted or 0.
        """
        safe_limit = _coerce_int(limit, 0)
        return self._fetch_and_render(safe_limit if safe_limit > 0 else None)

    def _fetch_and_render(self, limit: int | None) -> str:
        try:
            feed_title, items = self.client.fetch_headlines(limit=limit)
        except NewsFetchError as exc:
            details = "；".join(exc.messages[:3]) if exc.messages else "没有可用的新闻源。"
            return f"获取新闻失败：{details}"
        except Exception as exc:
            return f"获取新闻失败：{exc}"

        if not items:
            return "当前新闻源没有返回可展示的头条。"

        return self._render_headlines(feed_title, items)

    @staticmethod
    def _render_headlines(feed_title: str, items: list[NewsHeadline]) -> str:
        lines = [feed_title]
        for index, item in enumerate(items, start=1):
            suffix = f" ({item.source})" if item.source else ""
            lines.append(f"{index}. {item.title}{suffix}")
            if item.published_at:
                lines.append(f"   发布时间：{item.published_at}")
            if item.link:
                lines.append(f"   链接：{item.link}")
        return "\n".join(lines)

    def _help_text(self) -> str:
        source_names = "、".join(source.display_name for source in self.config.sources) or "未配置"
        return "\n".join(
            [
                "Daily News commands:",
                "/news today [count]",
                "/news help",
                "",
                f"当前新闻源：{source_names}",
                "",
                "自然语言示例：",
                "今天有什么新闻",
                "给我一份今日快讯",
                "抓取 3 条头条新闻",
            ]
        )
