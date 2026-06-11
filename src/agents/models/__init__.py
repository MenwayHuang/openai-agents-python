"""中文学习提示：模型默认配置相关导出口。

这里集中导出默认模型、默认 model_settings、GPT-5 推理设置判断和 OpenAI Agent 注册配置。
学习模型选择逻辑时继续看 `default_models.py`。
"""

from .default_models import (
    get_default_model,
    get_default_model_settings,
    gpt_5_reasoning_settings_required,
    is_gpt_5_default,
)
from .openai_agent_registration import OpenAIAgentRegistrationConfig

__all__ = [
    "get_default_model",
    "get_default_model_settings",
    "gpt_5_reasoning_settings_required",
    "is_gpt_5_default",
    "OpenAIAgentRegistrationConfig",
]
