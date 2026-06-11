"""
Internal step/result data structures used by the run loop orchestration.
These types are not part of the public SDK surface.
"""

from __future__ import annotations

# 中文学习注释：
# 这个文件定义 run loop 内部使用的“步骤协议”。
# 模型返回的是一堆 output items；SDK 会先把它们整理成 ProcessedResponse，
# 再根据执行结果产出 NextStep：最终输出、handoff、继续跑一轮、或等待审批中断。
# 自研 Agent runtime 时，可以把这里看成“状态机的数据结构定义”。

import dataclasses
from dataclasses import dataclass
from typing import Any

from openai.types.responses import ResponseComputerToolCall, ResponseFunctionToolCall
from openai.types.responses.response_output_item import LocalShellCall, McpApprovalRequest

from ..agent import Agent, ToolsToFinalOutputResult
from ..guardrail import OutputGuardrailResult
from ..handoffs import Handoff
from ..items import ModelResponse, RunItem, ToolApprovalItem, TResponseInputItem
from ..tool import (
    ApplyPatchTool,
    ComputerTool,
    CustomTool,
    FunctionTool,
    HostedMCPTool,
    LocalShellTool,
    ShellTool,
)
from ..tool_guardrails import ToolInputGuardrailResult, ToolOutputGuardrailResult

__all__ = [
    "QueueCompleteSentinel",
    "QUEUE_COMPLETE_SENTINEL",
    "NOT_FINAL_OUTPUT",
    "ToolRunHandoff",
    "ToolRunFunction",
    "ToolRunComputerAction",
    "ToolRunCustom",
    "ToolRunMCPApprovalRequest",
    "ToolRunLocalShellCall",
    "ToolRunShellCall",
    "ToolRunApplyPatchCall",
    "ToolRunFunctionNotFound",
    "ProcessedResponse",
    "NextStepHandoff",
    "NextStepFinalOutput",
    "NextStepRunAgain",
    "NextStepInterruption",
    "SingleStepResult",
]


class QueueCompleteSentinel:
    """Sentinel used to signal completion when streaming run loop results."""
    # Sentinel 是“特殊标记对象”。流式队列里放入它，表示没有更多事件。


QUEUE_COMPLETE_SENTINEL = QueueCompleteSentinel()

NOT_FINAL_OUTPUT = ToolsToFinalOutputResult(is_final_output=False, final_output=None)
# 工具结果默认不直接作为最终输出，除非 Agent.tool_use_behavior 显式指定。


@dataclass
class ToolRunHandoff:
    # 表示模型调用了某个 handoff 工具，等待 runtime 执行“切换 Agent”。
    handoff: Handoff
    tool_call: ResponseFunctionToolCall


@dataclass
class ToolRunFunction:
    # 表示模型调用了 FunctionTool，等待 runtime 执行 Python 函数。
    tool_call: ResponseFunctionToolCall
    function_tool: FunctionTool


@dataclass
class ToolRunFunctionNotFound:
    # 模型调用了一个不存在/不可用的函数工具。
    # runtime 会生成 tool output 告诉模型“工具不存在”，而不是直接崩溃。
    tool_call: ResponseFunctionToolCall
    tool_name: str


@dataclass
class ToolRunComputerAction:
    # 表示模型请求 computer tool 动作，例如点击、输入、截图。
    tool_call: ResponseComputerToolCall
    computer_tool: ComputerTool[Any]


@dataclass
class ToolRunCustom:
    # CustomTool 使用原始字符串输入，不走 FunctionTool 的 JSON 参数 schema。
    tool_call: Any
    custom_tool: CustomTool


@dataclass
class ToolRunMCPApprovalRequest:
    request_item: McpApprovalRequest
    mcp_tool: HostedMCPTool


@dataclass
class ToolRunLocalShellCall:
    tool_call: LocalShellCall
    local_shell_tool: LocalShellTool


@dataclass
class ToolRunShellCall:
    tool_call: Any
    shell_tool: ShellTool


@dataclass
class ToolRunApplyPatchCall:
    tool_call: Any
    apply_patch_tool: ApplyPatchTool


@dataclass
class ProcessedResponse:
    # ProcessedResponse 是模型响应的分类结果。
    # 它把同一个 ModelResponse 中的 message、tool call、handoff、approval request 等拆成不同桶，
    # 后续 turn_resolution/tool_planning 会按这些桶执行对应动作。
    new_items: list[RunItem]
    handoffs: list[ToolRunHandoff]
    functions: list[ToolRunFunction]
    computer_actions: list[ToolRunComputerAction]
    local_shell_calls: list[ToolRunLocalShellCall]
    shell_calls: list[ToolRunShellCall]
    apply_patch_calls: list[ToolRunApplyPatchCall]
    tools_used: list[str]  # Names of all tools used, including hosted tools
    mcp_approval_requests: list[ToolRunMCPApprovalRequest]  # Only requests with callbacks
    interruptions: list[ToolApprovalItem]  # Tool approval items awaiting user decision
    function_tools_not_found: list[ToolRunFunctionNotFound] = dataclasses.field(
        default_factory=list
    )
    custom_tool_calls: list[ToolRunCustom] = dataclasses.field(default_factory=list)

    def has_tools_or_approvals_to_run(self) -> bool:
        # Handoffs, functions and computer actions need local processing
        # Hosted tools have already run, so there's nothing to do.
        # Hosted tools 是模型服务端已经执行过的工具；本地只需要处理本地函数/电脑/shell/handoff/审批。
        return any(
            [
                self.handoffs,
                self.functions,
                self.computer_actions,
                self.custom_tool_calls,
                self.local_shell_calls,
                self.shell_calls,
                self.apply_patch_calls,
                self.mcp_approval_requests,
                self.function_tools_not_found,
            ]
        )

    def has_interruptions(self) -> bool:
        """Check if there are tool calls awaiting approval."""
        return len(self.interruptions) > 0


@dataclass
class NextStepHandoff:
    # 下一步切换到 new_agent 继续 run loop。
    new_agent: Agent[Any]


@dataclass
class NextStepFinalOutput:
    # 下一步结束整个 run，并把 output 作为最终输出。
    output: Any


@dataclass
class NextStepRunAgain:
    # 下一步继续调用模型，通常是因为刚执行完工具，需要把工具结果发回模型。
    pass


@dataclass
class NextStepInterruption:
    """Represents an interruption in the agent run due to tool approval requests."""
    # 下一步暂停，等待外部用户 approve/reject 工具调用。

    interruptions: list[ToolApprovalItem]
    """The list of tool calls awaiting approval."""


@dataclass
class SingleStepResult:
    # SingleStepResult 是“一轮 turn”的完整结果：
    # 包含本轮模型响应、这轮新增 RunItem、下一步状态、guardrail 结果、恢复所需 processed_response。
    original_input: str | list[TResponseInputItem]
    """The input items i.e. the items before run() was called. May be mutated by handoff input
    filters."""

    model_response: ModelResponse
    """The model response for the current step."""

    pre_step_items: list[RunItem]
    """Items generated before the current step."""

    new_step_items: list[RunItem]
    """Items generated during this current step."""

    next_step: NextStepHandoff | NextStepFinalOutput | NextStepRunAgain | NextStepInterruption
    """The next step to take."""

    tool_input_guardrail_results: list[ToolInputGuardrailResult]
    """Tool input guardrail results from this step."""

    tool_output_guardrail_results: list[ToolOutputGuardrailResult]
    """Tool output guardrail results from this step."""

    session_step_items: list[RunItem] | None = None
    """Full unfiltered items for session history. When set, these are used instead of
    new_step_items for session saving and generated_items property."""

    output_guardrail_results: list[OutputGuardrailResult] = dataclasses.field(default_factory=list)
    """Output guardrail results (populated when a final output is produced)."""

    processed_response: ProcessedResponse | None = None
    """The processed model response. This is needed for resuming from interruptions."""

    @property
    def generated_items(self) -> list[RunItem]:
        """Items generated during the agent run (i.e. everything generated after
        `original_input`). Uses session_step_items when available for full observability."""
        # generated_items 是“下一轮/最终结果”能看到的本轮生成内容。
        # handoff input filter 可能让模型输入项和 session 观测项不同，所以这里优先 session_step_items。
        items = (
            self.session_step_items if self.session_step_items is not None else self.new_step_items
        )
        return self.pre_step_items + items
