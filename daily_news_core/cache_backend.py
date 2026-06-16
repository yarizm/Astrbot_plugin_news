"""缓存后端抽象：支持内存缓存和可选 Redis 缓存。"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

_logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目。"""
    data: Any  # 缓存的数据
    fetched_at: float  # 获取时间（time.time() 用于跨进程兼容）
    ttl: int  # TTL（秒）


class CacheBackend(Protocol):
    """缓存后端接口。"""

    async def get(self, key: str) -> CacheEntry | None:
        """获取缓存条目，不存在或过期返回 None。"""
        ...

    async def set(self, key: str, entry: CacheEntry) -> None:
        """设置缓存条目。"""
        ...

    async def delete(self, key: str) -> None:
        """删除缓存条目。"""
        ...

    async def clear(self) -> None:
        """清空所有缓存。"""
        ...


class MemoryCache:
    """内存缓存后端（默认）。"""

    def __init__(self) -> None:
        self._cache: dict[str, CacheEntry] = {}

    async def get(self, key: str) -> CacheEntry | None:
        """获取缓存条目。"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        # 检查是否过期
        if time.monotonic() - entry.fetched_at > entry.ttl:
            del self._cache[key]
            return None
        return entry

    async def set(self, key: str, entry: CacheEntry) -> None:
        """设置缓存条目。"""
        self._cache[key] = entry

    async def delete(self, key: str) -> None:
        """删除缓存条目。"""
        self._cache.pop(key, None)

    async def clear(self) -> None:
        """清空所有缓存。"""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


class RedisCache:
    """Redis 缓存后端（可选）。"""

    def __init__(self, redis_url: str, prefix: str = "daily_news:") -> None:
        """初始化 Redis 缓存。

        Args:
            redis_url: Redis 连接 URL（如 redis://localhost:6379/0）
            prefix: 键前缀
        """
        self._redis_url = redis_url
        self._prefix = prefix
        self._redis = None

    async def _get_redis(self):
        """延迟初始化 Redis 连接。"""
        if self._redis is None:
            try:
                import aioredis
                self._redis = await aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
            except ImportError:
                _logger.error("aioredis 未安装，无法使用 Redis 缓存后端")
                raise
        return self._redis

    def _make_key(self, key: str) -> str:
        """生成完整的 Redis 键。"""
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> CacheEntry | None:
        """从 Redis 获取缓存条目。"""
        try:
            redis = await self._get_redis()
            raw = await redis.get(self._make_key(key))
            if raw is None:
                return None
            data = json.loads(raw)
            entry = CacheEntry(
                data=data["data"],
                fetched_at=data["fetched_at"],
                ttl=data["ttl"],
            )
            # 使用 time.time() 跨进程兼容（Redis TTL 由 Redis 自身管理，这里是双重检查）
            if time.time() - entry.fetched_at > entry.ttl:
                await self.delete(key)
                return None
            return entry
        except Exception:
            _logger.warning("Redis GET 失败: %s", key, exc_info=True)
            return None

    async def set(self, key: str, entry: CacheEntry) -> None:
        """将缓存条目写入 Redis。"""
        try:
            redis = await self._get_redis()
            data = {
                "data": entry.data,
                "fetched_at": entry.fetched_at,
                "ttl": entry.ttl,
            }
            await redis.set(
                self._make_key(key),
                json.dumps(data, ensure_ascii=False),
                ex=entry.ttl,  # 设置 Redis 过期时间
            )
        except Exception:
            _logger.warning("Redis SET 失败: %s", key, exc_info=True)

    async def delete(self, key: str) -> None:
        """从 Redis 删除缓存条目。"""
        try:
            redis = await self._get_redis()
            await redis.delete(self._make_key(key))
        except Exception:
            _logger.warning("Redis DELETE 失败: %s", key, exc_info=True)

    async def clear(self) -> None:
        """清空所有带前缀的缓存。"""
        try:
            redis = await self._get_redis()
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor, match=f"{self._prefix}*", count=100)
                if keys:
                    await redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            _logger.warning("Redis CLEAR 失败", exc_info=True)

    async def close(self) -> None:
        """关闭 Redis 连接。"""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None


def create_cache_backend(redis_url: str | None = None) -> CacheBackend:
    """创建缓存后端实例。

    Args:
        redis_url: Redis 连接 URL，为空则使用内存缓存

    Returns:
        CacheBackend 实例
    """
    if redis_url:
        return RedisCache(redis_url)
    return MemoryCache()
