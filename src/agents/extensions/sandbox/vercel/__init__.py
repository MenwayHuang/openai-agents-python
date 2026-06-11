"""Vercel sandbox 扩展导出入口。

学习提示：Vercel provider 把 Vercel Sandbox 接入 SDK 的统一 sandbox 接口，
适合在 Vercel 生态中运行受控代码执行任务。
"""

from __future__ import annotations

from .sandbox import (
    VercelSandboxClient,
    VercelSandboxClientOptions,
    VercelSandboxSession,
    VercelSandboxSessionState,
)

__all__ = [
    "VercelSandboxClient",
    "VercelSandboxClientOptions",
    "VercelSandboxSession",
    "VercelSandboxSessionState",
]
