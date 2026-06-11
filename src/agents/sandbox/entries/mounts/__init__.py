"""中文学习提示：远端/外部存储挂载能力的统一导出口。

Mount 让 sandbox 在工作区里看到 S3、GCS、R2、Box、Azure Blob 等远端资源。
这不是 PPT Agent 当前的主线，但以后做企业资料库、模板库或用户文件空间时会很有用。
"""

from __future__ import annotations

from .base import (
    DockerVolumeMountStrategy,
    InContainerMountStrategy,
    Mount,
    MountStrategy,
    MountStrategyBase,
)
from .patterns import (
    FuseMountPattern,
    MountPattern,
    MountPatternBase,
    MountpointMountPattern,
    RcloneMountPattern,
    S3FilesMountPattern,
)
from .providers import AzureBlobMount, BoxMount, GCSMount, R2Mount, S3FilesMount, S3Mount

__all__ = [
    "AzureBlobMount",
    "BoxMount",
    "FuseMountPattern",
    "GCSMount",
    "DockerVolumeMountStrategy",
    "InContainerMountStrategy",
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
]
