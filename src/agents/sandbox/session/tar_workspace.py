"""中文学习提示：生成 tar 命令的排除参数。

持久化 workspace 时，有些 runtime 文件或临时挂载不应进入 tar。这里把需要跳过的
相对路径转换成 shell tar 可用的 `--exclude=` 参数。
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable
from pathlib import Path

__all__ = ["shell_tar_exclude_args"]


def shell_tar_exclude_args(skip_relpaths: Iterable[Path]) -> list[str]:
    """把相对路径集合渲染成 tar --exclude 参数列表。"""

    excludes: list[str] = []
    for rel in sorted(skip_relpaths, key=lambda p: p.as_posix()):
        rel_posix = rel.as_posix().lstrip("/")
        if not rel_posix or rel_posix in {".", "/"}:
            continue
        excludes.append(f"--exclude={shlex.quote(rel_posix)}")
        excludes.append(f"--exclude={shlex.quote(f'./{rel_posix}')}")
    return excludes
