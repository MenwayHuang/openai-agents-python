"""Session 抽象：保存多轮对话历史。

中文学习说明：
- Session 不是“大模型记忆”，而是 SDK 在本地/数据库里保存的 conversation input items。
- Runner 每轮运行前从 Session 读历史，运行后把新消息/工具结果写回 Session。
- 对 PPT Agent 来说，Session 可以对应“某个 PPT 项目的对话历史/生成历史”，后续生产化时
  可用数据库实现这个协议，而不是只靠内存或前端 localStorage。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal, Protocol, TypeGuard, runtime_checkable

from typing_extensions import TypedDict

if TYPE_CHECKING:
    from ..items import TResponseInputItem
    from .session_settings import SessionSettings


@runtime_checkable
class Session(Protocol):
    """Protocol for session implementations.

    Session stores conversation history for a specific session, allowing
    agents to maintain context without requiring explicit manual memory management.
    """
    # Protocol 是 Python 的“结构化接口”：实现类不必继承 Session，
    # 只要拥有同名属性/方法，就被认为满足协议。`runtime_checkable` 允许 isinstance 检查。

    session_id: str
    session_settings: SessionSettings | None = None

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Retrieve the conversation history for this session.

        Args:
            limit: Maximum number of items to retrieve. If None, retrieves all items.
                   When specified, returns the latest N items in chronological order.

        Returns:
            List of input items representing the conversation history
        """
        ...

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Add new items to the conversation history.

        Args:
            items: List of input items to add to the history
        """
        ...

    async def pop_item(self) -> TResponseInputItem | None:
        """Remove and return the most recent item from the session.

        Returns:
            The most recent item if it exists, None if the session is empty
        """
        ...

    async def clear_session(self) -> None:
        """Clear all items for this session."""
        ...


class SessionABC(ABC):
    """Abstract base class for session implementations.

    Session stores conversation history for a specific session, allowing
    agents to maintain context without requiring explicit manual memory management.

    This ABC is intended for internal use and as a base class for concrete implementations.
    Third-party libraries should implement the Session protocol instead.
    """
    # ABC 是显式抽象基类：子类必须实现 abstractmethod。
    # Protocol 更适合第三方鸭子类型，ABC 更适合 SDK 内部基类。

    session_id: str
    session_settings: SessionSettings | None = None

    @abstractmethod
    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Retrieve the conversation history for this session.

        Args:
            limit: Maximum number of items to retrieve. If None, retrieves all items.
                   When specified, returns the latest N items in chronological order.

        Returns:
            List of input items representing the conversation history
        """
        ...

    @abstractmethod
    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Add new items to the conversation history.

        Args:
            items: List of input items to add to the history
        """
        ...

    @abstractmethod
    async def pop_item(self) -> TResponseInputItem | None:
        """Remove and return the most recent item from the session.

        Returns:
            The most recent item if it exists, None if the session is empty
        """
        ...

    @abstractmethod
    async def clear_session(self) -> None:
        """Clear all items for this session."""
        ...


class OpenAIResponsesCompactionArgs(TypedDict, total=False):
    """Arguments for the run_compaction method."""
    # TypedDict 描述 dict 的字段类型；total=False 表示字段都不是必填。
    # 这里用于传递 Responses API 历史压缩参数。

    response_id: str
    """The ID of the last response to use for compaction."""

    compaction_mode: Literal["previous_response_id", "input", "auto"]
    """How to provide history for compaction.

    - "auto": Use input when the last response was not stored or no response ID is available.
    - "previous_response_id": Use server-managed response history.
    - "input": Send locally stored session items as input.
    """

    store: bool
    """Whether the last model response was stored on the server.

    When set to False, compaction should avoid "previous_response_id" unless explicitly requested.
    """

    force: bool
    """Whether to force compaction even if the threshold is not met."""


@runtime_checkable
class OpenAIResponsesCompactionAwareSession(Session, Protocol):
    """Protocol for session implementations that support responses compaction."""
    # 支持 compaction 的 Session 可以在上下文太长时压缩历史，降低 token 成本和超长风险。

    async def run_compaction(self, args: OpenAIResponsesCompactionArgs | None = None) -> None:
        """Run the compaction process for the session."""
        ...


def is_openai_responses_compaction_aware_session(
    session: Session | None,
) -> TypeGuard[OpenAIResponsesCompactionAwareSession]:
    """Check if a session supports responses compaction."""
    # TypeGuard 是类型收窄工具：返回 True 后，类型检查器知道 session 支持 run_compaction。
    if session is None:
        return False
    try:
        run_compaction = getattr(session, "run_compaction", None)
    except Exception:
        return False
    return callable(run_compaction)
