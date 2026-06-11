from __future__ import annotations

# 中文学习注释：
# 这个文件定义工具级 guardrail：
# - ToolInputGuardrail：工具函数真正执行前检查工具参数/上下文；
# - ToolOutputGuardrail：工具函数执行后检查工具输出。
# 和 Agent 级 guardrail 不同，工具 guardrail 可以选择：
# allow、reject_content（不执行/替换输出但继续 run）、raise_exception（停止 run）。

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Literal, overload

from typing_extensions import TypedDict, TypeVar

from .exceptions import UserError
from .tool_context import ToolContext
from .util._types import MaybeAwaitable

if TYPE_CHECKING:
    from .agent import Agent


@dataclass
class ToolInputGuardrailResult:
    """The result of a tool input guardrail run."""

    guardrail: ToolInputGuardrail[Any]
    """The guardrail that was run."""

    output: ToolGuardrailFunctionOutput
    """The output of the guardrail function."""


@dataclass
class ToolOutputGuardrailResult:
    """The result of a tool output guardrail run."""

    guardrail: ToolOutputGuardrail[Any]
    """The guardrail that was run."""

    output: ToolGuardrailFunctionOutput
    """The output of the guardrail function."""


class RejectContentBehavior(TypedDict):
    """Rejects the tool call/output but continues execution with a message to the model."""
    # reject_content 不会让整个 run 崩溃，而是把 message 当作工具输出给模型。

    type: Literal["reject_content"]
    message: str


class RaiseExceptionBehavior(TypedDict):
    """Raises an exception to halt execution."""

    type: Literal["raise_exception"]


class AllowBehavior(TypedDict):
    """Allows normal tool execution to continue."""

    type: Literal["allow"]


@dataclass
class ToolGuardrailFunctionOutput:
    """The output of a tool guardrail function."""
    # behavior 是工具 guardrail 的核心差异点。
    # 默认 allow；需要拦截时用 reject_content 或 raise_exception。

    output_info: Any
    """
    Optional data about checks performed. For example, the guardrail could include
    information about the checks it performed and granular results.
    """

    behavior: RejectContentBehavior | RaiseExceptionBehavior | AllowBehavior = field(
        default_factory=lambda: AllowBehavior(type="allow")
    )
    """
    Defines how the system should respond when this guardrail result is processed.
    - allow: Allow normal tool execution to continue without interference (default)
    - reject_content: Reject the tool call/output but continue execution with a message to the model
    - raise_exception: Halt execution by raising a ToolGuardrailTripwireTriggered exception
    """

    @classmethod
    def allow(cls, output_info: Any = None) -> ToolGuardrailFunctionOutput:
        """Create a guardrail output that allows the tool execution to continue normally.

        Args:
            output_info: Optional data about checks performed.

        Returns:
            ToolGuardrailFunctionOutput configured to allow normal execution.
        """
        # 便捷构造：允许工具继续。
        return cls(output_info=output_info, behavior=AllowBehavior(type="allow"))

    @classmethod
    def reject_content(cls, message: str, output_info: Any = None) -> ToolGuardrailFunctionOutput:
        """Create a guardrail output that rejects the tool call/output but continues execution.

        Args:
            message: Message to send to the model instead of the tool result.
            output_info: Optional data about checks performed.

        Returns:
            ToolGuardrailFunctionOutput configured to reject the content.
        """
        # 便捷构造：拒绝工具输入/输出，并把 message 反馈给模型。
        return cls(
            output_info=output_info,
            behavior=RejectContentBehavior(type="reject_content", message=message),
        )

    @classmethod
    def raise_exception(cls, output_info: Any = None) -> ToolGuardrailFunctionOutput:
        """Create a guardrail output that raises an exception to halt execution.

        Args:
            output_info: Optional data about checks performed.

        Returns:
            ToolGuardrailFunctionOutput configured to raise an exception.
        """
        # 便捷构造：触发异常，停止整个 run。
        return cls(output_info=output_info, behavior=RaiseExceptionBehavior(type="raise_exception"))


@dataclass
class ToolInputGuardrailData:
    """Input data passed to a tool input guardrail function."""
    # 输入 guardrail 可从 ToolContext 读取 tool_name、tool_call_id、参数、run_config 等。

    context: ToolContext[Any]
    """
    The tool context containing information about the current tool execution.
    """

    agent: Agent[Any]
    """
    The agent that is executing the tool.
    """


@dataclass
class ToolOutputGuardrailData(ToolInputGuardrailData):
    """Input data passed to a tool output guardrail function.

    Extends input data with the tool's output.
    """
    # 输出 guardrail 比输入 guardrail 多一个 output 字段，用于检查工具返回值。

    output: Any
    """
    The output produced by the tool function.
    """


TContext_co = TypeVar("TContext_co", bound=Any, covariant=True)


@dataclass
class ToolInputGuardrail(Generic[TContext_co]):
    """A guardrail that runs before a function tool is invoked."""
    # 只适用于 FunctionTool；执行点在 run_internal/tool_execution.py。

    guardrail_function: Callable[
        [ToolInputGuardrailData], MaybeAwaitable[ToolGuardrailFunctionOutput]
    ]
    """
    The function that implements the guardrail logic.
    """

    name: str | None = None
    """
    Optional name for the guardrail. If not provided, uses the function name.
    """

    def get_name(self) -> str:
        return self.name or self.guardrail_function.__name__

    async def run(self, data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
        # guardrail 函数支持同步/异步两种写法。
        if not callable(self.guardrail_function):
            raise UserError(f"Guardrail function must be callable, got {self.guardrail_function}")

        result = self.guardrail_function(data)
        if inspect.isawaitable(result):
            return await result
        return result


@dataclass
class ToolOutputGuardrail(Generic[TContext_co]):
    """A guardrail that runs after a function tool is invoked."""
    # 工具执行完成后检查输出；可以替换为拒绝消息，也可以抛异常。

    guardrail_function: Callable[
        [ToolOutputGuardrailData], MaybeAwaitable[ToolGuardrailFunctionOutput]
    ]
    """
    The function that implements the guardrail logic.
    """

    name: str | None = None
    """
    Optional name for the guardrail. If not provided, uses the function name.
    """

    def get_name(self) -> str:
        return self.name or self.guardrail_function.__name__

    async def run(self, data: ToolOutputGuardrailData) -> ToolGuardrailFunctionOutput:
        if not callable(self.guardrail_function):
            raise UserError(f"Guardrail function must be callable, got {self.guardrail_function}")

        result = self.guardrail_function(data)
        if inspect.isawaitable(result):
            return await result
        return result


# Decorators
_ToolInputFuncSync = Callable[[ToolInputGuardrailData], ToolGuardrailFunctionOutput]
_ToolInputFuncAsync = Callable[[ToolInputGuardrailData], Awaitable[ToolGuardrailFunctionOutput]]


@overload
def tool_input_guardrail(func: _ToolInputFuncSync): ...


@overload
def tool_input_guardrail(func: _ToolInputFuncAsync): ...


@overload
def tool_input_guardrail(
    *, name: str | None = None
) -> Callable[[_ToolInputFuncSync | _ToolInputFuncAsync], ToolInputGuardrail[Any]]: ...


def tool_input_guardrail(
    func: _ToolInputFuncSync | _ToolInputFuncAsync | None = None,
    *,
    name: str | None = None,
) -> (
    ToolInputGuardrail[Any]
    | Callable[[_ToolInputFuncSync | _ToolInputFuncAsync], ToolInputGuardrail[Any]]
):
    """Decorator to create a ToolInputGuardrail from a function."""
    # 装饰器支持 @tool_input_guardrail 和 @tool_input_guardrail(name="...") 两种风格。

    def decorator(f: _ToolInputFuncSync | _ToolInputFuncAsync) -> ToolInputGuardrail[Any]:
        return ToolInputGuardrail(guardrail_function=f, name=name or f.__name__)

    if func is not None:
        return decorator(func)
    return decorator


_ToolOutputFuncSync = Callable[[ToolOutputGuardrailData], ToolGuardrailFunctionOutput]
_ToolOutputFuncAsync = Callable[[ToolOutputGuardrailData], Awaitable[ToolGuardrailFunctionOutput]]


@overload
def tool_output_guardrail(func: _ToolOutputFuncSync): ...


@overload
def tool_output_guardrail(func: _ToolOutputFuncAsync): ...


@overload
def tool_output_guardrail(
    *, name: str | None = None
) -> Callable[[_ToolOutputFuncSync | _ToolOutputFuncAsync], ToolOutputGuardrail[Any]]: ...


def tool_output_guardrail(
    func: _ToolOutputFuncSync | _ToolOutputFuncAsync | None = None,
    *,
    name: str | None = None,
) -> (
    ToolOutputGuardrail[Any]
    | Callable[[_ToolOutputFuncSync | _ToolOutputFuncAsync], ToolOutputGuardrail[Any]]
):
    """Decorator to create a ToolOutputGuardrail from a function."""
    # 输出 guardrail 的装饰器，与输入 guardrail 结构一致。

    def decorator(f: _ToolOutputFuncSync | _ToolOutputFuncAsync) -> ToolOutputGuardrail[Any]:
        return ToolOutputGuardrail(guardrail_function=f, name=name or f.__name__)

    if func is not None:
        return decorator(func)
    return decorator
