# Contributing to astrbot_plugin_daily_news

感谢你对本项目的关注！欢迎提交 Issue 和 Pull Request。

## 开发环境

```bash
git clone https://github.com/yarizm/Astrbot_plugin_news.git
cd Astrbot_plugin_news
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r astrbot_plugin_daily_news/requirements.txt
pip install ruff
```

## 代码规范

- 使用 `ruff` 进行代码检查：`ruff check astrbot_plugin_daily_news/`
- 遵循 PEP 8，行宽限制放宽到 100 字符
- 所有新功能需通过 `python -m ast` 语法检查
- 核心逻辑放在 `core/` 子包中，`main.py` 仅保留 AstrBot 适配层

## 提交 PR 前

1. 确保 `ruff check` 无报错
2. 确保所有 `.py` 文件可通过 `ast.parse` 语法检查
3. 若新增了内置源，在 `core/sources.py` 中注册并在 `_conf_schema.json` 描述中补充
4. 若修改了配置字段，同步更新 `_conf_schema.json` 和 `README.md`

## 项目结构

```
astrbot_plugin_daily_news/
├── main.py           # AstrBot 插件入口
├── core/             # 核心逻辑
│   ├── models.py     # 数据类 + 常量
│   ├── sources.py    # 内置源 + 分类
│   ├── config.py     # 配置解析
│   ├── parsers.py    # 数据解析
│   ├── client.py     # 异步客户端
│   └── history.py    # 持久化
├── _conf_schema.json # 配置 schema
├── metadata.yaml     # 插件元数据
└── requirements.txt  # 依赖
```
