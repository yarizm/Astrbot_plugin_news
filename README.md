# astrbot_plugin_daily_news

AstrBot 多源新闻聚合插件，从国内科技资讯站点抓取头条，支持 RSS/Atom 和 DailyHot 两种数据源类型。

## 功能

- 聚合多个新闻源，轮询取条目并自动去重
- 支持内置源、自定义 RSS 源、自定义 DailyHot 热榜源
- 提供 `/news` 命令组和 LLM Tool 两种调用方式
- 零外部依赖，仅使用 Python 标准库

## 安装

将 `astrbot_plugin_daily_news` 目录放入 AstrBot 的 plugins 目录，重启 AstrBot。

要求 AstrBot `>=4.16,<5`。

## 命令

| 命令 | 说明 |
|------|------|
| `/news today [数量]` | 获取今日新闻，可选指定条数 |
| `/news help` | 显示帮助信息 |

自然语言调用（通过 LLM Tool）：「今天有什么新闻」「给我一份今日快讯」「抓取 3 条头条新闻」

## 配置

在 AstrBot 管理界面的插件配置中设置：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| 新闻源 | string | `36kr-newsflash,ithome,cnbeta` | 新闻来源列表，逗号或换行分隔 |
| 自定义源 | string | `[]` | 自定义新闻源定义（JSON 数组） |
| 每日热榜地址 | string | `https://api-hot.imsyy.top` | DailyHot API 基地址 |
| 旧版RSS地址 | string | (空) | 兼容字段，仅在「新闻源」为空时生效 |
| 最大条数 | int | 5 | 每次返回条目上限 |
| 请求超时 | int | 10 | HTTP 超时秒数 |
| 启用命令 | bool | true | 是否启用 /news today 命令 |

### 内置新闻源

在「新闻源」中直接填写 ID 即可使用：

| ID | 名称 | 类型 |
|----|------|------|
| `36kr-newsflash` | 36氪快讯 | RSS |
| `36kr` | 36氪综合资讯 | RSS |
| `ithome` | IT之家 | RSS |
| `cnbeta` | cnBeta | RSS |
| `qq-news-hot` | 腾讯新闻热榜 | DailyHot |
| `thepaper-hot` | 澎湃新闻热榜 | DailyHot |

### 自定义新闻源

在「自定义源」中填写 JSON 数组，每个元素包含：

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 唯一标识，用于在「新闻源」中引用 |
| `name` | 否 | 显示名称，缺省使用 id |
| `type` | 是 | `rss` 或 `dailyhot` |
| `endpoint` | 是 | RSS 地址或 DailyHot 路由名 |

示例：

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

定义后，在「新闻源」中填入 `my-rss,zhihu-hot` 即可与内置源混合使用。

### 内联格式（无需预先定义）

在「新闻源」中也可以直接使用内联格式，无需先定义自定义源：

- RSS：`rss:https://example.com/feed.xml` 或直接填 URL
- DailyHot：`dailyhot:zhihu`

## 支持平台

qq_official、aiocqhttp、telegram、discord
