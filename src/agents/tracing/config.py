from __future__ import annotations

from typing_extensions import TypedDict

# 学习提示：TracingConfig 是 trace 导出配置的 TypedDict，total=False 表示字段都可选。


class TracingConfig(TypedDict, total=False):
    """Configuration for tracing export."""

    api_key: str
