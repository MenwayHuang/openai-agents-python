"""模型接入抽象接口。

中文学习说明：
- Agent runtime 不直接依赖某一个具体 API，而是通过 `Model` 接口调用 LLM。
- `get_response()` 是普通非流式调用；`stream_response()` 是流式调用。
- `ModelProvider` 负责按模型名返回具体 Model 实例。你未来自研 Agent 时，可以用同样方式
  把 OpenAI、Claude、本地模型或自建网关封装成统一接口。
"""

from __future__ import annotations

import abc
import enum
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from openai.types.responses.response_prompt_param import ResponsePromptParam

from ..agent_output import AgentOutputSchemaBase
from ..handoffs import Handoff
from ..items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from ..tool import Tool

if TYPE_CHECKING:
    from ..model_settings import ModelSettings
    from ..retry import ModelRetryAdvice, ModelRetryAdviceRequest


class ModelTracing(enum.Enum):
    # 模型调用的 trace 开关。生产环境常用 ENABLED_WITHOUT_DATA，
    # 保留调用链路和 usage，但不记录完整输入输出，降低隐私风险。
    DISABLED = 0
    """Tracing is disabled entirely."""

    ENABLED = 1
    """Tracing is enabled, and all data is included."""

    ENABLED_WITHOUT_DATA = 2
    """Tracing is enabled, but inputs/outputs are not included."""

    def is_disabled(self) -> bool:
        return self == ModelTracing.DISABLED

    def include_data(self) -> bool:
        return self == ModelTracing.ENABLED


class Model(abc.ABC):
    """The base interface for calling an LLM."""
    # 抽象基类定义模型能力边界。Runner 只认识这个接口，不关心底层是 Responses、
    # Chat Completions、WebSocket，还是你自己的 Go/Python API 网关。

    async def close(self) -> None:
        """Release any resources held by the model.

        Models that maintain persistent connections can override this. The default implementation
        is a no-op.
        """
        # 某些模型实现会持有 HTTP/WebSocket 连接；默认 no-op，子类可覆写清理资源。
        return None

    def get_retry_advice(self, request: ModelRetryAdviceRequest) -> ModelRetryAdvice | None:
        """Return provider-specific retry guidance for a failed model request.

        Models can override this to surface transport- or provider-specific hints such as replay
        safety, retry-after delays, or explicit server retry guidance.
        """
        # 不同 provider 的错误重试语义不同，例如请求是否已经被服务端接收。
        # 子类可提供“是否建议重试、重放是否安全”等信息。
        return None

    @abc.abstractmethod
    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        """Get a response from the model.

        Args:
            system_instructions: The system instructions to use.
            input: The input items to the model, in OpenAI Responses format.
            model_settings: The model settings to use.
            tools: The tools available to the model.
            output_schema: The output schema to use.
            handoffs: The handoffs available to the model.
            tracing: Tracing configuration.
            previous_response_id: the ID of the previous response. Generally not used by the model,
                except for the OpenAI Responses API.
            conversation_id: The ID of the stored conversation, if any.
            prompt: The prompt config to use for the model.

        Returns:
            The full model response.
        """
        # 返回 SDK 内部统一的 ModelResponse，而不是直接返回 provider 原始对象。
        # 这能让后续工具解析、handoff、guardrail 都走统一流程。
        pass

    @abc.abstractmethod
    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        """Stream a response from the model.

        Args:
            system_instructions: The system instructions to use.
            input: The input items to the model, in OpenAI Responses format.
            model_settings: The model settings to use.
            tools: The tools available to the model.
            output_schema: The output schema to use.
            handoffs: The handoffs available to the model.
            tracing: Tracing configuration.
            previous_response_id: the ID of the previous response. Generally not used by the model,
                except for the OpenAI Responses API.
            conversation_id: The ID of the stored conversation, if any.
            prompt: The prompt config to use for the model.

        Returns:
            An iterator of response stream events, in OpenAI Responses format.
        """
        # 返回 AsyncIterator，调用方可以 `async for event in model.stream_response(...)`。
        # 流式事件统一采用 Responses 格式，Chat Completions 也会被转换成这个格式。
        pass


class ModelProvider(abc.ABC):
    """The base interface for a model provider.

    Model provider is responsible for looking up Models by name.
    """
    # Provider 是模型注册/查找层。RunConfig 里设置 model_provider 后，
    # Runner 会通过它把字符串模型名解析成具体 Model。

    @abc.abstractmethod
    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name.

        Args:
            model_name: The name of the model to get.

        Returns:
            The model.
        """

    async def aclose(self) -> None:
        """Release any resources held by the provider.

        Providers that cache persistent models or network connections can override this. The
        default implementation is a no-op.
        """
        return None
