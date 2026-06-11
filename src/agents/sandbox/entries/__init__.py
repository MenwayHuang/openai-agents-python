"""中文学习提示：sandbox entries 的统一导出口。

Entry 是 Manifest 里描述“工作区里要出现什么”的抽象，包括内联文件、本地目录、
Git 仓库和各种云存储挂载。阅读时先看 `base.py` 的 BaseEntry，再看
`artifacts.py` 的具体文件类，以及 `mounts/` 里远端挂载的策略。
"""

from __future__ import annotations

from .artifacts import Dir, File, GitRepo, LocalDir, LocalFile
from .base import BaseEntry, resolve_workspace_path
from .mounts import (
    AzureBlobMount,
    BoxMount,
    DockerVolumeMountStrategy,
    FuseMountPattern,
    GCSMount,
    InContainerMountStrategy,
    Mount,
    MountPattern,
    MountPatternBase,
    MountpointMountPattern,
    MountStrategy,
    MountStrategyBase,
    R2Mount,
    RcloneMountPattern,
    S3FilesMount,
    S3FilesMountPattern,
    S3Mount,
)

__all__ = [
    "AzureBlobMount",
    "BaseEntry",
    "BoxMount",
    "Dir",
    "File",
    "DockerVolumeMountStrategy",
    "FuseMountPattern",
    "GCSMount",
    "GitRepo",
    "InContainerMountStrategy",
    "LocalDir",
    "LocalFile",
    "Mount",
    "MountPattern",
    "MountPatternBase",
    "MountStrategy",
    "MountStrategyBase",
    "MountpointMountPattern",
    "R2Mount",
    "RcloneMountPattern",
    "S3Mount",
    "S3FilesMount",
    "S3FilesMountPattern",
    "resolve_workspace_path",
]
