"""内置新闻源注册表和分类映射。"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 内置新闻源
# tuple: (source_id, display_name, source_type, endpoint, category, suggested_ttl)
# suggested_ttl: 源建议的缓存 TTL（秒），0 表示使用全局配置
# ---------------------------------------------------------------------------

BUILTIN_SOURCES: dict[str, tuple[str, str, str, str, str, int]] = {
    # —— RSS 源（科技） ——
    "36kr-newsflash": (
        "36kr-newsflash", "36氪快讯", "rss",
        "https://36kr.com/feed-newsflash", "tech",
        1800,  # 30 分钟：快讯更新频率适中
    ),
    "36kr": (
        "36kr", "36氪综合资讯", "rss",
        "https://36kr.com/feed", "tech",
        1800,  # 30 分钟
    ),
    "ithome": (
        "ithome", "IT之家", "rss",
        "https://www.ithome.com/rss/", "tech",
        1800,  # 30 分钟
    ),
    "cnbeta": (
        "cnbeta", "cnBeta", "rss",
        "https://www.cnbeta.com.tw/backend.php", "tech",
        1800,  # 30 分钟
    ),
    "v2ex": (
        "v2ex", "V2EX", "rss",
        "https://www.v2ex.com/index.xml", "tech",
        900,   # 15 分钟：社区讨论更新较快
    ),
    # —— DailyHot 源（综合资讯） ——
    "thepaper-hot": (
        "thepaper-hot", "澎湃新闻热榜", "dailyhot",
        "thepaper", "news",
        600,   # 10 分钟：热榜变化较快
    ),
    "toutiao": (
        "toutiao", "今日头条", "dailyhot",
        "toutiao", "news",
        600,   # 10 分钟
    ),
    # —— DailyHot 源（娱乐） ——
    "douyin": (
        "douyin", "抖音热点", "dailyhot",
        "douyin", "entertainment",
        300,   # 5 分钟：热点变化非常快
    ),
    # —— DailyHot 源（科技） ——
    "juejin": (
        "juejin", "掘金热榜", "dailyhot",
        "juejin", "tech",
        900,   # 15 分钟
    ),
    "sspai": (
        "sspai", "少数派", "dailyhot",
        "sspai", "tech",
        1800,  # 30 分钟
    ),
}

# 分类显示名称（中文）
CATEGORY_NAMES: dict[str, str] = {
    "tech": "科技",
    "entertainment": "娱乐",
    "news": "综合资讯",
}
