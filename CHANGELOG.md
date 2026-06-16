# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **P1-1**: 定时推送 / 早报订阅功能
  - 新增 `daily_news_core/scheduler.py` 模块：`NewsScheduler` 调度器 + `SubscriptionRecord` 订阅记录
  - 新增 `/news subscribe <时间> [分类] [条数]` 命令：订阅定时推送
  - 新增 `/news unsubscribe` 命令：取消订阅
  - 新增 `/news subscriptions` 命令：查看订阅信息
  - 订阅记录持久化到 `subscriptions.json`，插件重启后自动恢复
  - 支持按分类订阅（如 `/news subscribe 08:00 tech`）

- **P2-1**: LLM AI 摘要功能
  - 新增配置项 `启用AI摘要`（默认 false）和 `AI摘要提示词`
  - 启用后调用 AstrBot LLM Provider 为新闻标题生成一句话摘要
  - 并发限制（semaphore=3）避免大量 LLM 调用

- **P2-2**: 用户级个性化订阅
  - 新增 `daily_news_core/user_prefs.py` 模块：`UserPrefs` + `UserPrefsStore`
  - 新增 `/news prefer` 命令：设置个人偏好分类和源
  - 用户偏好持久化到 `user_prefs.json`

- **P2-4**: 新闻搜索命令
  - 新增 `/news search <关键词>` 命令：在已缓存条目中搜索

- **P3-1**: 独立包结构
  - 新增 `daily-news-core/` 目录：`pyproject.toml` + `README.md`
  - 可独立发布到 PyPI

- **P3-2**: Redis 缓存后端
  - 新增 `daily_news_core/cache_backend.py`：`CacheBackend` 协议 + `MemoryCache` + `RedisCache`
  - 新增配置项 `Redis地址`，空则使用内存缓存

- **P3-3**: Webhook 推送接入
  - 新增 `daily_news_core/webhook.py`：`WebhookHandler` + `WebhookStore` + `WebhookVerifier`
  - 支持 HMAC-SHA256 签名验证

### Changed
- **P1-2**: 按源独立缓存 — 每个新闻源可配置独立的缓存 TTL
  - `NewsSource` 新增 `suggested_ttl` 字段（源建议的缓存秒数，0 表示使用全局配置）
  - 高频源（抖音 5 分钟、热榜 10 分钟）和低频源（RSS 30 分钟）差异化缓存
  - 缓存命中检查改为使用条目级别的 TTL，而非全局统一值

- **P2-3**: Markdown 富文本渲染
  - 新增 `daily_news_core/renderer.py`：`HeadlineRenderer` 支持 plain/telegram/discord 格式
  - `_render_headlines` 方法改为使用渲染器，支持平台自适应

### Added (测试)
- **P1-3**: 单元测试套件 — 126 个测试用例，覆盖核心模块（77% 覆盖率）
  - `tests/test_models.py` — 数据模型、常量、异常测试
  - `tests/test_config.py` — 配置解析、类型转换、源解析测试
  - `tests/test_parsers.py` — RSS/Atom/DailyHot 解析器测试（含 fixtures）
  - `tests/test_history.py` — 去重历史、TTL 清理、v1 迁移测试
  - `tests/test_scheduler.py` — 定时调度器、订阅记录、持久化测试
  - `tests/test_client.py` — 缓存、健康检查、单源抓取、合并去重测试（mock aiohttp）
  - 新增 `requirements-test.txt` 测试依赖

### Fixed
- **P0-1**: 数据目录写权限问题 — 实现三层降级策略（StarTools API → CWD 相对路径 → 用户 home 目录），解决容器化部署和热重载场景下的 `PermissionError`
- **P0-2**: 去重历史文件无界增长 — 从 `set[str]` 迁移至 `dict[str, float]`（链接→时间戳），新增 TTL 清理（30 天）和容量上限（5000 条），支持 v1 格式自动迁移
- **TD-01/TD-02**: 修正 `metadata.yaml` 和 `main.py` 中的仓库地址（`EuxrvshPVPBOTv0.01` → `Astrbot_plugin_news`）
- **TD-03**: 为 `_conf_schema.json` 中的「旧版RSS地址」字段添加 `deprecated: true` 标注
- **TD-05**: 新增 `CHANGELOG.md` 版本说明

## [0.4.0] - 2026-06-07

### Added
- 多源聚合架构：支持 16 个内置新闻源（36kr、ithome、cnbeta、v2ex、thepaper、toutiao、douyin、juejin、sspai 等）
- 异步数据抓取（`aiohttp`）
- DailyHot API 兼容支持
- 自定义源配置（JSON 数组格式）
- `/news` 命令组（`today`、`help`）
- LLM Tool 注册（`news_fetch_daily_headlines`）
- 缓存机制（默认 15 分钟 TTL）
- 去重历史持久化

### Changed
- 目录结构扁平化：`astrbot_plugin_daily_news/core/` → `daily_news_core/`
- 改用相对导入，符合 AstrBot 插件规范

### Fixed
- 修复失效新闻源：cnBeta 改用 `backend.php`、DailyHot 迁移至 Vercel 部署、移除 6 个不可用源、v2ex 改为直接 RSS
- 修复 CI 源数量断言和 `CATEGORY_NAMES` 同步

## [0.3.0] - 2026-06-06

### Added
- 初始版本：单 RSS 源新闻插件
- 基础 `/news` 命令

---

[Unreleased]: https://github.com/yarizm/Astrbot_plugin_news/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/yarizm/Astrbot_plugin_news/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/yarizm/Astrbot_plugin_news/releases/tag/v0.3.0
