"""中文学习提示：sandbox 上下文压缩能力。

当对话、工具输出或文件内容太长时，Compaction 会根据模型上下文窗口和阈值生成
压缩策略参数。PPT Agent 以后做长任务时也会遇到类似问题：不能无限把历史都塞回
模型，而要有可解释的压缩阈值和保留策略。
"""

from __future__ import annotations

import abc
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from ...items import TResponseInputItem
from .capability import Capability

_DEFAULT_COMPACT_THRESHOLD = 240_000
_MODEL_NAME_SEPARATOR_TRANSLATION = str.maketrans("", "", ".-")


def _model_lookup_key(model: str) -> str:
    normalized_model = model.strip().lower().removeprefix("openai/")
    return normalized_model.translate(_MODEL_NAME_SEPARATOR_TRANSLATION)


def _model_context_windows(models: tuple[str, ...], context_window: int) -> dict[str, int]:
    return {_model_lookup_key(model): context_window for model in models}


_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # 中文说明：这里维护常见模型的上下文窗口估算值，用于动态计算压缩阈值。
    # 模型名称会先归一化，所以带供应商前缀、点号或日期的名字可以共用查找逻辑。
    **_model_context_windows(
        (
            "gpt-5.4",
            "gpt-5.4-2026-03-05",
            "gpt-5.4-pro",
            "gpt-5.4-pro-2026-03-05",
            "gpt-5.5",
            "gpt-5.5-2026-04-23",
            "gpt-5.5-pro",
            "gpt-5.5-pro-2026-04-23",
            "gpt-4.1",
            "gpt-4.1-2025-04-14",
            "gpt-4.1-mini",
            "gpt-4.1-mini-2025-04-14",
            "gpt-4.1-nano",
            "gpt-4.1-nano-2025-04-14",
        ),
        1_047_576,
    ),
    **_model_context_windows(
        (
            "gpt-5",
            "gpt-5-2025-08-07",
            "gpt-5-codex",
            "gpt-5-mini",
            "gpt-5-mini-2025-08-07",
            "gpt-5-nano",
            "gpt-5-nano-2025-08-07",
            "gpt-5-pro",
            "gpt-5-pro-2025-10-06",
            "gpt-5.1",
            "gpt-5.1-2025-11-13",
            "gpt-5.1-codex",
            "gpt-5.1-codex-max",
            "gpt-5.1-codex-mini",
            "gpt-5.2",
            "gpt-5.2-2025-12-11",
            "gpt-5.2-codex",
            "gpt-5.2-pro",
            "gpt-5.2-pro-2025-12-11",
            "gpt-5.3-codex",
            "gpt-5.4-mini",
            "gpt-5.4-mini-2026-03-17",
            "gpt-5.4-nano",
            "gpt-5.4-nano-2026-03-17",
        ),
        400_000,
    ),
    **_model_context_windows(
        (
            "codex-mini-latest",
            "o1",
            "o1-2024-12-17",
            "o1-pro",
            "o1-pro-2025-03-19",
            "o3",
            "o3-2025-04-16",
            "o3-deep-research",
            "o3-deep-research-2025-06-26",
            "o3-mini",
            "o3-mini-2025-01-31",
            "o3-pro",
            "o3-pro-2025-06-10",
            "o4-mini",
            "o4-mini-2025-04-16",
            "o4-mini-deep-research",
            "o4-mini-deep-research-2025-06-26",
        ),
        200_000,
    ),
    **_model_context_windows(
        (
            "gpt-4o",
            "gpt-4o-2024-05-13",
            "gpt-4o-2024-08-06",
            "gpt-4o-2024-11-20",
            "gpt-4o-mini",
            "gpt-4o-mini-2024-07-18",
            "gpt-5-chat-latest",
            "gpt-5.1-chat-latest",
            "gpt-5.2-chat-latest",
            "gpt-5.3-chat-latest",
        ),
        128_000,
    ),
}


class CompactionModelInfo(BaseModel):
    """模型上下文窗口信息。"""

    context_window: int

    @classmethod
    def maybe_for_model(cls, model: str) -> CompactionModelInfo | None:
        """根据模型名查上下文窗口；未知模型返回 None，让上层使用默认策略。"""

        context_window = _MODEL_CONTEXT_WINDOWS.get(_model_lookup_key(model))
        if context_window is None:
            return None
        return cls(context_window=context_window)

    @classmethod
    def for_model(cls, model: str) -> CompactionModelInfo:
        model_info = cls.maybe_for_model(model)
        if model_info is not None:
            return model_info
        raise ValueError(f"Unknown context window for model: {model!r}")


class CompactionPolicy(BaseModel, abc.ABC):
    """压缩策略基类：根据采样参数决定何时触发 compaction。"""

    type: str

    @abc.abstractmethod
    def compaction_threshold(self, sampling_params: dict[str, Any]) -> int: ...


class StaticCompactionPolicy(CompactionPolicy):
    """固定阈值策略：上下文超过指定 token 估算值后触发压缩。"""

    type: Literal["static"] = "static"
    threshold: int = Field(default=_DEFAULT_COMPACT_THRESHOLD)

    def compaction_threshold(self, sampling_params: dict[str, Any]) -> int:
        _ = sampling_params
        return self.threshold


class DynamicCompactionPolicy(CompactionPolicy):
    """动态阈值策略：按模型上下文窗口的一定比例触发压缩。"""

    type: Literal["dynamic"] = "dynamic"
    model_info: CompactionModelInfo
    threshold: float = Field(ge=0, le=1, default=0.9)

    def compaction_threshold(self, sampling_params: dict[str, Any]) -> int:
        _ = sampling_params
        return int(self.model_info.context_window * self.threshold)


class Compaction(Capability):
    """把上下文压缩能力挂到 sandbox run 中。"""

    type: Literal["compaction"] = "compaction"
    policy: CompactionPolicy | None = Field(default=None)

    @field_validator("policy", mode="before")
    @classmethod
    def _validate_policy(cls, value: object) -> object | None:
        if value is None:
            return None
        if isinstance(value, CompactionPolicy):
            return value
        if isinstance(value, Mapping):
            policy_type = value.get("type")
            if policy_type == "static":
                return StaticCompactionPolicy.model_validate(dict(value))
            if policy_type == "dynamic":
                return DynamicCompactionPolicy.model_validate(dict(value))
            raise ValueError(f"Unsupported compaction policy type: {policy_type!r}")
        return value

    @field_serializer("policy", when_used="always", return_type=dict[str, Any])
    def _serialize_policy(self, policy: CompactionPolicy | None) -> dict[str, Any] | None:
        if policy is None:
            return None
        return policy.model_dump()

    def sampling_params(self, sampling_params: dict[str, Any]) -> dict[str, Any]:
        """给模型请求补充 compact_threshold 等参数。"""

        policy = self.policy
        if policy is None:
            model = sampling_params.get("model")
            if isinstance(model, str) and model:
                model_info = CompactionModelInfo.maybe_for_model(model)
                if model_info is None:
                    policy = StaticCompactionPolicy()
                else:
                    policy = DynamicCompactionPolicy(model_info=model_info)
            else:
                policy = StaticCompactionPolicy()

        return {
            "context_management": [
                {
                    "type": "compaction",
                    "compact_threshold": policy.compaction_threshold(sampling_params),
                }
            ]
        }

    def process_context(self, context: list[TResponseInputItem]) -> list[TResponseInputItem]:
        """When a compaction item is received, truncate the context before it."""
        last_compaction_index: int | None = None
        for index in range(len(context) - 1, -1, -1):
            item = context[index]
            item_type = (
                item.get("type") if isinstance(item, Mapping) else getattr(item, "type", None)
            )
            if item_type == "compaction":
                last_compaction_index = index
                break

        if last_compaction_index is not None:
            return context[last_compaction_index:]

        return context
