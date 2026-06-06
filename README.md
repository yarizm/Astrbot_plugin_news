# astrbot_plugin_daily_news

[![CI](https://github.com/yarizm/Astrbot_plugin_news/actions/workflows/ci.yml/badge.svg)](https://github.com/yarizm/Astrbot_plugin_news/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16-blue)](https://github.com/AstrBotDevs/AstrBot)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green)](https://www.python.org/)

AstrBot 多源新闻聚合插件，支持 16 个内置新闻源（RSS / DailyHot），按分类查询，带异步并发、TTL 缓存、自动重试和内容摘要提取。

## ✨ 功能特性

- **多源聚合**：16 个内置源 + 自定义 RSS / DailyHot 源，轮询取条目并自动去重
- **分类查询**：科技 / 社交 / 娱乐 / 财经 / 综合资讯 五大分类
- **异步并发**：基于 `aiohttp`，并行抓取所有源，响应迅速
- **TTL 缓存**：15 分钟内存缓存，失败时自动降级使用陈旧缓存
- **指数退避重试**：单次请求最多重试 2 次，源连续失败 3 次后临时跳过
- **内容摘要**：自动从 RSS description / DailyHot description 提取摘要
- **去重历史**：`/news new` 命令仅展示自上次查询以来的新条目
- **双入口**：`/news` 命令组 + 4 个 LLM Tool，自然语言直接调用

## 📦 安装

```bash
# 方式一：AstrBot 插件市场搜索 "Daily News" 安装
# 方式二：手动安装
git clone https://github.com/yarizm/Astrbot_plugin_news.git
# 将 astrbot_plugin_daily_news 目录复制到 AstrBot 的 data/plugins/ 目录
cp -r astrbot_plugin_daily_news /path/to/astrbot/data/plugins/
```

安装后在 AstrBot 管理面板启用插件，重启生效。

> **要求**：AstrBot `>=4.16,<5`，Python `>=3.10`

## 🚀 命令

| 命令 | 说明 |
|------|------|
| `/news today [数量]` | 获取今日新闻 |
| `/news category <分类> [数量]` | 按分类获取（如 `/news category tech 10`） |
| `/news new [数量]` | 仅展示自上次查询以来的新条目 |
| `/news sources` | 查看已配置的新闻源列表 |
| `/news help` | 显示帮助信息 |

### 自然语言调用（LLM Tool）

直接向 AI 说：

- "今天有什么新闻"
- "看看科技新闻"
- "给我知乎热榜"
- "有哪些新闻源"
- "给我 10 条娱乐新闻"

## 📰 内置新闻源

| ID | 名称 | 类型 | 分类 |
|----|------|------|------|
| `36kr-newsflash` | 36氪快讯 | RSS | 科技 |
| `36kr` | 36氪综合资讯 | RSS | 科技 |
| `ithome` | IT之家 | RSS | 科技 |
| `cnbeta` | cnBeta | RSS | 科技 |
| `juejin` | 掘金热榜 | DailyHot | 科技 |
| `v2ex` | V2EX | DailyHot | 科技 |
| `sspai` | 少数派 | DailyHot | 科技 |
| `weibo` | 微博热搜 | DailyHot | 社交 |
| `zhihu` | 知乎热榜 | DailyHot | 社交 |
| `baidu` | 百度热搜 | DailyHot | 社交 |
| `bilibili` | B站热门 | DailyHot | 娱乐 |
| `douyin` | 抖音热点 | DailyHot | 娱乐 |
| `huxiu` | 虎嗅 | DailyHot | 财经 |
| `qq-news-hot` | 腾讯新闻热榜 | DailyHot | 综合资讯 |
| `thepaper-hot` | 澎湃新闻热榜 | DailyHot | 综合资讯 |
| `toutiao` | 今日头条 | DailyHot | 综合资讯 |

> DailyHot 源基于 [DailyHot API](https://github.com/imsyy/DailyHotApi)，支持 45+ 平台，可在「每日热榜地址」中配置自建实例。

## ⚙️ 配置

在 AstrBot 管理面板的插件配置中设置：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| 新闻源 | string | `36kr-newsflash,ithome,cnbeta` | 新闻来源列表，逗号或换行分隔 |
| 自定义源 | string | `[]` | 自定义源定义（JSON 数组） |
| 每日热榜地址 | string | `https://api-hot.imsyy.top` | DailyHot API 基地址 |
| 旧版RSS地址 | string | (空) | 向后兼容字段 |
| 最大条数 | int | 5 | 每次返回条目上限 |
| 请求超时 | int | 10 | HTTP 超时秒数 |
| 启用命令 | bool | true | 是否启用 `/news` 命令入口 |
| 缓存有效期 | int | 900 | 缓存 TTL（秒），设为 0 禁用 |

### 自定义新闻源

在「自定义源」中填写 JSON 数组：

```json
[
  {
    "id": "my-rss",
    "name": "我的 RSS 源",
    "type": "rss",
    "endpoint": "https://example.com/feed.xml"
  },
  {
    "id": "zhihu-hot",
    "name": "知乎热榜",
    "type": "dailyhot",
    "endpoint": "zhihu"
  }
]
```

定义后在「新闻源」中填入 `my-rss,zhihu-hot` 即可与内置源混合使用。

### 内联格式（无需预先定义）

直接在「新闻源」字段中使用：

- RSS：`rss:https://example.com/feed.xml` 或直接填 URL
- DailyHot：`dailyhot:zhihu`

## 🏗️ 项目结构

```
astrbot_plugin_daily_news/
├── __init__.py
├── main.py              # AstrBot 插件入口（兼容层 + 命令/Tool 注册）
├── _conf_schema.json    # AstrBot 配置 schema
├── metadata.yaml        # 插件元数据
├── requirements.txt     # Python 依赖
└── core/                # 核心逻辑子包
    ├── __init__.py      # 统一导出
    ├── models.py        # 数据类 + 异常 + 常量
    ├── sources.py       # 内置源注册表 + 分类映射
    ├── config.py        # 配置解析（类型转换 + 向后兼容）
    ├── parsers.py       # RSS / Atom / DailyHot 解析
    ├── client.py        # 异步抓取客户端（缓存 + 重试 + 并发）
    └── history.py       # JSON 持久化（去重历史）
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 许可证

[MIT License](LICENSE)
