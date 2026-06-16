"""数据模型、异常和常量定义。"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 默认值常量
# ---------------------------------------------------------------------------

LEGACY_GOOGLE_RSS_URL = "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"

DEFAULT_SOURCE_IDS = (
    "36kr-newsflash",
    "ithome",
    "cnbeta",
)
DEFAULT_DAILYHOT_BASE_URL = "https://dailyhot-api.vercel.app"
DEFAULT_MAX_ITEMS = 5
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_CACHE_TTL_SECONDS = 900  # 15 分钟
MAX_RETRIES = 2  # 最大重试次数
SOURCE_HEALTH_THRESHOLD = 3  # 连续失败次数阈值，超过后临时跳过
SOURCE_RECOVERY_SECONDS = 1800  # 源恢复等待时间（30 分钟）


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NewsSource:
    source_id: str
    display_name: str
    source_type: str
    endpoint: str
    description: str = ""
    category: str = ""
    suggested_ttl: int = 0  # 源建议的缓存 TTL（秒），0 表示使用全局配置


@dataclass(frozen=True)
class NewsConfig:
    sources: tuple[NewsSource, ...]
    max_items: int = DEFAULT_MAX_ITEMS
    request_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    enable_fallback_commands: bool = True
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    enable_ai_summary: bool = False
    ai_summary_prompt: str = "请用不超过30字概括以下新闻标题的核心内容："
    redis_url: str = ""


@dataclass(frozen=True)
class NewsHeadline:
    title: str
    link: str
    published_at: str = ""
    source: str = ""
    summary: str = ""


@dataclass(frozen=True)
class NewsSourceResult:
    feed_title: str
    items: tuple[NewsHeadline, ...]


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class NewsFetchError(RuntimeError):
    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("；".join(messages))
