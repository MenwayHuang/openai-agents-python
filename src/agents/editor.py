from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from .run_context import RunContextWrapper
from .util._types import MaybeAwaitable

ApplyPatchOperationType = Literal["create_file", "update_file", "delete_file"]

_DATACLASS_KWARGS = {"slots": True} if sys.version_info >= (3, 10) else {}

# 学习提示：这个文件定义 apply_patch 编辑器协议。Protocol 是 Python 的结构化类型：
# 只要对象有 create_file/update_file/delete_file 这些方法，就可被当作 ApplyPatchEditor。
# runtime_checkable 允许运行时用 isinstance 检查 Protocol。


@dataclass(**_DATACLASS_KWARGS)
class ApplyPatchOperation:
    """Represents a single apply_patch editor operation requested by the model."""

    type: ApplyPatchOperationType
    path: str
    diff: str | None = None
    ctx_wrapper: RunContextWrapper | None = None
    move_to: str | None = None
    # slots=True 会减少实例字典开销，也限制动态新增属性；这里只在 Python 3.10+ 启用。


@dataclass(**_DATACLASS_KWARGS)
class ApplyPatchResult:
    """Optional metadata returned by editor operations."""

    status: Literal["completed", "failed"] | None = None
    output: str | None = None
    # status/output 是宿主编辑器返回给 Agent 的最小结果信息。


@runtime_checkable
class ApplyPatchEditor(Protocol):
    """Host-defined editor that applies diffs on disk."""

    def create_file(
        self, operation: ApplyPatchOperation
    ) -> MaybeAwaitable[ApplyPatchResult | str | None]: ...

    def update_file(
        self, operation: ApplyPatchOperation
    ) -> MaybeAwaitable[ApplyPatchResult | str | None]: ...

    def delete_file(
        self, operation: ApplyPatchOperation
    ) -> MaybeAwaitable[ApplyPatchResult | str | None]: ...
