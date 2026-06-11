from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from ..exceptions import UserError

# Keep this helper here so both run_internal and realtime can import it without
# creating cross-package dependencies.

# 学习提示：needs_approval 可以是 bool，也可以是同步/异步函数。
# 这个 helper 统一求值，供普通 run_internal 和 realtime 共用。


async def evaluate_needs_approval_setting(
    needs_approval_setting: bool | Callable[..., Any],
    *args: Any,
    default: bool = False,
    strict: bool = True,
) -> bool:
    """Return bool from a needs_approval setting that may be bool or callable/awaitable."""
    if isinstance(needs_approval_setting, bool):
        return needs_approval_setting
    if callable(needs_approval_setting):
        maybe_result = needs_approval_setting(*args)
        if inspect.isawaitable(maybe_result):
            maybe_result = await maybe_result
        return bool(maybe_result)
    if strict:
        raise UserError(
            f"Invalid needs_approval value: expected a bool or callable, "
            f"got {type(needs_approval_setting).__name__}."
        )
    return default
