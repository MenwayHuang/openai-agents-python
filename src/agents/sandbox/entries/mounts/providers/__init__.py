"""中文学习提示：各云存储 mount provider 的导出口。

这里的类负责描述“要挂载哪个云存储资源”，实际挂载方式由 mount strategy/pattern
决定。当前 PPT Agent 不急着深入，但以后做用户文件库、企业模板库时会用到。
"""

from __future__ import annotations

from .azure_blob import AzureBlobMount
from .box import BoxMount
from .gcs import GCSMount
from .r2 import R2Mount
from .s3 import S3Mount
from .s3_files import S3FilesMount

__all__ = [
    "AzureBlobMount",
    "GCSMount",
    "R2Mount",
    "S3Mount",
    "S3FilesMount",
    "BoxMount",
]
