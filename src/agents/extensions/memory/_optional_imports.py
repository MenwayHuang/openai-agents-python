from __future__ import annotations

from typing import NoReturn

# 学习提示：扩展依赖按 extra 安装；这个 helper 专门生成友好的“缺少可选依赖”错误。


def raise_optional_dependency_error(
    export_name: str,
    *,
    dependency_name: str,
    extra_name: str,
    cause: ImportError | None = None,
) -> NoReturn:
    error = ImportError(
        f"{export_name} requires the '{dependency_name}' extra. "
        f"Install it with: pip install openai-agents[{extra_name}]"
    )
    if cause is None:
        raise error
    raise error from cause
