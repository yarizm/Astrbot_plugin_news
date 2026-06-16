"""core 包：新闻插件的核心逻辑。"""
from __future__ import annotations

from .cache_backend import CacheBackend, CacheEntry, MemoryCache, RedisCache, create_cache_backend
from .client import NewsFeedClient
from .config import (
    coerce_bool,
    coerce_int,
    coerce_source_tokens,
    news_config_from_mapping,
    resolve_source_token,
)
from .history import NewsHistory
from .models import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_DAILYHOT_BASE_URL,
    DEFAULT_MAX_ITEMS,
    DEFAULT_SOURCE_IDS,
    DEFAULT_TIMEOUT_SECONDS,
    NewsConfig,
    NewsFetchError,
    NewsHeadline,
    NewsSource,
    NewsSourceResult,
)
from .parsers import clean_text, truncate_summary
from .renderer import HeadlineRenderer, default_renderer
from .scheduler import NewsScheduler, SubscriptionRecord
from .sources import BUILTIN_SOURCES, CATEGORY_NAMES
from .user_prefs import UserPrefs, UserPrefsStore
from .webhook import WebhookConfig, WebhookHandler, WebhookPayload, WebhookStore, WebhookVerifier

__all__ = [
    # 缓存后端
    "CacheBackend",
    "CacheEntry",
    "MemoryCache",
    "RedisCache",
    "create_cache_backend",
    # 客户端
    "NewsFeedClient",
    # 配置
    "news_config_from_mapping",
    "resolve_source_token",
    "coerce_bool",
    "coerce_int",
    "coerce_source_tokens",
    # 数据模型
    "NewsSource",
    "NewsConfig",
    "NewsHeadline",
    "NewsSourceResult",
    "NewsFetchError",
    # 常量
    "BUILTIN_SOURCES",
    "CATEGORY_NAMES",
    "DEFAULT_SOURCE_IDS",
    "DEFAULT_DAILYHOT_BASE_URL",
    "DEFAULT_MAX_ITEMS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_CACHE_TTL_SECONDS",
    # 工具
    "clean_text",
    "truncate_summary",
    # 持久化
    "NewsHistory",
    # 调度器
    "NewsScheduler",
    "SubscriptionRecord",
    # 用户偏好
    "UserPrefs",
    "UserPrefsStore",
    # 渲染器
    "HeadlineRenderer",
    "default_renderer",
    # Webhook
    "WebhookConfig",
    "WebhookHandler",
    "WebhookPayload",
    "WebhookStore",
    "WebhookVerifier",
]
