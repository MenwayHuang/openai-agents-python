"""Contains common handoff input filters, for convenience."""

from __future__ import annotations

# 中文学习注释：
# 这个扩展文件提供常用 handoff input_filter。
# 当前核心函数 remove_all_tools 会在转交给下一个 Agent 时移除工具调用/工具输出/reasoning 等，
# 适合希望新 Agent 只看到用户和助手自然语言上下文的场景。

from ..handoffs import (
    HandoffInputData,
    default_handoff_history_mapper,
    nest_handoff_history,
)
from ..items import (
    HandoffCallItem,
    HandoffOutputItem,
    MCPApprovalRequestItem,
    MCPApprovalResponseItem,
    MCPListToolsItem,
    ReasoningItem,
    RunItem,
    ToolApprovalItem,
    ToolCallItem,
    ToolCallOutputItem,
    ToolSearchCallItem,
    ToolSearchOutputItem,
    TResponseInputItem,
)

__all__ = [
    "remove_all_tools",
    "nest_handoff_history",
    "default_handoff_history_mapper",
]


def remove_all_tools(handoff_input_data: HandoffInputData) -> HandoffInputData:
    """Filters out all tool items: file search, web search and function calls+output."""
    # 注意：这里同时过滤 input_history、pre_handoff_items、new_items、input_items。
    # 这样和 nest_handoff_history 链式组合时，不会把工具项又引回模型输入。

    history = handoff_input_data.input_history
    new_items = handoff_input_data.new_items

    filtered_history = (
        _remove_tool_types_from_input(history) if isinstance(history, tuple) else history
    )
    filtered_pre_handoff_items = _remove_tools_from_items(handoff_input_data.pre_handoff_items)
    filtered_new_items = _remove_tools_from_items(new_items)
    # Preserve and filter input_items so chained filters (e.g. after
    # nest_handoff_history) don't drop or re-introduce tool items.
    existing_input_items = handoff_input_data.input_items
    filtered_input_items = (
        _remove_tools_from_items(existing_input_items) if existing_input_items is not None else None
    )

    return handoff_input_data.clone(
        input_history=filtered_history,
        pre_handoff_items=filtered_pre_handoff_items,
        new_items=filtered_new_items,
        input_items=filtered_input_items,
    )


def _remove_tools_from_items(items: tuple[RunItem, ...]) -> tuple[RunItem, ...]:
    # RunItem 层面的过滤：移除各种 Tool/Handoff/MCP/Reasoning 内部项。
    filtered_items = []
    for item in items:
        if (
            isinstance(item, HandoffCallItem)
            or isinstance(item, HandoffOutputItem)
            or isinstance(item, ToolSearchCallItem)
            or isinstance(item, ToolSearchOutputItem)
            or isinstance(item, ToolCallItem)
            or isinstance(item, ToolCallOutputItem)
            or isinstance(item, ReasoningItem)
            or isinstance(item, MCPListToolsItem)
            or isinstance(item, MCPApprovalRequestItem)
            or isinstance(item, MCPApprovalResponseItem)
            or isinstance(item, ToolApprovalItem)
        ):
            continue
        filtered_items.append(item)
    return tuple(filtered_items)


def _remove_tool_types_from_input(
    items: tuple[TResponseInputItem, ...],
) -> tuple[TResponseInputItem, ...]:
    # 原始 input item 层面的过滤：根据 type 字段移除工具相关项。
    tool_types = [
        "function_call",
        "function_call_output",
        "computer_call",
        "computer_call_output",
        "file_search_call",
        "tool_search_call",
        "tool_search_output",
        "web_search_call",
        "mcp_call",
        "mcp_list_tools",
        "mcp_approval_request",
        "mcp_approval_response",
        "reasoning",
        "code_interpreter_call",
        "image_generation_call",
        "local_shell_call",
        "local_shell_call_output",
        "shell_call",
        "shell_call_output",
        "apply_patch_call",
        "apply_patch_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "hosted_tool_call",
    ]

    filtered_items: list[TResponseInputItem] = []
    for item in items:
        itype = item.get("type")
        if itype in tool_types:
            continue
        filtered_items.append(item)
    return tuple(filtered_items)
