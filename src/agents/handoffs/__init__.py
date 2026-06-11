from __future__ import annotations

# 中文学习注释：
# 这个文件定义 handoff：让一个 Agent 把对话/任务转交给另一个 Agent。
# 在模型看来，handoff 是一个特殊工具调用；在 runtime 看来，它会改变 current_agent，
# 并准备下一轮输入历史。它和 agent.as_tool 的区别是：
# - handoff：新 Agent 接管后续对话；
# - as_tool：子 Agent 像普通工具一样被调用，结果返回给原 Agent。

import inspect
import json
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace as dataclasses_replace
from typing import TYPE_CHECKING, Any, Generic, TypeAlias, cast, overload

from pydantic import TypeAdapter
from typing_extensions import TypeVar

from ..exceptions import ModelBehaviorError, UserError
from ..items import RunItem, TResponseInputItem
from ..run_context import RunContextWrapper, TContext
from ..strict_schema import ensure_strict_json_schema
from ..tracing.spans import SpanError
from ..util import _error_tracing, _json, _transforms
from ..util._types import MaybeAwaitable
from .history import (
    default_handoff_history_mapper,
    get_conversation_history_wrappers,
    nest_handoff_history,
    reset_conversation_history_wrappers,
    set_conversation_history_wrappers,
)

if TYPE_CHECKING:
    # 避免运行时循环导入 Agent，同时保留类型检查能力。
    from ..agent import Agent, AgentBase


# The handoff input type is the type of data passed when the agent is called via a handoff.
THandoffInput = TypeVar("THandoffInput", default=Any)

# The agent type that the handoff returns.
TAgent = TypeVar("TAgent", bound="AgentBase[Any]", default="Agent[Any]")

OnHandoffWithInput = Callable[[RunContextWrapper[Any], THandoffInput], Any]
OnHandoffWithoutInput = Callable[[RunContextWrapper[Any]], Any]


@dataclass(frozen=True)
class HandoffInputData:
    # HandoffInputData 是 input_filter/nest_handoff_history 能操作的数据包。
    # frozen=True 表示不可原地修改，通常用 clone() 创建修改后的副本。
    input_history: str | tuple[TResponseInputItem, ...]
    """
    The input history before `Runner.run()` was called.
    """

    pre_handoff_items: tuple[RunItem, ...]
    """
    The items generated before the agent turn where the handoff was invoked.
    """

    new_items: tuple[RunItem, ...]
    """
    The new items generated during the current agent turn, including the item that triggered the
    handoff and the tool output message representing the response from the handoff output.
    """

    run_context: RunContextWrapper[Any] | None = None
    """
    The run context at the time the handoff was invoked. Note that, since this property was added
    later on, it is optional for backwards compatibility.
    """

    input_items: tuple[RunItem, ...] | None = None
    """
    Items to include in the next agent's input. When set, these items are used instead of
    new_items for building the input to the next agent. This allows filtering duplicates
    from agent input while preserving all items in new_items for session history.
    """

    def clone(self, **kwargs: Any) -> HandoffInputData:
        """
        Make a copy of the handoff input data, with the given arguments changed. For example, you
        could do:

        ```
        new_handoff_input_data = handoff_input_data.clone(new_items=())
        ```
        """

        # dataclasses.replace 会复制 dataclass，并替换传入字段。
        return dataclasses_replace(self, **kwargs)


HandoffInputFilter: TypeAlias = Callable[[HandoffInputData], MaybeAwaitable[HandoffInputData]]
"""A function that filters the input data passed to the next agent."""

HandoffHistoryMapper: TypeAlias = Callable[[list[TResponseInputItem]], list[TResponseInputItem]]
"""A function that maps the previous transcript to the nested summary payload."""


@dataclass
class Handoff(Generic[TContext, TAgent]):
    """A handoff is when an agent delegates a task to another agent.

    For example, in a customer support scenario you might have a "triage agent" that determines
    which agent should handle the user's request, and sub-agents that specialize in different areas
    like billing, account management, etc.
    """
    # Handoff 本质是“特殊工具定义 + 转交目标元数据”。
    # input_json_schema 只描述 handoff 工具参数，不等于新 Agent 的完整输入。

    tool_name: str
    """The name of the tool that represents the handoff."""

    tool_description: str
    """The description of the tool that represents the handoff."""

    input_json_schema: dict[str, Any]
    """The JSON schema for the handoff tool-call arguments.

    This schema is exposed to the model as the handoff tool's ``parameters``. It only describes the
    structured payload passed to ``on_invoke_handoff`` and does not replace the next agent's main
    input.
    """

    on_invoke_handoff: Callable[[RunContextWrapper[Any], str], Awaitable[TAgent]]
    """The function that invokes the handoff.

    The parameters passed are: (1) the handoff run context, (2) the arguments from the LLM as a
    JSON string (or an empty string if ``input_json_schema`` is empty). Must return an agent.
    """

    agent_name: str
    """The name of the agent that is being handed off to."""

    input_filter: HandoffInputFilter | None = None
    """A function that filters the inputs that are passed to the next agent.

    By default, the new agent sees the entire conversation history. In some cases, you may want to
    filter inputs (for example, to remove older inputs or remove tools from existing inputs). The
    function receives the entire conversation history so far, including the input item that
    triggered the handoff and a tool call output item representing the handoff tool's output. You
    are free to modify the input history or new items as you see fit. The next agent receives the
    input history plus ``input_items`` when provided, otherwise it receives ``new_items``. Use
    ``input_items`` to filter model input while keeping ``new_items`` intact for session history.
    IMPORTANT: in streaming mode, we will not stream anything as a result of this function. The
    items generated before will already have been streamed. Server-managed conversations
    (`conversation_id`, `previous_response_id`, or `auto_previous_response_id`) do not support
    handoff input filters.
    """

    nest_handoff_history: bool | None = None
    """Override the run-level ``nest_handoff_history`` behavior for this handoff only.

    Server-managed conversations (`conversation_id`, `previous_response_id`, or
    `auto_previous_response_id`) automatically disable nested handoff history with a warning.
    """

    strict_json_schema: bool = True
    """Whether the input JSON schema is in strict mode. We strongly recommend setting this to True
    because it increases the likelihood of correct JSON input."""

    is_enabled: bool | Callable[[RunContextWrapper[Any], AgentBase[Any]], MaybeAwaitable[bool]] = (
        True
    )
    """Whether the handoff is enabled.

    Either a bool or a callable that takes the run context and agent and returns whether the
    handoff is enabled. You can use this to dynamically enable or disable a handoff based on your
    context or state.
    """

    _agent_ref: weakref.ReferenceType[AgentBase[Any]] | None = field(
        default=None, init=False, repr=False
    )
    """Weak reference to the target agent when constructed via `handoff()`."""
    # weakref 避免 Handoff 和 Agent 互相强引用导致对象难以释放。

    def get_transfer_message(self, agent: AgentBase[Any]) -> str:
        # handoff 工具输出会告诉模型已经转给哪个 assistant。
        return json.dumps({"assistant": agent.name})

    @classmethod
    def default_tool_name(cls, agent: AgentBase[Any]) -> str:
        # 默认工具名类似 transfer_to_billing_agent，符合函数名风格。
        return _transforms.transform_string_function_style(f"transfer_to_{agent.name}")

    @classmethod
    def default_tool_description(cls, agent: AgentBase[Any]) -> str:
        return (
            f"Handoff to the {agent.name} agent to handle the request. "
            f"{agent.handoff_description or ''}"
        )


@overload
def handoff(
    agent: Agent[TContext],
    *,
    tool_name_override: str | None = None,
    tool_description_override: str | None = None,
    input_filter: Callable[[HandoffInputData], HandoffInputData] | None = None,
    nest_handoff_history: bool | None = None,
    is_enabled: bool | Callable[[RunContextWrapper[Any], Agent[Any]], MaybeAwaitable[bool]] = True,
) -> Handoff[TContext, Agent[TContext]]: ...
# @overload 只给类型检查器看，运行时真正实现是下面那个 handoff()。
# 这里支持“无输入 handoff”“带 input_type 的 handoff”等多种调用签名。


@overload
def handoff(
    agent: Agent[TContext],
    *,
    on_handoff: OnHandoffWithInput[THandoffInput],
    input_type: type[THandoffInput],
    tool_description_override: str | None = None,
    tool_name_override: str | None = None,
    input_filter: Callable[[HandoffInputData], HandoffInputData] | None = None,
    nest_handoff_history: bool | None = None,
    is_enabled: bool | Callable[[RunContextWrapper[Any], Agent[Any]], MaybeAwaitable[bool]] = True,
) -> Handoff[TContext, Agent[TContext]]: ...


@overload
def handoff(
    agent: Agent[TContext],
    *,
    on_handoff: OnHandoffWithoutInput,
    tool_description_override: str | None = None,
    tool_name_override: str | None = None,
    input_filter: Callable[[HandoffInputData], HandoffInputData] | None = None,
    nest_handoff_history: bool | None = None,
    is_enabled: bool | Callable[[RunContextWrapper[Any], Agent[Any]], MaybeAwaitable[bool]] = True,
) -> Handoff[TContext, Agent[TContext]]: ...


def handoff(
    agent: Agent[TContext],
    tool_name_override: str | None = None,
    tool_description_override: str | None = None,
    on_handoff: OnHandoffWithInput[THandoffInput] | OnHandoffWithoutInput | None = None,
    input_type: type[THandoffInput] | None = None,
    input_filter: Callable[[HandoffInputData], HandoffInputData] | None = None,
    nest_handoff_history: bool | None = None,
    is_enabled: bool
    | Callable[[RunContextWrapper[Any], Agent[TContext]], MaybeAwaitable[bool]] = True,
) -> Handoff[TContext, Agent[TContext]]:
    """Create a handoff from an agent.

    Args:
        agent: The agent to handoff to.
        tool_name_override: Optional override for the name of the tool that represents the handoff.
        tool_description_override: Optional override for the description of the tool that
            represents the handoff.
        on_handoff: A function that runs when the handoff is invoked. The ``handoff()`` helper
            always returns the specific ``agent`` captured here, so use ``on_handoff`` for side
            effects or bookkeeping rather than dynamic destination selection.
        input_type: The type of the handoff tool-call arguments. If provided, the model-generated
            JSON arguments are validated against this type and the parsed value is passed to
            ``on_handoff``. This only affects the handoff tool payload, not the next agent's main
            input.
        input_filter: A function that filters the inputs that are passed to the next agent.
        nest_handoff_history: Optional override for the RunConfig-level ``nest_handoff_history``
            flag. If ``None`` we fall back to the run's configuration.
        is_enabled: Whether the handoff is enabled. Can be a bool or a callable that takes the run
            context and agent and returns whether the handoff is enabled. Disabled handoffs are
            hidden from the LLM at runtime.
    """
    # handoff() 是创建 Handoff 对象的便捷函数。
    # 它会生成工具名/描述/schema，并创建 _invoke_handoff 回调。

    if input_type is not None and on_handoff is None:
        raise UserError("You must provide on_handoff when input_type is provided")
    type_adapter: TypeAdapter[Any] | None
    if input_type is not None:
        # 如果指定 input_type，模型调用 handoff 工具时必须提供符合该类型的 JSON 参数。
        if not callable(on_handoff):
            raise UserError("on_handoff must be callable")
        sig = inspect.signature(on_handoff)
        if len(sig.parameters) != 2:
            raise UserError("on_handoff must take two arguments: context and input")

        type_adapter = TypeAdapter(input_type)
        input_json_schema = type_adapter.json_schema()
    else:
        # 无 input_type 时，handoff 工具参数 schema 为空；on_handoff 只能接收 context。
        type_adapter = None
        input_json_schema = {}
        if on_handoff is not None:
            sig = inspect.signature(on_handoff)
            if len(sig.parameters) != 1:
                raise UserError("on_handoff must take one argument: context")

    async def _invoke_handoff(
        ctx: RunContextWrapper[Any], input_json: str | None = None
    ) -> Agent[TContext]:
        # runtime 执行 handoff 工具时调用这里。
        # on_handoff 只用于副作用/记账，最后总是返回 handoff() 捕获的目标 agent。
        if input_type is not None and type_adapter is not None:
            if input_json is None:
                _error_tracing.attach_error_to_current_span(
                    SpanError(
                        message="Handoff function expected non-null input, but got None",
                        data={"details": "input_json is None"},
                    )
                )
                raise ModelBehaviorError("Handoff function expected non-null input, but got None")

            validated_input = _json.validate_json(
                # 用 Pydantic TypeAdapter 校验模型给 handoff 工具的 JSON 参数。
                json_str=input_json,
                type_adapter=type_adapter,
                partial=False,
            )
            input_func = cast(OnHandoffWithInput[THandoffInput], on_handoff)
            result = input_func(ctx, validated_input)
            if inspect.isawaitable(result):
                await result
        elif on_handoff is not None:
            no_input_func = cast(OnHandoffWithoutInput, on_handoff)
            result = no_input_func(ctx)
            if inspect.isawaitable(result):
                await result

        return agent

    tool_name = tool_name_override or Handoff.default_tool_name(agent)
    tool_description = tool_description_override or Handoff.default_tool_description(agent)

    # Always ensure the input JSON schema is in strict mode. If needed, we can make this
    # configurable in the future.
    input_json_schema = ensure_strict_json_schema(input_json_schema)
    # handoff 工具参数也使用 strict schema，提高模型输出正确率。

    async def _is_enabled(ctx: RunContextWrapper[Any], agent_base: AgentBase[Any]) -> bool:
        # is_enabled 如果是函数，这里包装成统一 async 形式。
        from ..agent import Agent

        assert callable(is_enabled), "is_enabled must be callable here"
        assert isinstance(agent_base, Agent), "Can't handoff to a non-Agent"
        result = is_enabled(ctx, agent_base)
        if inspect.isawaitable(result):
            return await result
        return bool(result)

    handoff_obj = Handoff(
        # 创建真正 Handoff 配置对象，供 turn_preparation 暴露成模型可调用工具。
        tool_name=tool_name,
        tool_description=tool_description,
        input_json_schema=input_json_schema,
        on_invoke_handoff=_invoke_handoff,
        input_filter=input_filter,
        nest_handoff_history=nest_handoff_history,
        agent_name=agent.name,
        is_enabled=_is_enabled if callable(is_enabled) else is_enabled,
    )
    handoff_obj._agent_ref = weakref.ref(agent)
    return handoff_obj


__all__ = [
    "Handoff",
    "HandoffHistoryMapper",
    "HandoffInputData",
    "HandoffInputFilter",
    "default_handoff_history_mapper",
    "get_conversation_history_wrappers",
    "handoff",
    "nest_handoff_history",
    "reset_conversation_history_wrappers",
    "set_conversation_history_wrappers",
]
