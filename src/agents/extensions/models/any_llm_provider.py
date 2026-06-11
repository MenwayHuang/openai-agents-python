from typing import Literal

# 中文导入说明：
# - 这个 Provider 本身不直接导入 any_llm；真正的第三方依赖在 AnyLLMModel 里动态导入。
# - get_default_model 来自项目内部默认模型配置，用来生成 `openai/<model>` 形式的默认模型名。

from ...models.default_models import get_default_model
from ...models.interface import Model, ModelProvider
from .any_llm_model import AnyLLMModel

DEFAULT_MODEL: str = f"openai/{get_default_model()}"

# 学习提示：Provider 负责按 model_name 返回具体 Model 实例。
# any-llm 通常从各 Provider 的环境变量读取 key，所以这里配置很薄。


class AnyLLMProvider(ModelProvider):
    """A ModelProvider that routes model calls through any-llm.

    API keys are typically sourced from the provider-specific environment variables expected by
    any-llm, such as `OPENAI_API_KEY` or `OPENROUTER_API_KEY`. For custom wiring or explicit
    credentials, instantiate `AnyLLMModel` directly.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        api: Literal["responses", "chat_completions"] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.api = api

    def get_model(self, model_name: str | None) -> Model:
        return AnyLLMModel(
            model=model_name or DEFAULT_MODEL,
            api_key=self.api_key,
            base_url=self.base_url,
            api=self.api,
        )
