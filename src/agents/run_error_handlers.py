"""Run 级错误处理回调。

中文学习说明：
- 有些错误不一定要直接抛给调用方，比如 max_turns 超限或模型拒绝，可以由业务 handler
  转成一个最终输出。
- 这适合做“兜底回复”“任务失败说明”“保存失败状态”等业务化处理。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic

from typing_extensions import TypedDict

from .agent import Agent
from .exceptions import MaxTurnsExceeded, ModelRefusalError
from .items import ModelResponse, RunItem, TResponseInputItem
from .run_context import RunContextWrapper, TContext
from .util._types import MaybeAwaitable


@dataclass
class RunErrorData:
    """Snapshot of run data passed to error handlers."""

    input: str | list[TResponseInputItem]
    new_items: list[RunItem]
    history: list[TResponseInputItem]
    output: list[TResponseInputItem]
    raw_responses: list[ModelResponse]
    last_agent: Agent[Any]


@dataclass
class RunErrorHandlerInput(Generic[TContext]):
    error: MaxTurnsExceeded | ModelRefusalError
    context: RunContextWrapper[TContext]
    run_data: RunErrorData


@dataclass
class RunErrorHandlerResult:
    """Result returned by an error handler."""
    # include_in_history=True 表示 handler 产出的 final_output 也进入对话历史。

    final_output: Any
    include_in_history: bool = True


# Handlers may return RunErrorHandlerResult, a dict with final_output, or a raw final output value.
RunErrorHandler = Callable[
    [RunErrorHandlerInput[TContext]],
    MaybeAwaitable[RunErrorHandlerResult | dict[str, Any] | Any | None],
]


class RunErrorHandlers(TypedDict, Generic[TContext], total=False):
    """Error handlers keyed by error kind."""

    max_turns: RunErrorHandler[TContext]
    model_refusal: RunErrorHandler[TContext]


__all__ = [
    "RunErrorData",
    "RunErrorHandler",
    "RunErrorHandlerInput",
    "RunErrorHandlerResult",
    "RunErrorHandlers",
]
