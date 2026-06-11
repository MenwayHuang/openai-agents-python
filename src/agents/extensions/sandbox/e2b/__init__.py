"""E2B sandbox 扩展导出入口。

学习提示：E2B provider 适合代码解释器/远程执行类 Agent 场景。当前只需要知道它也是
SandboxClient/SandboxSession 的一个第三方实现。
"""

from __future__ import annotations

from .mounts import E2BCloudBucketMountStrategy
from .sandbox import (
    E2BSandboxClient,
    E2BSandboxClientOptions,
    E2BSandboxSession,
    E2BSandboxSessionState,
    E2BSandboxTimeouts,
    E2BSandboxType,
    _E2BSandboxFactoryAPI,
    _encode_e2b_snapshot_ref,
    _import_sandbox_class,
    _sandbox_connect,
)

__all__ = [
    "_E2BSandboxFactoryAPI",
    "_encode_e2b_snapshot_ref",
    "_import_sandbox_class",
    "_sandbox_connect",
    "E2BCloudBucketMountStrategy",
    "E2BSandboxClient",
    "E2BSandboxClientOptions",
    "E2BSandboxSession",
    "E2BSandboxSessionState",
    "E2BSandboxTimeouts",
    "E2BSandboxType",
]
