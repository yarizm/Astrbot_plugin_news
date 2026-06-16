# daily-news-core

Core library for multi-source news aggregation with RSS, Atom, and DailyHot support.

## Features

- **Multi-source aggregation**: Fetch headlines from multiple RSS/Atom feeds and DailyHot-compatible APIs
- **Async HTTP client**: Built on aiohttp with retry and exponential backoff
- **Smart caching**: Per-source TTL configuration for optimal refresh rates
- **Health monitoring**: Automatic source failure detection and recovery
- **History tracking**: Deduplication with TTL-based cleanup
- **Scheduling**: Built-in subscription scheduler for timed push notifications
- **User preferences**: Per-session configuration storage
- **Markdown rendering**: Platform-adaptive output (plain text, Telegram, Discord)

## Installation

```bash
pip install daily-news-core
```

## Quick Start

```python
import asyncio
from daily_news_core import NewsFeedClient, news_config_from_mapping

async def main():
    # Configure news sources
    config = news_config_from_mapping({
        "新闻源": "36kr-newsflash,ithome,cnbeta",
        "最大条数": 5,
    })

    # Create client and fetch headlines
    client = NewsFeedClient(config)
    title, items = await client.fetch_headlines()

    print(title)
    for item in items:
        print(f"  {item.title} - {item.link}")

    await client.close()

asyncio.run(main())
```

## Supported Sources

### Built-in Sources

| ID | Name | Type | Category |
|---|---|---|---|
| 36kr-newsflash | 36氪快讯 | RSS | Tech |
| 36kr | 36氪综合资讯 | RSS | Tech |
| ithome | IT之家 | RSS | Tech |
| cnbeta | cnBeta | RSS | Tech |
| v2ex | V2EX | RSS | Tech |
| thepaper-hot | 澎湃新闻热榜 | DailyHot | News |
| toutiao | 今日头条 | DailyHot | News |
| douyin | 抖音热点 | DailyHot | Entertainment |
| juejin | 掘金热榜 | DailyHot | Tech |
| sspai | 少数派 | DailyHot | Tech |

### Custom Sources

```python
config = news_config_from_mapping({
    "自定义源": '''[
        {
            "id": "my-rss",
            "name": "My RSS Feed",
            "type": "rss",
            "endpoint": "https://example.com/feed.xml"
        }
    ]''',
    "新闻源": "36kr-newsflash,my-rss",
})
```

## License

MIT
