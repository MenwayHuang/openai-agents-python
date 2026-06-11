"""
Internal helpers shared by the agent run pipeline. Public-facing APIs (e.g., RunConfig,
RunOptions) belong at the top-level; only execution-time utilities that are not part of the
surface area should live under run_internal.

中文学习提示：这里放 run 流程内部工具，不是公开 API。学习 Runner 主线时可以阅读，
但业务代码不要直接依赖 run_internal。
"""

from __future__ import annotations
