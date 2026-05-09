# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AstrBot 新闻插件（`astrbot_plugin_daily_news`），从多个国内新闻源聚合头条，支持 RSS 和 DailyHot 两种数据源类型。通过 AstrBot 插件系统注册，提供 `/news` 命令组和 LLM Tool 两种调用方式。

## Architecture

整个插件只有一个主文件 [main.py](astrbot_plugin_daily_news/main.py)，无外部 Python 依赖（仅用 stdlib）。

**数据层**：
- `NewsSource` / `NewsConfig` / `NewsHeadline` / `NewsSourceResult` — 不可变数据类，描述新闻源配置和解析结果
- `BUILTIN_SOURCES` — 内置源字典，key 为 source_id，value 为 `(id, 显示名, 类型, endpoint)` 元组
- `news_config_from_mapping()` — 将 AstrBot 传入的原始 dict 配置解析为 `NewsConfig`，兼容旧版 `rss_url` 字段

**抓取层**：
- `NewsFeedClient` — 核心客户端，负责 HTTP 请求 + 解析 + 多源合并
- 支持三种 source token 格式：内置 ID（如 `36kr-newsflash`）、`dailyhot:<route>`、`rss:<url>` 或裸 URL
- RSS 解析同时支持 RSS 2.0 和 Atom 格式
- `_merge_results()` 按轮询方式从各源交错取条目，基于 link/title 去重

**插件层**：
- `DailyNewsPlugin(Star)` — 通过 `@register` 装饰器注册到 AstrBot
- `@filter.command_group("news")` 注册 `/news` 命令组，子命令 `today` 和 `help`
- `@filter.llm_tool` 注册 LLM 工具 `news_fetch_daily_headlines`，供 AI Agent 自然语言调用

## Key Patterns

- 所有数据类使用 `@dataclass(frozen=True)`，不可变设计
- `try/except ModuleNotFoundError` 块（第 13-68 行）提供 AstrBot API 的本地 fallback 存根，使文件可脱离 AstrBot 环境做语法检查
- 配置解析全部通过 `_coerce_*` 辅助函数做类型安全转换，容忍各种输入格式
- HTTP 请求仅用 `urllib.request`，不依赖 requests/httpx

## Configuration

配置通过 AstrBot 管理界面传入，schema 定义在 [_conf_schema.json](astrbot_plugin_daily_news/_conf_schema.json)：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source_ids` | string | `36kr-newsflash,ithome,cnbeta` | 逗号/换行分隔的新闻源列表 |
| `dailyhot_base_url` | string | `https://api-hot.imsyy.top` | DailyHot API 基地址 |
| `rss_url` | string | (空) | 旧版兼容字段，source_ids 为空时生效 |
| `max_items` | int | 5 | 返回条目上限 |
| `request_timeout_seconds` | int | 10 | HTTP 超时秒数 |
| `enable_fallback_commands` | bool | true | 是否启用 /news 命令 |

## Development

插件目录为 `astrbot_plugin_daily_news/`，元数据在 [metadata.yaml](astrbot_plugin_daily_news/metadata.yaml)，要求 AstrBot `>=4.16,<5`。

无测试套件、无 linter 配置、无构建步骤。修改后直接部署到 AstrBot 实例的 plugins 目录即可生效。

`requirements.txt` 为空，插件仅依赖 Python 标准库。
