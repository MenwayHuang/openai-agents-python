from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_DISABLE_PROVIDER_MANAGED_RETRIES: ContextVar[bool] = ContextVar(
    "disable_provider_managed_retries",
    default=False,
)
_DISABLE_WEBSOCKET_PRE_EVENT_RETRIES: ContextVar[bool] = ContextVar(
    "disable_websocket_pre_event_retries",
    default=False,
)

# 学习提示：ContextVar 是 Python 的“异步上下文局部变量”，比全局变量更适合 asyncio。
# 这里用它在某段调用链内临时关闭 provider 自带重试或 WebSocket 早期重试，
# 不会污染其它并发请求。


@contextmanager
def provider_managed_retries_disabled(disabled: bool) -> Iterator[None]:
    # @contextmanager 让普通生成器函数变成 with 上下文管理器；
    # yield 前设置上下文值，finally 里恢复，避免异常时状态泄漏。
    token = _DISABLE_PROVIDER_MANAGED_RETRIES.set(disabled)
    try:
        yield
    finally:
        _DISABLE_PROVIDER_MANAGED_RETRIES.reset(token)


def should_disable_provider_managed_retries() -> bool:
    # 模型层在真正调用 Provider 前会读取这个开关。
    return _DISABLE_PROVIDER_MANAGED_RETRIES.get()


@contextmanager
def websocket_pre_event_retries_disabled(disabled: bool) -> Iterator[None]:
    # 控制 WebSocket 在尚未收到事件前是否允许自动重试。
    token = _DISABLE_WEBSOCKET_PRE_EVENT_RETRIES.set(disabled)
    try:
        yield
    finally:
        _DISABLE_WEBSOCKET_PRE_EVENT_RETRIES.reset(token)


def should_disable_websocket_pre_event_retries() -> bool:
    # 这个函数隐藏 ContextVar 细节，让调用方只关心布尔开关。
    return _DISABLE_WEBSOCKET_PRE_EVENT_RETRIES.get()
