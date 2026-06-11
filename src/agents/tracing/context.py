"""Runner 创建/恢复 trace 的上下文管理器。

中文学习说明：
- Runner 每次运行前会通过这里决定：新建 trace、复用当前 trace，还是从 RunState 恢复 trace。
- `reattach_resumed_trace` 用于断点续跑，避免同一个任务恢复后生成一条全新的 trace。
- 对 PPT Agent 来说，这个模式适合“一个 PPT 生成任务跨多次请求，但观测上仍属于同一条任务链路”。
"""

from __future__ import annotations

from typing import Any

from .config import TracingConfig
from .create import get_current_trace, trace
from .traces import (
    Trace,
    TraceState,
    _hash_tracing_api_key,
    _trace_id_was_started,
    reattach_trace,
)


def _get_tracing_api_key(tracing: TracingConfig | None) -> str | None:
    return tracing.get("api_key") if tracing is not None else None


def _trace_state_matches_effective_settings(
    *,
    trace_state: TraceState,
    workflow_name: str,
    trace_id: str | None,
    group_id: str | None,
    metadata: dict[str, Any] | None,
    tracing: TracingConfig | None,
) -> bool:
    # 恢复 trace 前先确认 trace_id/workflow/group/metadata/key 都匹配，
    # 防止把当前运行错误挂到另一个任务的 trace 上。
    if trace_state.trace_id is None or trace_state.trace_id != trace_id:
        return False
    if trace_state.workflow_name != workflow_name:
        return False
    if trace_state.group_id != group_id:
        return False
    if trace_state.metadata != metadata:
        return False
    tracing_api_key = _get_tracing_api_key(tracing)
    if trace_state.tracing_api_key is not None:
        return trace_state.tracing_api_key == tracing_api_key
    if trace_state.tracing_api_key_hash is not None:
        # A fingerprint lets stripped RunState snapshots prove the caller
        # re-supplied the same explicit key.
        return trace_state.tracing_api_key_hash == _hash_tracing_api_key(tracing_api_key)
    return tracing_api_key is None


def create_trace_for_run(
    *,
    workflow_name: str,
    trace_id: str | None,
    group_id: str | None,
    metadata: dict[str, Any] | None,
    tracing: TracingConfig | None,
    disabled: bool,
    trace_state: TraceState | None = None,
    reattach_resumed_trace: bool = False,
) -> Trace | None:
    """Return a trace object for this run when one is not already active."""
    # 如果外层已经有 current_trace，Runner 不再创建新 trace，避免嵌套 workflow 混乱。
    current_trace = get_current_trace()
    if current_trace:
        return None

    if (
        reattach_resumed_trace
        and not disabled
        and trace_state is not None
        and _trace_id_was_started(trace_state.trace_id)
        and _trace_state_matches_effective_settings(
            trace_state=trace_state,
            workflow_name=workflow_name,
            trace_id=trace_id,
            group_id=group_id,
            metadata=metadata,
            tracing=tracing,
        )
    ):
        # Reuse the live key because secure snapshots may persist only the
        # fingerprint, not the secret itself.
        # 安全快照可能只有 key hash，没有明文 key；恢复时用本次配置里的 key。
        return reattach_trace(trace_state, tracing_api_key=_get_tracing_api_key(tracing))

    return trace(
        workflow_name=workflow_name,
        trace_id=trace_id,
        group_id=group_id,
        metadata=metadata,
        tracing=tracing,
        disabled=disabled,
    )


class TraceCtxManager:
    """Create a trace when none exists and manage its lifecycle for a run."""
    # Runner 用这个上下文管理器包住一次 run，确保 trace start/finish 成对发生。

    def __init__(
        self,
        workflow_name: str,
        trace_id: str | None,
        group_id: str | None,
        metadata: dict[str, Any] | None,
        tracing: TracingConfig | None,
        disabled: bool,
        trace_state: TraceState | None = None,
        reattach_resumed_trace: bool = False,
    ):
        self.trace: Trace | None = None
        self.workflow_name = workflow_name
        self.trace_id = trace_id
        self.group_id = group_id
        self.metadata = metadata
        self.tracing = tracing
        self.disabled = disabled
        self.trace_state = trace_state
        self.reattach_resumed_trace = reattach_resumed_trace

    def __enter__(self) -> TraceCtxManager:
        # __enter__/__exit__ 是 Python context manager 协议，对应 `with TraceCtxManager(...)`。
        self.trace = create_trace_for_run(
            workflow_name=self.workflow_name,
            trace_id=self.trace_id,
            group_id=self.group_id,
            metadata=self.metadata,
            tracing=self.tracing,
            disabled=self.disabled,
            trace_state=self.trace_state,
            reattach_resumed_trace=self.reattach_resumed_trace,
        )
        if self.trace:
            assert self.trace is not None
            self.trace.start(mark_as_current=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.trace:
            self.trace.finish(reset_current=True)
