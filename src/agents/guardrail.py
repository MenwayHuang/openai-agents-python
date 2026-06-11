from __future__ import annotations

# 中文学习注释：
# 这个文件定义 Agent 级 guardrail：
# - InputGuardrail：在首轮用户输入进入 Agent 前/并行时检查；
# - OutputGuardrail：在最终输出返回给用户前检查。
# guardrail 返回 GuardrailFunctionOutput，如果 tripwire_triggered=True，
# runtime 会抛出对应异常并停止执行。

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, overload

from typing_extensions import TypeVar

from .exceptions import UserError
from .items import TResponseInputItem
from .run_context import RunContextWrapper, TContext
from .util._types import MaybeAwaitable

if TYPE_CHECKING:
    # 只用于类型检查，避免运行时循环导入 Agent。
    from .agent import Agent


@dataclass
class GuardrailFunctionOutput:
    """The output of a guardrail function."""
    # guardrail 的通用输出：output_info 放检查细节，tripwire_triggered 决定是否拦截。

    output_info: Any
    """
    Optional information about the guardrail's output. For example, the guardrail could include
    information about the checks it performed and granular results.
    """

    tripwire_triggered: bool
    """
    Whether the tripwire was triggered. If triggered, the agent's execution will be halted.
    """


@dataclass
class InputGuardrailResult:
    """The result of a guardrail run."""

    guardrail: InputGuardrail[Any]
    """
    The guardrail that was run.
    """

    output: GuardrailFunctionOutput
    """The output of the guardrail function."""


@dataclass
class OutputGuardrailResult:
    """The result of a guardrail run."""

    guardrail: OutputGuardrail[Any]
    """
    The guardrail that was run.
    """

    agent_output: Any
    """
    The output of the agent that was checked by the guardrail.
    """

    agent: Agent[Any]
    """
    The agent that was checked by the guardrail.
    """

    output: GuardrailFunctionOutput
    """The output of the guardrail function."""


@dataclass
class InputGuardrail(Generic[TContext]):
    """Input guardrails are checks that run either in parallel with the agent or before it starts.
    They can be used to do things like:
    - Check if input messages are off-topic
    - Take over control of the agent's execution if an unexpected input is detected

    You can use the `@input_guardrail()` decorator to turn a function into an `InputGuardrail`, or
    create an `InputGuardrail` manually.

    Guardrails return a `GuardrailResult`. If `result.tripwire_triggered` is `True`,
    the agent's execution will immediately stop, and
    an `InputGuardrailTripwireTriggered` exception will be raised
    """
    # Generic[TContext] 让 guardrail 函数知道 run context 的业务类型。

    guardrail_function: Callable[
        [RunContextWrapper[TContext], Agent[Any], str | list[TResponseInputItem]],
        MaybeAwaitable[GuardrailFunctionOutput],
    ]
    """A function that receives the agent input and the context, and returns a
     `GuardrailResult`. The result marks whether the tripwire was triggered, and can optionally
     include information about the guardrail's output.
    """

    name: str | None = None
    """The name of the guardrail, used for tracing. If not provided, we'll use the guardrail
    function's name.
    """

    run_in_parallel: bool = True
    """Whether the guardrail runs concurrently with the agent (True, default) or before
    the agent starts (False).
    """

    def get_name(self) -> str:
        if self.name:
            return self.name

        return self.guardrail_function.__name__

    async def run(
        self,
        agent: Agent[Any],
        input: str | list[TResponseInputItem],
        context: RunContextWrapper[TContext],
    ) -> InputGuardrailResult:
        # guardrail_function 可以同步也可以异步，统一在这里 await。
        if not callable(self.guardrail_function):
            raise UserError(f"Guardrail function must be callable, got {self.guardrail_function}")

        output = self.guardrail_function(context, agent, input)
        if inspect.isawaitable(output):
            return InputGuardrailResult(
                guardrail=self,
                output=await output,
            )

        return InputGuardrailResult(
            guardrail=self,
            output=output,
        )


@dataclass
class OutputGuardrail(Generic[TContext]):
    """Output guardrails are checks that run on the final output of an agent.
    They can be used to do check if the output passes certain validation criteria

    You can use the `@output_guardrail()` decorator to turn a function into an `OutputGuardrail`,
    or create an `OutputGuardrail` manually.

    Guardrails return a `GuardrailResult`. If `result.tripwire_triggered` is `True`, an
    `OutputGuardrailTripwireTriggered` exception will be raised.
    """
    # OutputGuardrail 只检查最终输出，不检查中间工具结果。
    # 工具级检查在 tool_guardrails.py。

    guardrail_function: Callable[
        [RunContextWrapper[TContext], Agent[Any], Any],
        MaybeAwaitable[GuardrailFunctionOutput],
    ]
    """A function that receives the final agent, its output, and the context, and returns a
     `GuardrailResult`. The result marks whether the tripwire was triggered, and can optionally
     include information about the guardrail's output.
    """

    name: str | None = None
    """The name of the guardrail, used for tracing. If not provided, we'll use the guardrail
    function's name.
    """

    def get_name(self) -> str:
        if self.name:
            return self.name

        return self.guardrail_function.__name__

    async def run(
        self, context: RunContextWrapper[TContext], agent: Agent[Any], agent_output: Any
    ) -> OutputGuardrailResult:
        if not callable(self.guardrail_function):
            raise UserError(f"Guardrail function must be callable, got {self.guardrail_function}")

        output = self.guardrail_function(context, agent, agent_output)
        if inspect.isawaitable(output):
            return OutputGuardrailResult(
                guardrail=self,
                agent=agent,
                agent_output=agent_output,
                output=await output,
            )

        return OutputGuardrailResult(
            guardrail=self,
            agent=agent,
            agent_output=agent_output,
            output=output,
        )


TContext_co = TypeVar("TContext_co", bound=Any, covariant=True)
# covariant=True 表示类型参数协变，是类型系统概念；运行时没有行为影响。

# For InputGuardrail
_InputGuardrailFuncSync = Callable[
    [RunContextWrapper[TContext_co], "Agent[Any]", str | list[TResponseInputItem]],
    GuardrailFunctionOutput,
]
_InputGuardrailFuncAsync = Callable[
    [RunContextWrapper[TContext_co], "Agent[Any]", str | list[TResponseInputItem]],
    Awaitable[GuardrailFunctionOutput],
]


@overload
def input_guardrail(
    func: _InputGuardrailFuncSync[TContext_co],
) -> InputGuardrail[TContext_co]: ...


@overload
def input_guardrail(
    func: _InputGuardrailFuncAsync[TContext_co],
) -> InputGuardrail[TContext_co]: ...


@overload
def input_guardrail(
    *,
    name: str | None = None,
    run_in_parallel: bool = True,
) -> Callable[
    [_InputGuardrailFuncSync[TContext_co] | _InputGuardrailFuncAsync[TContext_co]],
    InputGuardrail[TContext_co],
]: ...


def input_guardrail(
    func: _InputGuardrailFuncSync[TContext_co]
    | _InputGuardrailFuncAsync[TContext_co]
    | None = None,
    *,
    name: str | None = None,
    run_in_parallel: bool = True,
) -> (
    InputGuardrail[TContext_co]
    | Callable[
        [_InputGuardrailFuncSync[TContext_co] | _InputGuardrailFuncAsync[TContext_co]],
        InputGuardrail[TContext_co],
    ]
):
    """
    Decorator that transforms a sync or async function into an `InputGuardrail`.
    It can be used directly (no parentheses) or with keyword args, e.g.:

        @input_guardrail
        def my_sync_guardrail(...): ...

        @input_guardrail(name="guardrail_name", run_in_parallel=False)
        async def my_async_guardrail(...): ...

    Args:
        func: The guardrail function to wrap.
        name: Optional name for the guardrail. If not provided, uses the function's name.
        run_in_parallel: Whether to run the guardrail concurrently with the agent (True, default)
            or before the agent starts (False).
    """
    # 和 @function_tool 类似，这个装饰器支持两种写法：
    # @input_guardrail
    # @input_guardrail(name="...", run_in_parallel=False)

    def decorator(
        f: _InputGuardrailFuncSync[TContext_co] | _InputGuardrailFuncAsync[TContext_co],
    ) -> InputGuardrail[TContext_co]:
        return InputGuardrail(
            guardrail_function=f,
            # If not set, guardrail name uses the function’s name by default.
            name=name if name else f.__name__,
            run_in_parallel=run_in_parallel,
        )

    if func is not None:
        # Decorator was used without parentheses
        # 使用 @input_guardrail 的路径。
        return decorator(func)

    # Decorator used with keyword arguments
    # 使用 @input_guardrail(...) 的路径。
    return decorator


_OutputGuardrailFuncSync = Callable[
    [RunContextWrapper[TContext_co], "Agent[Any]", Any],
    GuardrailFunctionOutput,
]
_OutputGuardrailFuncAsync = Callable[
    [RunContextWrapper[TContext_co], "Agent[Any]", Any],
    Awaitable[GuardrailFunctionOutput],
]


@overload
def output_guardrail(
    func: _OutputGuardrailFuncSync[TContext_co],
) -> OutputGuardrail[TContext_co]: ...


@overload
def output_guardrail(
    func: _OutputGuardrailFuncAsync[TContext_co],
) -> OutputGuardrail[TContext_co]: ...


@overload
def output_guardrail(
    *,
    name: str | None = None,
) -> Callable[
    [_OutputGuardrailFuncSync[TContext_co] | _OutputGuardrailFuncAsync[TContext_co]],
    OutputGuardrail[TContext_co],
]: ...


def output_guardrail(
    func: _OutputGuardrailFuncSync[TContext_co]
    | _OutputGuardrailFuncAsync[TContext_co]
    | None = None,
    *,
    name: str | None = None,
) -> (
    OutputGuardrail[TContext_co]
    | Callable[
        [_OutputGuardrailFuncSync[TContext_co] | _OutputGuardrailFuncAsync[TContext_co]],
        OutputGuardrail[TContext_co],
    ]
):
    """
    Decorator that transforms a sync or async function into an `OutputGuardrail`.
    It can be used directly (no parentheses) or with keyword args, e.g.:

        @output_guardrail
        def my_sync_guardrail(...): ...

        @output_guardrail(name="guardrail_name")
        async def my_async_guardrail(...): ...
    """
    # 输出 guardrail 装饰器，同样兼容 @output_guardrail 和 @output_guardrail(...)。

    def decorator(
        f: _OutputGuardrailFuncSync[TContext_co] | _OutputGuardrailFuncAsync[TContext_co],
    ) -> OutputGuardrail[TContext_co]:
        return OutputGuardrail(
            guardrail_function=f,
            # Guardrail name defaults to function's name when not specified (None).
            name=name if name else f.__name__,
        )

    if func is not None:
        # Decorator was used without parentheses
        return decorator(func)

    # Decorator used with keyword arguments
    return decorator
