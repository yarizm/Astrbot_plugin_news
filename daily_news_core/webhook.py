"""Webhook 服务器：接收外部推送的新闻数据。"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

_logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    """Webhook 配置。"""
    source_id: str  # 关联的新闻源 ID
    secret: str  # 验证密钥
    enabled: bool = True
    max_items: int = 20  # 单次推送最大条目数


@dataclass
class WebhookPayload:
    """Webhook 推送的数据。"""
    source_id: str
    items: list[dict[str, Any]]
    timestamp: float = field(default_factory=time.time)
    signature: str = ""


class WebhookVerifier:
    """Webhook 签名验证器。"""

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def generate_signature(self, payload: bytes) -> str:
        """生成 HMAC-SHA256 签名。"""
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """验证签名。"""
        expected = self.generate_signature(payload)
        return hmac.compare_digest(expected, signature)


class WebhookStore:
    """Webhook 配置存储。"""

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "webhooks.json"
        self._configs: dict[str, WebhookConfig] = {}
        self._load()

    def get_config(self, source_id: str) -> WebhookConfig | None:
        """获取 Webhook 配置。"""
        return self._configs.get(source_id)

    def add_config(self, config: WebhookConfig) -> None:
        """添加或更新 Webhook 配置。"""
        self._configs[config.source_id] = config
        self._persist()
        _logger.info("Webhook 配置已添加: %s", config.source_id)

    def remove_config(self, source_id: str) -> bool:
        """删除 Webhook 配置。"""
        removed = self._configs.pop(source_id, None)
        if removed is not None:
            self._persist()
            _logger.info("Webhook 配置已删除: %s", source_id)
            return True
        return False

    def get_all_configs(self) -> list[WebhookConfig]:
        """获取所有 Webhook 配置。"""
        return list(self._configs.values())

    def _load(self) -> None:
        """从 JSON 文件加载配置。"""
        if not self._file.exists():
            return
        try:
            with self._file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "source_id" in item:
                        config = WebhookConfig(
                            source_id=item["source_id"],
                            secret=item.get("secret", ""),
                            enabled=item.get("enabled", True),
                            max_items=item.get("max_items", 20),
                        )
                        self._configs[config.source_id] = config
            _logger.info("加载了 %d 个 Webhook 配置", len(self._configs))
        except Exception:
            _logger.warning("Webhook 配置加载失败", exc_info=True)

    def _persist(self) -> None:
        """原子写入配置。"""
        payload = [
            {
                "source_id": c.source_id,
                "secret": c.secret,
                "enabled": c.enabled,
                "max_items": c.max_items,
            }
            for c in self._configs.values()
        ]
        tmp = self._file.with_suffix(".json.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp.replace(self._file)
        except OSError:
            _logger.warning("Webhook 配置保存失败", exc_info=True)
            tmp.unlink(missing_ok=True)


class WebhookHandler:
    """Webhook 请求处理器。

    使用方式：
        handler = WebhookHandler(store, on_receive)
        # 在 HTTP 服务器中调用
        result = await handler.handle_request(source_id, request_body, signature)
    """

    def __init__(
        self,
        store: WebhookStore,
        on_receive: Callable[[WebhookPayload], Awaitable[None]],
    ) -> None:
        self._store = store
        self._on_receive = on_receive

    async def handle_request(
        self,
        source_id: str,
        body: bytes,
        signature: str | None = None,
    ) -> tuple[bool, str]:
        """处理 Webhook 请求。

        Args:
            source_id: 新闻源 ID
            body: 请求体（JSON）
            signature: 请求签名（可选）

        Returns:
            (success, message) 元组
        """
        # 获取配置
        config = self._store.get_config(source_id)
        if config is None:
            return False, f"未找到 Webhook 配置: {source_id}"

        if not config.enabled:
            return False, f"Webhook 已禁用: {source_id}"

        # 验证签名
        if config.secret and signature:
            verifier = WebhookVerifier(config.secret)
            if not verifier.verify_signature(body, signature):
                return False, "签名验证失败"

        # 解析数据
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return False, f"JSON 解析失败: {exc}"

        # 提取条目
        items = data.get("items") or data.get("data") or []
        if not isinstance(items, list):
            return False, "数据格式错误：items 应为数组"

        # 限制条目数
        items = items[:config.max_items]

        # 构造 payload
        payload = WebhookPayload(
            source_id=source_id,
            items=items,
            timestamp=time.time(),
            signature=signature or "",
        )

        # 调用回调
        try:
            await self._on_receive(payload)
        except Exception as exc:
            _logger.exception("Webhook 回调处理失败: %s", source_id)
            return False, f"处理失败: {exc}"

        return True, f"成功接收 {len(items)} 条数据"
