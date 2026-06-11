"""中文学习提示：所有 sandbox capability 的抽象基类。

这里是“能力插件”的共同协议：每个能力都可以声明依赖、绑定运行中的
SandboxSession、返回工具列表、追加系统指令、改写上下文或补充采样参数。
阅读重点是 `bind()`、`tools()`、`instructions()`，它们决定 agent 在运行时
真正能看到什么能力。
"""

import asyncio
import copy
import threading
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...items import TResponseInputItem
from ...tool import Tool
from ..manifest import Manifest
from ..session.base_sandbox_session import BaseSandboxSession
from ..types import User


class Capability(BaseModel):
    """沙箱能力基类。

    `session` 是运行中的沙箱会话，`run_as` 是工具操作使用的系统用户身份。
    这两个字段被排除在 Pydantic 序列化之外，因为它们是运行时对象，不属于配置。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    type: str
    session: BaseSandboxSession | None = Field(default=None, exclude=True)
    run_as: User | None = Field(default=None, exclude=True)

    def clone(self) -> "Capability":
        """Return a per-run copy of this capability.

        中文说明：每次 run 都复制一份能力配置，避免一个会话里的运行时状态泄漏到
        另一轮调用；但工具、锁、会话等不可深拷贝对象会由 `_clone_capability_value`
        做特殊处理。
        """

        cloned = self.model_copy(deep=False)
        for name, value in self.__dict__.items():
            cloned.__dict__[name] = _clone_capability_value(value)
        return cloned

    def bind(self, session: BaseSandboxSession) -> None:
        """Bind a live session to this plugin (default no-op).

        中文说明：Runner 准备沙箱时会把真实会话注入 capability，之后工具才能
        调用 `session.read/write/exec` 等方法。
        """

        self.session = session

    def bind_run_as(self, user: User | None) -> None:
        """Bind the sandbox user identity for model-facing operations."""
        self.run_as = user

    def required_capability_types(self) -> set[str]:
        """Return capability types that must be present alongside this capability."""
        return set()

    def tools(self) -> list[Tool]:
        """返回要暴露给模型调用的工具列表；默认没有工具。"""

        return []

    def process_manifest(self, manifest: Manifest) -> Manifest:
        return manifest

    async def instructions(self, manifest: Manifest) -> str | None:
        """Return a deterministic instruction fragment appended during run preparation."""
        _ = manifest
        return None

    def sampling_params(self, sampling_params: dict[str, Any]) -> dict[str, Any]:
        """Return additional model request parameters needed for this capability."""
        _ = sampling_params
        return {}

    def process_context(self, context: list[TResponseInputItem]) -> list[TResponseInputItem]:
        """Transform the model input context before sampling."""
        return context


def _clone_capability_value(value: Any) -> Any:
    """按对象类型决定 capability 字段如何复制。

    中文说明：普通配置深拷贝；会话、锁、事件、工具这类运行时对象保持引用。
    这是一个容易忽略的点：agent 系统里很多对象不是纯数据，不能盲目 deepcopy。
    """

    if getattr(type(value), "__module__", "").startswith("agents.tool"):
        return value
    if isinstance(
        value,
        BaseSandboxSession
        | asyncio.Event
        | asyncio.Lock
        | asyncio.Semaphore
        | asyncio.Condition
        | threading.Event
        | type(threading.Lock())
        | type(threading.RLock()),
    ):
        return value
    if isinstance(value, list):
        return [_clone_capability_value(item) for item in value]
    if isinstance(value, dict):
        return {
            _clone_capability_value(key): _clone_capability_value(item)
            for key, item in value.items()
        }
    if isinstance(value, set):
        return {_clone_capability_value(item) for item in value}
    if isinstance(value, tuple):
        return tuple(_clone_capability_value(item) for item in value)
    if isinstance(value, bytearray):
        return bytearray(value)
    if hasattr(value, "__dict__"):
        cloned = copy.copy(value)
        for name, nested in value.__dict__.items():
            setattr(cloned, name, _clone_capability_value(nested))
        return cloned
    try:
        return copy.deepcopy(value)
    except Exception:
        return value
    return value
