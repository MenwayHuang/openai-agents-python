"""Agent/Run 生命周期 hooks。

中文学习说明：
- Hooks 是扩展点，不改变 Runner 主流程，但能在关键时机插入日志、指标、审计、业务回调。
- `RunHooksBase` 作用于一次 run 的全局事件；`AgentHooksBase` 作用于某个 agent 自己的事件。
- 对 PPT Agent 来说，可以用 hooks 记录“开始规划、模型返回、工具开始/结束、handoff、最终输出”等执行轨迹。
"""

from typing import Any, Generic

from typing_extensions import TypeVar

from .agent import Agent, AgentBase
from .items import ModelResponse, TResponseInputItem
from .run_context import AgentHookContext, RunContextWrapper, TContext
from .tool import Tool

TAgent = TypeVar("TAgent", bound=AgentBase, default=AgentBase)


class RunHooksBase(Generic[TContext, TAgent]):
    """A class that receives callbacks on various lifecycle events in an agent run. Subclass and
    override the methods you need.
    """
    # 全局 run hooks：不需要每个 Agent 单独配置，适合统一观测/审计。

    async def on_llm_start(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent[TContext],
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Called just before invoking the LLM for this agent."""
        # 模型调用前：可记录输入摘要、模型名、项目 ID，但生产环境要避免记录完整隐私内容。
        pass

    async def on_llm_end(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        """Called immediately after the LLM call returns for this agent."""
        pass

    async def on_agent_start(self, context: AgentHookContext[TContext], agent: TAgent) -> None:
        """Called before the agent is invoked. Called each time the current agent changes.

        Args:
            context: The agent hook context.
            agent: The agent that is about to be invoked.
        """
        pass

    async def on_agent_end(
        self,
        context: AgentHookContext[TContext],
        agent: TAgent,
        output: Any,
    ) -> None:
        """Called when the agent produces a final output.

        Args:
            context: The agent hook context.
            agent: The agent that produced the output.
            output: The final output produced by the agent.
        """
        pass

    async def on_handoff(
        self,
        context: RunContextWrapper[TContext],
        from_agent: TAgent,
        to_agent: TAgent,
    ) -> None:
        """Called when a handoff occurs."""
        pass

    async def on_tool_start(
        self,
        context: RunContextWrapper[TContext],
        agent: TAgent,
        tool: Tool,
    ) -> None:
        """Called immediately before a local tool is invoked.

        For function-tool invocations, ``context`` is typically a ``ToolContext`` instance,
        which exposes tool-call-specific metadata such as ``tool_call_id``, ``tool_name``,
        and ``tool_arguments``. Other local tool families may provide a plain
        ``RunContextWrapper`` instead.
        """
        # 工具调用前：可做业务日志、权限检查、耗时统计起点等。
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[TContext],
        agent: TAgent,
        tool: Tool,
        result: object,
    ) -> None:
        """Called immediately after a local tool is invoked.

        For function-tool invocations, ``context`` is typically a ``ToolContext`` instance,
        which exposes tool-call-specific metadata such as ``tool_call_id``, ``tool_name``,
        and ``tool_arguments``. Other local tool families may provide a plain
        ``RunContextWrapper`` instead.

        Simple tool outputs are typically ``str`` values. Function tools may also return
        structured tool output objects or any value the SDK can stringify before sending it to
        the model.
        """
        pass


class AgentHooksBase(Generic[TContext, TAgent]):
    """A class that receives callbacks on various lifecycle events for a specific agent. You can
    set this on `agent.hooks` to receive events for that specific agent.

    Subclass and override the methods you need.
    """
    # Agent 级 hooks：只在绑定的 agent 上触发，适合记录某个专业 agent 的行为。

    async def on_start(self, context: AgentHookContext[TContext], agent: TAgent) -> None:
        """Called before the agent is invoked. Called each time the running agent is changed to this
        agent.

        Args:
            context: The agent hook context.
            agent: This agent instance.
        """
        # 当前 agent 开始工作时触发，handoff 后新 agent 也会触发。
        pass

    async def on_end(
        self,
        context: AgentHookContext[TContext],
        agent: TAgent,
        output: Any,
    ) -> None:
        """Called when the agent produces a final output.

        Args:
            context: The agent hook context.
            agent: This agent instance.
            output: The final output produced by the agent.
        """
        pass

    async def on_handoff(
        self,
        context: RunContextWrapper[TContext],
        agent: TAgent,
        source: TAgent,
    ) -> None:
        """Called when the agent is being handed off to. The `source` is the agent that is handing
        off to this agent."""
        pass

    async def on_tool_start(
        self,
        context: RunContextWrapper[TContext],
        agent: TAgent,
        tool: Tool,
    ) -> None:
        """Called immediately before a local tool is invoked.

        For function-tool invocations, ``context`` is typically a ``ToolContext`` instance,
        which exposes tool-call-specific metadata such as ``tool_call_id``, ``tool_name``,
        and ``tool_arguments``. Other local tool families may provide a plain
        ``RunContextWrapper`` instead.
        """
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[TContext],
        agent: TAgent,
        tool: Tool,
        result: object,
    ) -> None:
        """Called immediately after a local tool is invoked.

        For function-tool invocations, ``context`` is typically a ``ToolContext`` instance,
        which exposes tool-call-specific metadata such as ``tool_call_id``, ``tool_name``,
        and ``tool_arguments``. Other local tool families may provide a plain
        ``RunContextWrapper`` instead.

        Simple tool outputs are typically ``str`` values. Function tools may also return
        structured tool output objects or any value the SDK can stringify before sending it to
        the model.
        """
        pass

    async def on_llm_start(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent[TContext],
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Called immediately before the agent issues an LLM call."""
        pass

    async def on_llm_end(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        """Called immediately after the agent receives the LLM response."""
        pass


RunHooks = RunHooksBase[TContext, Agent]
"""Run hooks when using `Agent`."""

AgentHooks = AgentHooksBase[TContext, Agent]
"""Agent hooks for `Agent`s."""
