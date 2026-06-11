from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .types import Permissions

# 学习提示：这里是 sandbox 文件列表/元信息的数据结构。
# EntryKind 区分目录、文件、链接等类型，FileEntry 则记录权限、owner、group、size。


class EntryKind(str, Enum):
    DIRECTORY = "directory"
    FILE = "file"
    SYMLINK = "symlink"
    OTHER = "other"


@dataclass(frozen=True, kw_only=True)
class FileEntry:
    path: str
    permissions: Permissions
    owner: str
    group: str
    size: int
    kind: EntryKind = EntryKind.FILE

    def is_dir(self) -> bool:
        return self.kind == EntryKind.DIRECTORY
