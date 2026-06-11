"""流式运行对外暴露的事件类型。

中文学习说明：
- `RawResponsesStreamEvent` 是模型/Responses API 原始流事件。
- `RunItemStreamEvent` 是 SDK 消化模型输出后生成的语义事件，例如工具调用、工具输出、handoff。
- `AgentUpdatedStreamEvent` 表示当前执行 agent 发生变化。
- 对 PPT Agent 的前端来说，可以参考这种拆分：原始 token 流、业务步骤事件、当前 agent 状态事件分开处理。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from .agent import Agent
from .items import RunItem, TResponseStreamEvent


@dataclass
class RawResponsesStreamEvent:
    """Streaming event from the LLM. These are 'raw' events, i.e. they are directly passed through
    from the LLM.
    """
    # 最底层的模型流事件，适合调试或做 token 级 UI。

    data: TResponseStreamEvent
    """The raw responses streaming event from the LLM."""

    type: Literal["raw_response_event"] = "raw_response_event"
    """The type of the event."""


@dataclass
class RunItemStreamEvent:
    """Streaming events that wrap a `RunItem`. As the agent processes the LLM response, it will
    generate these events for new messages, tool calls, tool outputs, handoffs, etc.
    """
    # 更适合业务前端消费的事件：模型消息、工具调用、工具结果、审批请求等。

    name: Literal[
        "message_output_created",
        "handoff_requested",
        # This is misspelled, but we can't change it because that would be a breaking change
        "handoff_occured",
        "tool_called",
        "tool_search_called",
        "tool_search_output_created",
        "tool_output",
        "reasoning_item_created",
        "mcp_approval_requested",
        "mcp_approval_response",
        "mcp_list_tools",
    ]
    """The name of the event."""

    item: RunItem
    """The item that was created."""

    type: Literal["run_item_stream_event"] = "run_item_stream_event"


@dataclass
class AgentUpdatedStreamEvent:
    """Event that notifies that there is a new agent running."""
    # 多 agent handoff 后，前端可以用这个事件更新“当前正在工作的 agent”。

    new_agent: Agent[Any]
    """The new agent."""

    type: Literal["agent_updated_stream_event"] = "agent_updated_stream_event"


StreamEvent: TypeAlias = RawResponsesStreamEvent | RunItemStreamEvent | AgentUpdatedStreamEvent
"""A streaming event from an agent."""
