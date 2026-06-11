"""Agents SDK 异常类型。

中文学习说明：
- `AgentsException` 是 SDK 统一异常基类，很多异常会附带 `run_data`，便于定位出错时的输入、
  新增 item、原始模型响应、最后运行的 agent。
- `ModelBehaviorError` 通常表示模型输出不符合预期；`UserError` 通常表示调用 SDK 的代码配置错误。
- 对 PPT Agent 来说，建议也区分“用户输入错误、模型行为异常、工具执行异常、系统内部异常”。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import Agent
    from .guardrail import InputGuardrailResult, OutputGuardrailResult
    from .items import ModelResponse, RunItem, TResponseInputItem
    from .run_context import RunContextWrapper
    from .tool_guardrails import (
        ToolGuardrailFunctionOutput,
        ToolInputGuardrail,
        ToolOutputGuardrail,
    )

from .util._pretty_print import pretty_print_run_error_details

_DRAIN_STREAM_EVENTS_ATTR = "_agents_drain_queued_stream_events"


def _mark_error_to_drain_stream_events(error: Exception) -> None:
    # 某些流式异常抛出前需要先把队列里已有事件吐完，避免前端丢失已生成内容。
    setattr(error, _DRAIN_STREAM_EVENTS_ATTR, True)


def _should_drain_stream_events_before_raising(error: Exception) -> bool:
    return bool(getattr(error, _DRAIN_STREAM_EVENTS_ATTR, False))


@dataclass
class RunErrorDetails:
    """Data collected from an agent run when an exception occurs."""
    # 出错快照：异常对象可以携带它，方便上层日志/接口返回/调试展示。

    input: str | list[TResponseInputItem]
    new_items: list[RunItem]
    raw_responses: list[ModelResponse]
    last_agent: Agent[Any]
    context_wrapper: RunContextWrapper[Any]
    input_guardrail_results: list[InputGuardrailResult]
    output_guardrail_results: list[OutputGuardrailResult]

    def __str__(self) -> str:
        return pretty_print_run_error_details(self)


class AgentsException(Exception):
    """Base class for all exceptions in the Agents SDK."""
    # 所有 SDK 自定义异常都继承它，便于上层统一捕获。

    run_data: RunErrorDetails | None

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self.run_data = None


class MaxTurnsExceeded(AgentsException):
    """Exception raised when the maximum number of turns is exceeded."""

    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ModelBehaviorError(AgentsException):
    """Exception raised when the model does something unexpected, e.g. calling a tool that doesn't
    exist, or providing malformed JSON.
    """

    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ModelRefusalError(AgentsException):
    """Exception raised when the model refuses to produce the requested output."""

    refusal: str
    """The refusal text returned by the model."""

    def __init__(self, refusal: str):
        self.refusal = refusal
        super().__init__(f"Model refused to produce output: {refusal}")


class UserError(AgentsException):
    """Exception raised when the user makes an error using the SDK."""

    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class MCPToolCancellationError(AgentsException):
    """Exception raised when an MCP tool call is internally cancelled."""

    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ToolTimeoutError(AgentsException):
    """Exception raised when a function tool invocation exceeds its timeout."""

    tool_name: str
    timeout_seconds: float

    def __init__(self, tool_name: str, timeout_seconds: float):
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Tool '{tool_name}' timed out after {timeout_seconds:g} seconds.")


class InputGuardrailTripwireTriggered(AgentsException):
    """Exception raised when a guardrail tripwire is triggered."""

    guardrail_result: InputGuardrailResult
    """The result data of the guardrail that was triggered."""

    def __init__(self, guardrail_result: InputGuardrailResult):
        self.guardrail_result = guardrail_result
        super().__init__(
            f"Guardrail {guardrail_result.guardrail.__class__.__name__} triggered tripwire"
        )


class OutputGuardrailTripwireTriggered(AgentsException):
    """Exception raised when a guardrail tripwire is triggered."""

    guardrail_result: OutputGuardrailResult
    """The result data of the guardrail that was triggered."""

    def __init__(self, guardrail_result: OutputGuardrailResult):
        self.guardrail_result = guardrail_result
        super().__init__(
            f"Guardrail {guardrail_result.guardrail.__class__.__name__} triggered tripwire"
        )


class ToolInputGuardrailTripwireTriggered(AgentsException):
    """Exception raised when a tool input guardrail tripwire is triggered."""

    guardrail: ToolInputGuardrail[Any]
    """The guardrail that was triggered."""

    output: ToolGuardrailFunctionOutput
    """The output from the guardrail function."""

    def __init__(self, guardrail: ToolInputGuardrail[Any], output: ToolGuardrailFunctionOutput):
        self.guardrail = guardrail
        self.output = output
        super().__init__(f"Tool input guardrail {guardrail.__class__.__name__} triggered tripwire")


class ToolOutputGuardrailTripwireTriggered(AgentsException):
    """Exception raised when a tool output guardrail tripwire is triggered."""

    guardrail: ToolOutputGuardrail[Any]
    """The guardrail that was triggered."""

    output: ToolGuardrailFunctionOutput
    """The output from the guardrail function."""

    def __init__(self, guardrail: ToolOutputGuardrail[Any], output: ToolGuardrailFunctionOutput):
        self.guardrail = guardrail
        self.output = output
        super().__init__(f"Tool output guardrail {guardrail.__class__.__name__} triggered tripwire")
