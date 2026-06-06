"""内置新闻源注册表和分类映射。"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 内置新闻源
# tuple: (source_id, display_name, source_type, endpoint, category)
# ---------------------------------------------------------------------------

BUILTIN_SOURCES: dict[str, tuple[str, str, str, str, str]] = {
    # —— RSS 源（科技） ——
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
        "https://www.cnbeta.com.tw/backend.php", "tech",
    ),
    "v2ex": (
        "v2ex", "V2EX", "rss",
        "https://www.v2ex.com/index.xml", "tech",
    ),
    # —— DailyHot 源（综合资讯） ——
    "thepaper-hot": (
        "thepaper-hot", "澎湃新闻热榜", "dailyhot",
        "thepaper", "news",
    ),
    "toutiao": (
        "toutiao", "今日头条", "dailyhot",
        "toutiao", "news",
    ),
    # —— DailyHot 源（娱乐） ——
    "douyin": (
        "douyin", "抖音热点", "dailyhot",
        "douyin", "entertainment",
    ),
    # —— DailyHot 源（科技） ——
    "juejin": (
        "juejin", "掘金热榜", "dailyhot",
        "juejin", "tech",
    ),
    "sspai": (
        "sspai", "少数派", "dailyhot",
        "sspai", "tech",
    ),
}

# 分类显示名称（中文）
CATEGORY_NAMES: dict[str, str] = {
    "tech": "科技",
    "entertainment": "娱乐",
    "news": "综合资讯",
}
