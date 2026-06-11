from __future__ import annotations

from dataclasses import dataclass
from typing import Generic

from ..agent import Agent
from ..run_context import TContext

# 学习提示：AgentBindings 同时保存 public_agent 和 execution_agent。
# 普通运行二者相同；sandbox 等执行重写场景下，模型实际运行的是 execution_agent，
# 但对用户回调/结果展示仍应暴露 public_agent。

__all__ = [
    "AgentBindings",
    "bind_execution_agent",
    "bind_public_agent",
]


@dataclass(frozen=True)
class AgentBindings(Generic[TContext]):
    """Carry the public and execution agent identities for a turn."""

    public_agent: Agent[TContext]
    execution_agent: Agent[TContext]


def bind_public_agent(agent: Agent[TContext]) -> AgentBindings[TContext]:
    """Build bindings for non-rewritten execution where both identities are the same."""
    return AgentBindings(public_agent=agent, execution_agent=agent)


def bind_execution_agent(
    *,
    public_agent: Agent[TContext],
    execution_agent: Agent[TContext],
) -> AgentBindings[TContext]:
    """Build bindings for execution-only clones such as sandbox-prepared agents."""
    return AgentBindings(
        public_agent=public_agent,
        execution_agent=execution_agent,
    )
