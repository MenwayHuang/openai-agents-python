"""Modal sandbox 扩展导出入口。

学习提示：Modal provider 把 Modal.Sandbox 接入 SDK sandbox 抽象，并补充镜像选择、
云桶挂载和 snapshot 引用编码等能力。
"""

from __future__ import annotations

import tarfile

from ....sandbox.snapshot import resolve_snapshot
from .mounts import ModalCloudBucketMountConfig, ModalCloudBucketMountStrategy
from .sandbox import (
    _DEFAULT_TIMEOUT_S,
    _MODAL_STDIN_CHUNK_SIZE,
    ModalImageSelector,
    ModalSandboxClient,
    ModalSandboxClientOptions,
    ModalSandboxSelector,
    ModalSandboxSession,
    ModalSandboxSessionState,
    _encode_modal_snapshot_ref,
    _encode_snapshot_directory_ref,
    _encode_snapshot_filesystem_ref,
)

__all__ = [
    "_DEFAULT_TIMEOUT_S",
    "_MODAL_STDIN_CHUNK_SIZE",
    "_encode_modal_snapshot_ref",
    "_encode_snapshot_directory_ref",
    "_encode_snapshot_filesystem_ref",
    "ModalCloudBucketMountConfig",
    "ModalCloudBucketMountStrategy",
    "ModalImageSelector",
    "ModalSandboxClient",
    "ModalSandboxClientOptions",
    "ModalSandboxSelector",
    "ModalSandboxSession",
    "ModalSandboxSessionState",
    "resolve_snapshot",
    "tarfile",
]
