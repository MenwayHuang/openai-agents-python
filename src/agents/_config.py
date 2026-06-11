"""SDK 全局默认配置入口。

中文学习说明：
- 这里设置默认 OpenAI key/client、默认使用 Responses 还是 Chat Completions、Responses transport。
- 这些是进程级默认值，适合 demo 或简单应用；生产服务更建议通过依赖注入/配置对象显式传递。
- 注意：真实 API key 不应该写进代码仓库，应来自环境变量或密钥系统。
"""

from typing import Literal

from openai import AsyncOpenAI

from .models import _openai_shared
from .models.openai_agent_registration import (
    OpenAIAgentRegistrationConfig,
    set_default_openai_agent_registration_config,
)
from .tracing import set_tracing_export_api_key


def set_default_openai_key(key: str, use_for_tracing: bool) -> None:
    # 设置默认 OpenAI API key；use_for_tracing=True 时也把它用于 tracing 导出。
    _openai_shared.set_default_openai_key(key)

    if use_for_tracing:
        set_tracing_export_api_key(key)


def set_default_openai_client(client: AsyncOpenAI, use_for_tracing: bool) -> None:
    _openai_shared.set_default_openai_client(client)

    if use_for_tracing:
        set_tracing_export_api_key(client.api_key)


def set_default_openai_api(api: Literal["chat_completions", "responses"]) -> None:
    # 控制字符串模型默认走 Chat Completions 还是 Responses。
    if api == "chat_completions":
        _openai_shared.set_use_responses_by_default(False)
    else:
        _openai_shared.set_use_responses_by_default(True)


def set_default_openai_responses_transport(transport: Literal["http", "websocket"]) -> None:
    if transport not in {"http", "websocket"}:
        raise ValueError(
            "Invalid OpenAI Responses transport. Expected one of: 'http', 'websocket'."
        )
    _openai_shared.set_default_openai_responses_transport(transport)


def set_default_openai_agent_registration(
    config: OpenAIAgentRegistrationConfig | None,
) -> None:
    set_default_openai_agent_registration_config(config)


def set_default_openai_harness(harness_id: str | None) -> None:
    if harness_id is None:
        set_default_openai_agent_registration_config(None)
        return

    set_default_openai_agent_registration_config(
        OpenAIAgentRegistrationConfig(harness_id=harness_id)
    )
