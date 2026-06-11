"""Session configuration settings.

学习提示：SessionSettings 是会话读写的轻量配置对象。当前主要只有 limit，
后续如果自研 PPT Agent 需要“读取最近 N 条历史”“读取某个项目范围历史”，
可以参考这种把可选设置集中到配置对象里的方式。
"""

from __future__ import annotations

import dataclasses
from dataclasses import fields, replace
from typing import Any

from pydantic.dataclasses import dataclass


def resolve_session_limit(
    explicit_limit: int | None,
    settings: SessionSettings | None,
) -> int | None:
    """Safely resolve the effective limit for session operations."""
    # 显式传入优先于 SessionSettings，调用点可以临时覆盖默认配置。
    if explicit_limit is not None:
        return explicit_limit
    if settings is not None:
        return settings.limit
    return None


@dataclass
class SessionSettings:
    """Settings for session operations.

    This class holds optional session configuration parameters that can be used
    when interacting with session methods.
    """

    limit: int | None = None
    """Maximum number of items to retrieve. If None, retrieves all items."""

    def resolve(self, override: SessionSettings | None) -> SessionSettings:
        """Produce a new SessionSettings by overlaying any non-None values from the
        override on top of this instance."""
        if override is None:
            return self

        # dataclasses.fields(self) 会枚举 dataclass 字段；replace 返回一个新对象，不改原对象。
        changes = {
            field.name: getattr(override, field.name)
            for field in fields(self)
            if getattr(override, field.name) is not None
        }

        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to a dictionary."""
        # dataclasses.asdict 会递归把 dataclass 转为普通 dict，适合日志/序列化。
        return dataclasses.asdict(self)
