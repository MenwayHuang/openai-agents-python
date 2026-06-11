from __future__ import annotations

# 学习提示：sandbox 子包的公开导出入口。
# Sandbox 是 SDK 里“受控执行环境”的抽象，负责工作区文件、命令执行、快照、
# 能力开关和 Agent 工具暴露。当前 PPT Agent 暂时不需要照搬，但安全边界值得学习。

from ..run_config import SandboxArchiveLimits, SandboxConcurrencyLimits, SandboxRunConfig
from .capabilities import Capability
from .config import MemoryGenerateConfig, MemoryLayoutConfig, MemoryReadConfig
from .entries import Dir, LocalFile
from .errors import (
    ErrorCode,
    ExecTimeoutError,
    ExecTransportError,
    ExposedPortUnavailableError,
    SandboxError,
    WorkspaceArchiveReadError,
    WorkspaceArchiveWriteError,
    WorkspaceReadNotFoundError,
    WorkspaceWriteTypeError,
)
from .manifest import Manifest
from .sandbox_agent import SandboxAgent
from .snapshot import (
    LocalSnapshot,
    LocalSnapshotSpec,
    RemoteSnapshot,
    RemoteSnapshotSpec,
    SnapshotSpec,
    resolve_snapshot,
)
from .types import ExecResult, ExposedPortEndpoint, FileMode, Group, Permissions, User
from .workspace_paths import SandboxPathGrant

__all__ = [
    "Capability",
    "Dir",
    "ErrorCode",
    "ExecResult",
    "ExposedPortEndpoint",
    "ExposedPortUnavailableError",
    "ExecTimeoutError",
    "ExecTransportError",
    "FileMode",
    "Group",
    "LocalFile",
    "LocalSnapshot",
    "LocalSnapshotSpec",
    "Manifest",
    "MemoryLayoutConfig",
    "MemoryReadConfig",
    "MemoryGenerateConfig",
    "RemoteSnapshot",
    "RemoteSnapshotSpec",
    "Permissions",
    "SandboxAgent",
    "SandboxArchiveLimits",
    "SandboxPathGrant",
    "SandboxConcurrencyLimits",
    "SandboxError",
    "SandboxRunConfig",
    "SnapshotSpec",
    "WorkspaceArchiveReadError",
    "WorkspaceArchiveWriteError",
    "WorkspaceReadNotFoundError",
    "WorkspaceWriteTypeError",
    "User",
    "resolve_snapshot",
]
