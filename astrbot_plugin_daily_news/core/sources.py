"""内置新闻源注册表和分类映射。"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 内置新闻源
# tuple: (source_id, display_name, source_type, endpoint, category)
# ---------------------------------------------------------------------------

BUILTIN_SOURCES: dict[str, tuple[str, str, str, str, str]] = {
    # —— RSS 源 ——
    "36kr-newsflash": (
        "36kr-newsflash", "36氪快讯", "rss",
        "https://36kr.com/feed-newsflash", "tech",
    ),
    "36kr": (
        "36kr", "36氪综合资讯", "rss",
        "https://36kr.com/feed", "tech",
    ),
    "ithome": (
        "ithome", "IT之家", "rss",
        "https://www.ithome.com/rss/", "tech",
    ),
    "cnbeta": (
        "cnbeta", "cnBeta", "rss",
        "http://rss.cnbeta.com/", "tech",
    ),
    # —— DailyHot 源（综合资讯） ——
    "qq-news-hot": (
        "qq-news-hot", "腾讯新闻热榜", "dailyhot",
        "qq-news", "news",
    ),
    "thepaper-hot": (
        "thepaper-hot", "澎湃新闻热榜", "dailyhot",
        "thepaper", "news",
    ),
    "toutiao": (
        "toutiao", "今日头条", "dailyhot",
        "toutiao", "news",
    ),
    # —— DailyHot 源（社交） ——
    "weibo": (
        "weibo", "微博热搜", "dailyhot",
        "weibo", "social",
    ),
    "zhihu": (
        "zhihu", "知乎热榜", "dailyhot",
        "zhihu", "social",
    ),
    "baidu": (
        "baidu", "百度热搜", "dailyhot",
        "baidu", "social",
    ),
    # —— DailyHot 源（娱乐） ——
    "bilibili": (
        "bilibili", "B站热门", "dailyhot",
        "bilibili", "entertainment",
    ),
    "douyin": (
        "douyin", "抖音热点", "dailyhot",
        "douyin", "entertainment",
    ),
    # —— DailyHot 源（科技） ——
    "juejin": (
        "juejin", "掘金热榜", "dailyhot",
        "juejin", "tech",
    ),
    "v2ex": (
        "v2ex", "V2EX", "dailyhot",
        "v2ex", "tech",
    ),
    "sspai": (
        "sspai", "少数派", "dailyhot",
        "sspai", "tech",
    ),
    # —— DailyHot 源（财经） ——
    "huxiu": (
        "huxiu", "虎嗅", "dailyhot",
        "huxiu", "finance",
    ),
}

# 分类显示名称（中文）
CATEGORY_NAMES: dict[str, str] = {
    "tech": "科技",
    "social": "社交",
    "entertainment": "娱乐",
    "finance": "财经",
    "news": "综合资讯",
}
