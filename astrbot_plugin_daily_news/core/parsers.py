"""RSS / Atom / DailyHot 数据解析工具函数。"""
from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from xml.etree import ElementTree

from .models import NewsHeadline, NewsSource, NewsSourceResult


# ---------------------------------------------------------------------------
# 文本清理工具
# ---------------------------------------------------------------------------

def clean_text(value: str) -> str:
    """清理 HTML 标签、实体和多余空白。"""
    cleaned = html.unescape(value or "").strip()
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def truncate_summary(text: str, max_chars: int = 120) -> str:
    """截断摘要文本到指定长度。"""
    if not text or len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# XML 工具方法
# ---------------------------------------------------------------------------

def local_name(tag: str) -> str:
    """去除 XML namespace 前缀，返回本地标签名。"""
    return tag.rsplit("}", 1)[-1]


def iter_children(node: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in list(node) if local_name(child.tag) == name]


def find_child(node: ElementTree.Element, name: str) -> ElementTree.Element | None:
    for child in list(node):
        if local_name(child.tag) == name:
            return child
    return None


def child_text(node: ElementTree.Element, *names: str) -> str:
    for child in list(node):
        if local_name(child.tag) in names and child.text:
            return child.text
    return ""


def extract_atom_link(node: ElementTree.Element) -> str:
    for child in list(node):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "")
        rel = child.attrib.get("rel", "")
        if href and rel in {"", "alternate"}:
            return href
    return ""


# ---------------------------------------------------------------------------
# DailyHot 解析
# ---------------------------------------------------------------------------

def parse_dailyhot_source(source: NewsSource, payload: bytes, limit: int) -> NewsSourceResult:
    data = json.loads(payload.decode("utf-8", errors="replace"))
    feed_title = clean_text(str(data.get("title") or source.display_name))
    update_time = clean_text(str(data.get("updateTime") or ""))

    items: list[NewsHeadline] = []
    for entry in data.get("data") or []:
        if not isinstance(entry, Mapping):
            continue
        title = clean_text(str(entry.get("title") or ""))
        link = clean_text(str(entry.get("url") or entry.get("mobileUrl") or ""))
        summary = clean_text(str(entry.get("description") or entry.get("summary") or ""))
        if not title:
            continue
        items.append(
            NewsHeadline(
                title=title,
                link=link,
                published_at=update_time,
                source=feed_title,
                summary=truncate_summary(summary, 120),
            )
        )
        if len(items) >= limit:
            break
    return NewsSourceResult(feed_title=feed_title, items=tuple(items))


# ---------------------------------------------------------------------------
# RSS 2.0 解析
# ---------------------------------------------------------------------------

def parse_rss_feed(source: NewsSource, root: ElementTree.Element, limit: int) -> NewsSourceResult:
    channel = find_child(root, "channel")
    if channel is None and local_name(root.tag) == "channel":
        channel = root
    if channel is None:
        raise ValueError("RSS feed format is not supported or contains no channel node.")

    feed_title = clean_text(child_text(channel, "title")) or source.display_name
    items: list[NewsHeadline] = []
    for item in iter_children(channel, "item"):
        title = clean_text(child_text(item, "title"))
        link = clean_text(child_text(item, "link"))
        published_at = clean_text(child_text(item, "pubDate", "published"))
        source_name = clean_text(child_text(item, "source")) or source.display_name
        raw_summary = child_text(item, "description", "summary", "content")
        summary = truncate_summary(clean_text(raw_summary), 120)
        if not title:
            continue
        items.append(
            NewsHeadline(
                title=title,
                link=link,
                published_at=published_at,
                source=source_name,
                summary=summary,
            )
        )
        if len(items) >= limit:
            break
    return NewsSourceResult(feed_title=feed_title, items=tuple(items))


# ---------------------------------------------------------------------------
# Atom 解析
# ---------------------------------------------------------------------------

def parse_atom_feed(source: NewsSource, root: ElementTree.Element, limit: int) -> NewsSourceResult:
    feed_title = clean_text(child_text(root, "title")) or source.display_name
    items: list[NewsHeadline] = []
    for entry in iter_children(root, "entry"):
        title = clean_text(child_text(entry, "title"))
        link = extract_atom_link(entry)
        published_at = clean_text(child_text(entry, "updated", "published"))
        raw_summary = child_text(entry, "summary", "content")
        summary = truncate_summary(clean_text(raw_summary), 120)
        if not title:
            continue
        items.append(
            NewsHeadline(
                title=title,
                link=link,
                published_at=published_at,
                source=source.display_name,
                summary=summary,
            )
        )
        if len(items) >= limit:
            break
    return NewsSourceResult(feed_title=feed_title, items=tuple(items))


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

def parse_feed_source(source: NewsSource, payload: bytes, limit: int) -> NewsSourceResult:
    """根据内容格式自动选择 RSS 或 Atom 解析器。"""
    root = ElementTree.fromstring(payload)
    if local_name(root.tag) == "feed":
        return parse_atom_feed(source, root, limit)
    return parse_rss_feed(source, root, limit)
