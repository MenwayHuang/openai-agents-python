"""运行上下文与工具审批状态。

中文学习说明：
- `RunContextWrapper` 包住你传给 `Runner.run(..., context=...)` 的业务上下文。
  这个 context 不会发给模型，而是给工具函数、hooks、guardrails 等 Python 代码使用。
- 本文件还维护工具审批状态：某个工具调用是已批准、已拒绝，还是仍需人工确认。
- 对 PPT Agent 来说，context 可以放“当前用户、项目 ID、模板库路径、任务配置、数据库会话”
  这类后端内部信息；审批状态可用于“是否允许联网搜图/覆盖文件/导出文件”等动作。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic

from typing_extensions import TypeVar

from ._tool_identity import (
    FunctionToolLookupKey,
    get_function_tool_approval_keys,
    get_function_tool_lookup_key,
    is_reserved_synthetic_tool_namespace,
    tool_qualified_name,
)
from .usage import Usage

if TYPE_CHECKING:
    from .items import ToolApprovalItem, TResponseInputItem
else:
    # Keep runtime annotations resolvable for TypeAdapter users (e.g., Temporal's
    # Pydantic data converter) without importing items.py and introducing cycles.
    ToolApprovalItem = Any
    TResponseInputItem = Any

TContext = TypeVar("TContext", default=Any)


@dataclass(eq=False)
class _ApprovalRecord:
    """Tracks approval/rejection state for a tool.

    ``approved`` and ``rejected`` are either booleans (permanent allow/deny)
    or lists of call IDs when approval is scoped to specific tool calls.
    """

    approved: bool | list[str] = field(default_factory=list)
    rejected: bool | list[str] = field(default_factory=list)
    rejection_messages: dict[str, str] = field(default_factory=dict)
    sticky_rejection_message: str | None = None


@dataclass(eq=False)
class RunContextWrapper(Generic[TContext]):
    """This wraps the context object that you passed to `Runner.run()`. It also contains
    information about the usage of the agent run so far.

    NOTE: Contexts are not passed to the LLM. They're a way to pass dependencies and data to code
    you implement, like tool functions, callbacks, hooks, etc.
    """
    # `Generic[TContext]` 表示 context 可以是任意业务类型。
    # 例如你的 PPT Agent 可以传 dict，也可以传一个自定义 dataclass/Pydantic 对象。

    context: TContext
    """The context object (or None), passed by you to `Runner.run()`"""

    usage: Usage = field(default_factory=Usage)
    """The usage of the agent run so far. For streamed responses, the usage will be stale until the
    last chunk of the stream is processed.
    """

    turn_input: list[TResponseInputItem] = field(default_factory=list)
    _approvals: dict[str, _ApprovalRecord] = field(default_factory=dict)
    # `_approvals` 是内存态审批表：key 是工具名/命名空间组合，value 记录批准/拒绝范围。
    tool_input: Any | None = None
    """Structured input for the current agent tool run, when available."""

    @staticmethod
    def _to_str_or_none(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if value is not None:
            try:
                return str(value)
            except Exception:
                return None
        return None

    @staticmethod
    def _resolve_tool_name(approval_item: ToolApprovalItem) -> str:
        # 审批 item 可能来自 function tool、MCP、shell 等不同来源，
        # 所以工具名要从多个位置兜底解析。
        raw = approval_item.raw_item
        if approval_item.tool_name:
            return approval_item.tool_name
        candidate: Any | None
        if isinstance(raw, dict):
            candidate = raw.get("name") or raw.get("type")
        else:
            candidate = getattr(raw, "name", None) or getattr(raw, "type", None)
        return RunContextWrapper._to_str_or_none(candidate) or "unknown_tool"

    @staticmethod
    def _resolve_tool_namespace(approval_item: ToolApprovalItem) -> str | None:
        # namespace 用来区分同名工具。大型 Agent 系统里同名工具很常见，
        # 比如多个 MCP server 都有 `search`。
        raw = approval_item.raw_item
        if isinstance(approval_item.tool_namespace, str) and approval_item.tool_namespace:
            return approval_item.tool_namespace
        if isinstance(raw, dict):
            candidate = raw.get("namespace")
        else:
            candidate = getattr(raw, "namespace", None)
        return RunContextWrapper._to_str_or_none(candidate)

    @staticmethod
    def _resolve_approval_key(approval_item: ToolApprovalItem) -> str:
        # 审批 key 是恢复运行的关键：approve/reject 写入的 key 必须能在下一次工具执行时匹配回来。
        tool_name = RunContextWrapper._resolve_tool_name(approval_item)
        tool_namespace = RunContextWrapper._resolve_tool_namespace(approval_item)
        lookup_key = RunContextWrapper._resolve_tool_lookup_key(approval_item)
        approval_keys = get_function_tool_approval_keys(
            tool_name=tool_name,
            tool_namespace=tool_namespace,
            tool_lookup_key=lookup_key,
            prefer_legacy_same_name_namespace=lookup_key is None,
        )
        if approval_keys:
            return approval_keys[-1]
        return tool_qualified_name(tool_name, tool_namespace) or tool_name or "unknown_tool"

    @staticmethod
    def _resolve_approval_keys(approval_item: ToolApprovalItem) -> tuple[str, ...]:
        """Return all approval keys that should mirror this approval record."""
        # 为了兼容历史裸工具名、新命名空间工具名、deferred tool lookup key，
        # 同一次审批可能要同步写入多个候选 key。
        lookup_key = RunContextWrapper._resolve_tool_lookup_key(approval_item)
        return get_function_tool_approval_keys(
            tool_name=RunContextWrapper._resolve_tool_name(approval_item),
            tool_namespace=RunContextWrapper._resolve_tool_namespace(approval_item),
            allow_bare_name_alias=getattr(approval_item, "_allow_bare_name_alias", False),
            tool_lookup_key=lookup_key,
            prefer_legacy_same_name_namespace=lookup_key is None,
        )

    @staticmethod
    def _resolve_tool_lookup_key(approval_item: ToolApprovalItem) -> FunctionToolLookupKey | None:
        candidate = getattr(approval_item, "tool_lookup_key", None)
        if isinstance(candidate, tuple):
            return candidate

        raw = approval_item.raw_item
        if isinstance(raw, dict):
            raw_type = raw.get("type")
        else:
            raw_type = getattr(raw, "type", None)
        if raw_type != "function_call":
            return None

        tool_name = RunContextWrapper._resolve_tool_name(approval_item)
        tool_namespace = RunContextWrapper._resolve_tool_namespace(approval_item)
        if is_reserved_synthetic_tool_namespace(tool_name, tool_namespace):
            return None
        return get_function_tool_lookup_key(tool_name, tool_namespace)

    @staticmethod
    def _resolve_call_id(approval_item: ToolApprovalItem) -> str | None:
        # call_id 决定审批是“只针对这次工具调用”还是“没有具体调用 ID，只能按工具级处理”。
        raw = approval_item.raw_item
        if isinstance(raw, dict):
            provider_data = raw.get("provider_data")
            if (
                isinstance(provider_data, dict)
                and provider_data.get("type") == "mcp_approval_request"
            ):
                candidate = provider_data.get("id")
                if isinstance(candidate, str):
                    return candidate
            candidate = raw.get("call_id") or raw.get("id")
        else:
            provider_data = getattr(raw, "provider_data", None)
            if (
                isinstance(provider_data, dict)
                and provider_data.get("type") == "mcp_approval_request"
            ):
                candidate = provider_data.get("id")
                if isinstance(candidate, str):
                    return candidate
            candidate = getattr(raw, "call_id", None) or getattr(raw, "id", None)
        return RunContextWrapper._to_str_or_none(candidate)

    def _get_or_create_approval_entry(self, tool_name: str) -> _ApprovalRecord:
        approval_entry = self._approvals.get(tool_name)
        if approval_entry is None:
            approval_entry = _ApprovalRecord()
            self._approvals[tool_name] = approval_entry
        return approval_entry

    def is_tool_approved(self, tool_name: str, call_id: str) -> bool | None:
        """Return True/False/None for the given tool call."""
        # 返回值三态：True=允许执行，False=拒绝执行，None=还没有决定，需要中断/审批。
        return self._get_approval_status_for_key(tool_name, call_id)

    def _get_approval_status_for_key(self, approval_key: str, call_id: str) -> bool | None:
        """Return True/False/None for a concrete approval key and tool call."""
        approval_entry = self._approvals.get(approval_key)
        if not approval_entry:
            return None

        # Check for permanent approval/rejection
        if approval_entry.approved is True and approval_entry.rejected is True:
            # Approval takes precedence
            return True

        if approval_entry.approved is True:
            return True

        if approval_entry.rejected is True:
            return False

        approved_ids = (
            set(approval_entry.approved) if isinstance(approval_entry.approved, list) else set()
        )
        rejected_ids = (
            set(approval_entry.rejected) if isinstance(approval_entry.rejected, list) else set()
        )

        if call_id in approved_ids:
            return True
        if call_id in rejected_ids:
            return False
        # Per-call approvals are scoped to the exact call ID, so other calls require a new decision.
        return None

    @staticmethod
    def _clear_rejection_message(record: _ApprovalRecord, call_id: str | None) -> None:
        if call_id is None:
            return
        record.rejection_messages.pop(call_id, None)

    @staticmethod
    def _get_rejection_message_for_key(record: _ApprovalRecord, call_id: str) -> str | None:
        if record.rejected is True:
            if call_id in record.rejection_messages:
                return record.rejection_messages[call_id]
            return record.sticky_rejection_message
        if isinstance(record.rejected, list) and call_id in record.rejected:
            return record.rejection_messages.get(call_id)
        return None

    @staticmethod
    def _restore_approval_value(value: Any) -> bool | list[str]:
        if isinstance(value, bool):
            return value
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []

    def get_rejection_message(
        self,
        tool_name: str,
        call_id: str,
        *,
        tool_namespace: str | None = None,
        existing_pending: ToolApprovalItem | None = None,
        tool_lookup_key: FunctionToolLookupKey | None = None,
    ) -> str | None:
        """Return a stored rejection message for a tool call if one exists."""
        # 拒绝工具时可以带一句反馈给模型，例如“不能覆盖用户文件，请改为新建副本”。
        # 恢复运行时模型会拿到这句话，用来调整后续计划。
        candidates: list[str] = []
        explicit_namespace = (
            tool_namespace if isinstance(tool_namespace, str) and tool_namespace else None
        )
        pending_namespace = (
            self._resolve_tool_namespace(existing_pending) if existing_pending is not None else None
        )
        pending_key = self._resolve_approval_key(existing_pending) if existing_pending else None
        pending_tool_name = self._resolve_tool_name(existing_pending) if existing_pending else None
        pending_keys = (
            list(self._resolve_approval_keys(existing_pending))
            if existing_pending is not None
            else []
        )

        if existing_pending and pending_key is not None:
            candidates.append(pending_key)
        explicit_keys = (
            list(
                get_function_tool_approval_keys(
                    tool_name=tool_name,
                    tool_namespace=explicit_namespace,
                    tool_lookup_key=tool_lookup_key,
                    include_legacy_deferred_key=True,
                )
            )
            if explicit_namespace is not None or tool_lookup_key is not None
            else []
        )
        for explicit_key in explicit_keys:
            if explicit_key not in candidates:
                candidates.append(explicit_key)
        if not explicit_keys and pending_namespace and pending_key is not None:
            if pending_key not in candidates:
                candidates.append(pending_key)
        if (
            explicit_namespace is None
            and tool_lookup_key is None
            and existing_pending is None
            and tool_name not in candidates
        ):
            candidates.append(tool_name)
        if existing_pending:
            for pending_candidate in pending_keys:
                if pending_candidate not in candidates:
                    candidates.append(pending_candidate)
            if (
                pending_namespace is None
                and pending_tool_name is not None
                and pending_tool_name not in candidates
            ):
                candidates.append(pending_tool_name)

        for candidate in candidates:
            approval_entry = self._approvals.get(candidate)
            if not approval_entry:
                continue
            message = self._get_rejection_message_for_key(approval_entry, call_id)
            if message is not None:
                return message
        return None

    def _apply_approval_decision(
        self,
        approval_item: ToolApprovalItem,
        *,
        always: bool,
        approve: bool,
        rejection_message: str | None = None,
    ) -> None:
        """Record an approval or rejection decision."""
        # `always=True` 表示永久批准/拒绝这个工具；否则只记录当前 call_id。
        # 这对应产品里的“仅本次允许”和“始终允许”两种按钮。
        approval_keys = self._resolve_approval_keys(approval_item) or ("unknown_tool",)
        exact_approval_key = self._resolve_approval_key(approval_item)
        call_id = self._resolve_call_id(approval_item)
        decision_keys = (exact_approval_key,) if always or call_id is None else approval_keys

        for approval_key in decision_keys:
            approval_entry = self._get_or_create_approval_entry(approval_key)
            if always or call_id is None:
                approval_entry.approved = approve
                approval_entry.rejected = [] if approve else True
                if not approve:
                    approval_entry.approved = False
                    if rejection_message is not None and call_id is not None:
                        approval_entry.rejection_messages[call_id] = rejection_message
                    elif call_id is not None:
                        self._clear_rejection_message(approval_entry, call_id)
                    approval_entry.sticky_rejection_message = rejection_message
                else:
                    approval_entry.rejection_messages.clear()
                    approval_entry.sticky_rejection_message = None
                continue

            opposite = approval_entry.rejected if approve else approval_entry.approved
            if isinstance(opposite, list) and call_id in opposite:
                opposite.remove(call_id)

            target = approval_entry.approved if approve else approval_entry.rejected
            if isinstance(target, list) and call_id not in target:
                target.append(call_id)
            if approve:
                self._clear_rejection_message(approval_entry, call_id)
            elif call_id is not None:
                if rejection_message is not None:
                    approval_entry.rejection_messages[call_id] = rejection_message
                else:
                    self._clear_rejection_message(approval_entry, call_id)

    def approve_tool(self, approval_item: ToolApprovalItem, always_approve: bool = False) -> None:
        """Approve a tool call, optionally for all future calls."""
        # 对外暴露的批准入口，通常由 `RunState.approve(...)` 间接调用。
        self._apply_approval_decision(
            approval_item,
            always=always_approve,
            approve=True,
        )

    def reject_tool(
        self,
        approval_item: ToolApprovalItem,
        always_reject: bool = False,
        rejection_message: str | None = None,
    ) -> None:
        """Reject a tool call, optionally for all future calls."""
        # 对外暴露的拒绝入口；可附带 rejection_message 让模型知道拒绝原因。
        self._apply_approval_decision(
            approval_item,
            always=always_reject,
            approve=False,
            rejection_message=rejection_message,
        )

    def get_approval_status(
        self,
        tool_name: str,
        call_id: str,
        *,
        tool_namespace: str | None = None,
        existing_pending: ToolApprovalItem | None = None,
        tool_lookup_key: FunctionToolLookupKey | None = None,
    ) -> bool | None:
        """Return approval status, retrying with pending item's tool name if necessary."""
        # 执行工具前会调用这里。它会按多个候选 key 查找审批记录，
        # 以兼容“同名工具、命名空间工具、旧格式恢复”等情况。
        candidates: list[str] = []
        explicit_namespace = (
            tool_namespace if isinstance(tool_namespace, str) and tool_namespace else None
        )
        pending_namespace = (
            self._resolve_tool_namespace(existing_pending) if existing_pending is not None else None
        )
        pending_key = self._resolve_approval_key(existing_pending) if existing_pending else None
        pending_tool_name = self._resolve_tool_name(existing_pending) if existing_pending else None
        pending_keys = (
            list(self._resolve_approval_keys(existing_pending))
            if existing_pending is not None
            else []
        )

        if existing_pending and pending_key is not None:
            candidates.append(pending_key)
        explicit_keys = (
            list(
                get_function_tool_approval_keys(
                    tool_name=tool_name,
                    tool_namespace=explicit_namespace,
                    tool_lookup_key=tool_lookup_key,
                    include_legacy_deferred_key=True,
                )
            )
            if explicit_namespace is not None or tool_lookup_key is not None
            else []
        )
        for explicit_key in explicit_keys:
            if explicit_key not in candidates:
                candidates.append(explicit_key)
        if not explicit_keys and pending_namespace and pending_key is not None:
            if pending_key not in candidates:
                candidates.append(pending_key)
        if (
            explicit_namespace is None
            and tool_lookup_key is None
            and existing_pending is None
            and tool_name not in candidates
        ):
            candidates.append(tool_name)
        if existing_pending:
            for pending_candidate in pending_keys:
                if pending_candidate not in candidates:
                    candidates.append(pending_candidate)
            if (
                pending_namespace is None
                and pending_tool_name is not None
                and pending_tool_name not in candidates
            ):
                candidates.append(pending_tool_name)

        status: bool | None = None
        for candidate in candidates:
            status = self._get_approval_status_for_key(candidate, call_id)
            if status is not None:
                break
        return status

    def _rebuild_approvals(self, approvals: Any) -> None:
        """Restore approvals from serialized state."""
        # RunState 从 JSON 恢复时会把审批表重建回 `_approvals`，
        # 所以审批记录可以跨进程/跨请求保存。
        self._approvals = {}
        if not isinstance(approvals, Mapping):
            return
        for tool_name, record_dict in approvals.items():
            if not isinstance(tool_name, str) or not isinstance(record_dict, dict):
                continue
            record = _ApprovalRecord()
            record.approved = self._restore_approval_value(record_dict.get("approved", []))
            record.rejected = self._restore_approval_value(record_dict.get("rejected", []))
            rejection_messages = record_dict.get("rejection_messages", {})
            if isinstance(rejection_messages, dict):
                record.rejection_messages = {
                    str(call_id): message
                    for call_id, message in rejection_messages.items()
                    if isinstance(message, str)
                }
            sticky_rejection_message = record_dict.get("sticky_rejection_message")
            if isinstance(sticky_rejection_message, str):
                record.sticky_rejection_message = sticky_rejection_message
            self._approvals[tool_name] = record

    def _fork_with_tool_input(self, tool_input: Any) -> RunContextWrapper[TContext]:
        """Create a child context that shares approvals and usage with tool input set."""
        # 工具运行时可能需要一个“子 context”：共享 usage/审批表，但额外挂上当前工具输入。
        # 这样 hook/guardrail 可以知道当前工具拿到的结构化参数。
        fork = RunContextWrapper(context=self.context)
        fork.usage = self.usage
        fork._approvals = self._approvals
        fork.turn_input = self.turn_input
        fork.tool_input = tool_input
        return fork

    def _fork_without_tool_input(self) -> RunContextWrapper[TContext]:
        """Create a child context that shares approvals and usage without tool input."""
        # 有些 hook 不需要工具输入，但仍要共享 usage 和 approvals。
        fork = RunContextWrapper(context=self.context)
        fork.usage = self.usage
        fork._approvals = self._approvals
        fork.turn_input = self.turn_input
        return fork


@dataclass(eq=False)
class AgentHookContext(RunContextWrapper[TContext]):
    """Context passed to agent hooks (on_start, on_end)."""
    # Agent hook 专用 context，目前继承 RunContextWrapper，方便未来扩展 hook 场景字段。
