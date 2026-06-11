from __future__ import annotations

from typing import Literal

from openai import AsyncOpenAI

OpenAIResponsesTransport = Literal["http", "websocket"]

_default_openai_key: str | None = None
_default_openai_client: AsyncOpenAI | None = None
_use_responses_by_default: bool = True
# Source of truth for the default Responses transport.
_default_openai_responses_transport: OpenAIResponsesTransport = "http"
# Backward-compatibility shim for internal code/tests that still mutate the legacy flag directly.
_use_responses_websocket_by_default: bool = False

# 学习提示：这个文件保存 OpenAI Provider 的进程级默认配置，例如默认 API Key、
# 默认 AsyncOpenAI 客户端、默认使用 Responses 还是 Chat Completions。
# 自研项目里不建议到处读写全局配置，更适合通过依赖注入/配置对象集中管理。


def set_default_openai_key(key: str) -> None:
    # 设置默认 key，供未显式传 client/key 的模型 Provider 使用。
    global _default_openai_key
    _default_openai_key = key


def get_default_openai_key() -> str | None:
    return _default_openai_key


def set_default_openai_client(client: AsyncOpenAI) -> None:
    # 直接复用调用方创建好的 AsyncOpenAI 客户端，可包含代理、超时、base_url 等配置。
    global _default_openai_client
    _default_openai_client = client


def get_default_openai_client() -> AsyncOpenAI | None:
    return _default_openai_client


def set_use_responses_by_default(use_responses: bool) -> None:
    # 控制默认走 Responses API 还是 Chat Completions API。
    global _use_responses_by_default
    _use_responses_by_default = use_responses


def get_use_responses_by_default() -> bool:
    return _use_responses_by_default


def set_use_responses_websocket_by_default(use_responses_websocket: bool) -> None:
    set_default_openai_responses_transport("websocket" if use_responses_websocket else "http")


def get_use_responses_websocket_by_default() -> bool:
    return get_default_openai_responses_transport() == "websocket"


def set_default_openai_responses_transport(transport: OpenAIResponsesTransport) -> None:
    # 同步维护新字段和旧兼容字段，保证老测试或内部代码直接改私有变量时仍能工作。
    global _default_openai_responses_transport
    global _use_responses_websocket_by_default
    _default_openai_responses_transport = transport
    _use_responses_websocket_by_default = transport == "websocket"


def get_default_openai_responses_transport() -> OpenAIResponsesTransport:
    global _default_openai_responses_transport
    # Respect direct writes to the legacy private flag (used in tests) by syncing on read.
    legacy_transport: OpenAIResponsesTransport = (
        "websocket" if _use_responses_websocket_by_default else "http"
    )
    if _default_openai_responses_transport != legacy_transport:
        _default_openai_responses_transport = legacy_transport
    return _default_openai_responses_transport
