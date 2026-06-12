"""OpenAI 模型 Provider。

中文学习说明：
- OpenAIProvider 根据配置决定返回 ResponsesModel、ResponsesWSModel 或 ChatCompletionsModel。
- 它负责创建/复用 AsyncOpenAI client，并共享 httpx 连接池以降低延迟和资源消耗。
- 对 PPT Agent 来说，正式后端建议把 provider/client 作为应用级依赖管理，而不是每次请求都新建。
"""

from __future__ import annotations

# 中文导入说明：
# - os 用于读取环境变量，例如 OPENAI_API_KEY、OPENAI_BASE_URL。
# - weakref 用于缓存 WebSocket Model 时不强行延长事件循环生命周期。
# - httpx.AsyncClient 是共享连接池；DefaultAsyncHttpxClient 是 OpenAI SDK 提供的默认异步 HTTP 客户端。
# - AsyncOpenAI 是 OpenAI 官方异步客户端，Provider 会创建或复用它。

import asyncio
import os
import weakref

import httpx
from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from . import _openai_shared
from .default_models import get_default_model
from .interface import Model, ModelProvider
from .openai_agent_registration import (
    OpenAIAgentRegistrationConfig,
    ResolvedOpenAIAgentRegistrationConfig,
    resolve_openai_agent_registration_config,
)
from .openai_chatcompletions import OpenAIChatCompletionsModel
from .openai_responses import (
    OpenAIResponsesModel,
    OpenAIResponsesWebSocketOptions,
    OpenAIResponsesWSModel,
)

# This is kept for backward compatibility but using get_default_model() method is recommended.
DEFAULT_MODEL: str = "gpt-4o"


_http_client: httpx.AsyncClient | None = None
_WSModelCacheKey = tuple[str, bool]
_WSLoopModelCache = dict[_WSModelCacheKey, Model]


# If we create a new httpx client for each request, that would mean no sharing of connection pools,
# which would mean worse latency and resource usage. So, we share the client across requests.
def shared_http_client() -> httpx.AsyncClient:
    # 共享 httpx client 可以复用连接池，避免每次模型调用都重新建连接。
    global _http_client
    if _http_client is None:
        _http_client = DefaultAsyncHttpxClient()
    return _http_client


class OpenAIProvider(ModelProvider):
    # OpenAIProvider 是 ModelProvider 的具体实现，负责按模型名创建/缓存 Model。
    #
    # 它本身不直接代表某一次 LLM 调用，而是负责回答：
    # - 当前应该走 Responses 还是 Chat Completions。
    # - 当前应该走 HTTP 还是 Responses WebSocket。
    # - AsyncOpenAI client 应该如何创建和复用。
    # - 如果 model_name 为空，应该用哪个默认模型。
    #
    # 因此 `OpenAIProvider.get_model("gpt-5.4-mini")` 返回的才是具体可调用的
    # `OpenAIResponsesModel`、`OpenAIResponsesWSModel` 或 `OpenAIChatCompletionsModel`。
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        websocket_base_url: str | None = None,
        openai_client: AsyncOpenAI | None = None,
        organization: str | None = None,
        project: str | None = None,
        use_responses: bool | None = None,
        use_responses_websocket: bool | None = None,
        strict_feature_validation: bool = False,
        agent_registration: OpenAIAgentRegistrationConfig | None = None,
        responses_websocket_options: OpenAIResponsesWebSocketOptions | None = None,
    ) -> None:
        """Create a new OpenAI provider.

        Args:
            api_key: The API key to use for the OpenAI client. If not provided, we will use the
                default API key.
            base_url: The base URL to use for the OpenAI client. If not provided, we will use the
                default base URL.
            websocket_base_url: The websocket base URL to use for the OpenAI client. If not
                provided, we will use the OPENAI_WEBSOCKET_BASE_URL environment variable when set.
            openai_client: An optional OpenAI client to use. If not provided, we will create a new
                OpenAI client using the api_key and base_url.
            organization: The organization to use for the OpenAI client.
            project: The project to use for the OpenAI client.
            use_responses: Whether to use the OpenAI responses API.
            use_responses_websocket: Whether to use websocket transport for the OpenAI responses
                API.
            strict_feature_validation: Whether Chat Completions models should raise a UserError
                when callers pass Responses-only features such as previous_response_id,
                conversation_id, prompt, or non-text-only tool outputs. Defaults to False, which
                preserves the default compatibility behavior.
            agent_registration: Optional agent registration configuration.
            responses_websocket_options: Optional low-level websocket keepalive options for the
                OpenAI Responses websocket transport.
        """
        if openai_client is not None:
            assert api_key is None and base_url is None and websocket_base_url is None, (
                "Don't provide api_key, base_url, or websocket_base_url if you provide "
                "openai_client"
            )
            self._client: AsyncOpenAI | None = openai_client
        else:
            self._client = None
            self._stored_api_key = api_key
            self._stored_base_url = base_url
            self._stored_websocket_base_url = websocket_base_url
            self._stored_organization = organization
            self._stored_project = project

        if use_responses is not None:
            self._use_responses = use_responses
        else:
            self._use_responses = _openai_shared.get_use_responses_by_default()

        if use_responses_websocket is not None:
            self._responses_transport: _openai_shared.OpenAIResponsesTransport = (
                "websocket" if use_responses_websocket else "http"
            )
        else:
            self._responses_transport = _openai_shared.get_default_openai_responses_transport()
        # Backward-compatibility shim for internal tests/diagnostics that inspect the legacy flag.
        self._use_responses_websocket = self._responses_transport == "websocket"
        self._strict_feature_validation = strict_feature_validation
        self._responses_websocket_options = responses_websocket_options

        # Reuse websocket model wrappers so websocket transport can keep a persistent connection
        # when callers pass model names as strings through a shared provider.
        self._ws_model_cache_by_loop: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, _WSLoopModelCache
        ] = weakref.WeakKeyDictionary()
        self._agent_registration = resolve_openai_agent_registration_config(agent_registration)

    @property
    def agent_registration(self) -> ResolvedOpenAIAgentRegistrationConfig | None:
        return self._agent_registration

    # We lazy load the client in case you never actually use OpenAIProvider(). Otherwise
    # AsyncOpenAI() raises an error if you don't have an API key set.
    def _get_client(self) -> AsyncOpenAI:
        # 懒加载 client：只有真的调用模型时才要求 API key 存在。
        if self._client is None:
            self._client = _openai_shared.get_default_openai_client() or AsyncOpenAI(
                api_key=self._stored_api_key or _openai_shared.get_default_openai_key(),
                base_url=self._stored_base_url or os.getenv("OPENAI_BASE_URL"),
                websocket_base_url=(
                    self._stored_websocket_base_url or os.getenv("OPENAI_WEBSOCKET_BASE_URL")
                ),
                organization=self._stored_organization,
                project=self._stored_project,
                http_client=shared_http_client(),
            )

        return self._client

    def _get_running_loop(self) -> asyncio.AbstractEventLoop | None:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    async def _close_ws_models_for_loop(
        self,
        loop: asyncio.AbstractEventLoop,
        models: list[Model],
        current_loop: asyncio.AbstractEventLoop,
    ) -> None:
        if not models:
            return
        if loop is current_loop:
            await self._close_models(models)
            return
        if loop.is_running():
            for model in models:
                future = asyncio.run_coroutine_threadsafe(model.close(), loop)
                await asyncio.wrap_future(future)
            return
        # Do not run an inactive foreign loop on another thread. This also covers closed loops.
        # Close from the current loop and rely on model-specific cross-loop cleanup fallbacks.
        await self._close_models(models)

    async def _close_models(self, models: list[Model]) -> None:
        for model in models:
            await model.close()

    def _clear_ws_loop_cache_entry(
        self, loop: asyncio.AbstractEventLoop, loop_cache: _WSLoopModelCache
    ) -> None:
        loop_cache.clear()
        try:
            del self._ws_model_cache_by_loop[loop]
        except KeyError:
            pass

    def _collect_unique_cached_models(
        self, loop_cache: _WSLoopModelCache, seen: set[int]
    ) -> list[Model]:
        models_to_close: list[Model] = []
        for model in list(loop_cache.values()):
            model_id = id(model)
            if model_id in seen:
                continue
            seen.add(model_id)
            models_to_close.append(model)
        return models_to_close

    def _prune_closed_ws_loop_caches(self) -> None:
        """Drop websocket model cache entries for loops that are already closed."""
        for loop, loop_cache in list(self._ws_model_cache_by_loop.items()):
            if not loop.is_closed():
                continue

            for model in list(loop_cache.values()):
                if isinstance(model, OpenAIResponsesWSModel):
                    model._force_drop_websocket_connection_sync()

            self._clear_ws_loop_cache_entry(loop, loop_cache)

    def get_model(self, model_name: str | None) -> Model:
        """Resolve a string model name into a concrete OpenAI-backed Model implementation."""
        # 这是 ModelProvider 最核心的方法。
        # 调用链通常是：
        # Agent.model / RunConfig.model 是字符串。
        # -> turn_preparation.get_model(...)。
        # -> run_config.model_provider.get_model(model_name)。
        # -> 这里根据配置返回具体 Model。
        #
        # 如果你在业务代码中直接传入一个自定义 Model 实例，这个方法不会被调用。
        # 如果你只传字符串模型名，就必须通过 provider 解析。
        model_is_explicit = model_name is not None
        resolved_model_name = model_name if model_name is not None else get_default_model()
        cache_key: _WSModelCacheKey = (
            resolved_model_name,
            model_is_explicit,
        )
        running_loop: asyncio.AbstractEventLoop | None = None
        loop_cache: _WSLoopModelCache | None = None

        use_websocket_transport = self._responses_transport == "websocket"
        if self._use_responses and use_websocket_transport:
            # WebSocket transport 更像一条长连接。这里按事件循环缓存 model wrapper，
            # 让多次 run 可以复用连接，同时避免跨 event loop 错用连接。
            self._prune_closed_ws_loop_caches()
            running_loop = self._get_running_loop()
            loop_cache = (
                self._ws_model_cache_by_loop.setdefault(running_loop, {})
                if running_loop is not None
                else None
            )
            if loop_cache is not None and (cached_model := loop_cache.get(cache_key)):
                return cached_model
        client = self._get_client()
        model: Model

        if not self._use_responses:
            # 兼容路径：把 SDK 内部统一输入转换成 Chat Completions messages。
            # 新项目优先学习 Responses 路径，Chat Completions 主要用于老接口或兼容网关。
            return OpenAIChatCompletionsModel(
                model=resolved_model_name,
                openai_client=client,
                strict_feature_validation=self._strict_feature_validation,
            )

        if use_websocket_transport:
            # Responses WebSocket 仍然是文本/工具 Agent loop，不等同于 Realtime/语音会话。
            # 它适合多轮 Responses 调用频繁、希望复用 socket 的场景。
            model = OpenAIResponsesWSModel(
                model=resolved_model_name,
                openai_client=client,
                model_is_explicit=model_is_explicit,
                websocket_options=self._responses_websocket_options,
            )
            if loop_cache is not None:
                loop_cache[cache_key] = model
            return model

        # 默认主路径：HTTP Responses API。
        # 对大多数 Agent 项目来说，这是最先理解和最推荐落地的模型适配器。
        model = OpenAIResponsesModel(
            model=resolved_model_name,
            openai_client=client,
            model_is_explicit=model_is_explicit,
        )
        return model

    async def aclose(self) -> None:
        """Close any cached model resources held by this provider.

        This primarily releases persistent websocket connections opened by
        ``OpenAIResponsesWSModel`` instances. It intentionally does not close the
        underlying ``AsyncOpenAI`` client because the SDK may be sharing the HTTP client
        across providers/process-wide.
        """
        seen: set[int] = set()
        current_loop = self._get_running_loop()
        if current_loop is None:
            return
        for loop, loop_cache in list(self._ws_model_cache_by_loop.items()):
            models_to_close = self._collect_unique_cached_models(loop_cache, seen)
            await self._close_ws_models_for_loop(loop, models_to_close, current_loop)
            self._clear_ws_loop_cache_entry(loop, loop_cache)
