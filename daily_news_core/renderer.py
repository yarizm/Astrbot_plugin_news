"""新闻标题渲染器：支持纯文本和 Markdown 格式。"""
from __future__ import annotations

from .models import NewsHeadline


class HeadlineRenderer:
    """根据平台类型选择渲染格式。"""

    # 支持 Markdown 的平台
    MARKDOWN_PLATFORMS = {"telegram", "discord", "slack", "matrix"}

    def render(
        self,
        title: str,
        items: list[NewsHeadline],
        platform: str = "plain",
    ) -> str:
        """渲染新闻标题列表。

        Args:
            title: 标题文本
            items: 新闻条目列表
            platform: 平台类型（plain/telegram/discord/slack/matrix）
        """
        if platform.lower() in self.MARKDOWN_PLATFORMS:
            return self._render_markdown(title, items)
        return self._render_plain(title, items)

    def _render_plain(self, title: str, items: list[NewsHeadline]) -> str:
        """纯文本渲染。"""
        lines = [title]
        for index, item in enumerate(items, start=1):
            suffix = f" ({item.source})" if item.source else ""
            lines.append(f"{index}. {item.title}{suffix}")
            if item.summary:
                lines.append(f"   摘要：{item.summary}")
            if item.published_at:
                lines.append(f"   发布时间：{item.published_at}")
            if item.link:
                lines.append(f"   链接：{item.link}")
        return "\n".join(lines)

    def _render_markdown(self, title: str, items: list[NewsHeadline]) -> str:
        """Markdown 渲染（Telegram/Discord）。"""
        lines = [f"**{title}**", ""]
        for index, item in enumerate(items, start=1):
            source_tag = f" `{item.source}`" if item.source else ""
            if item.link:
                lines.append(f"{index}. [{item.title}]({item.link}){source_tag}")
            else:
                lines.append(f"{index}. {item.title}{source_tag}")
            if item.summary:
                lines.append(f"   > {item.summary}")
            if item.published_at:
                lines.append(f"   📅 {item.published_at}")
            lines.append("")
        return "\n".join(lines).rstrip()


# 默认渲染器实例
default_renderer = HeadlineRenderer()
