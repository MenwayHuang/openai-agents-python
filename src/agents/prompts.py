"""Reusable Prompt 配置工具。

中文学习说明：
- OpenAI Responses API 支持通过 prompt id/version/variables 引用托管 prompt。
- `Prompt` 是静态配置；`DynamicPromptFunction` 可以根据 run context 和 agent 动态生成 prompt。
- 对 PPT Agent 来说，早期可以先把 prompt 放代码里；后续商业化可逐步迁移到可版本化的 prompt 配置。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from openai.types.responses.response_prompt_param import (
    ResponsePromptParam,
    Variables as ResponsesPromptVariables,
)
from typing_extensions import NotRequired, TypedDict

from agents.util._types import MaybeAwaitable

from .exceptions import UserError
from .run_context import RunContextWrapper

if TYPE_CHECKING:
    from .agent import Agent


class Prompt(TypedDict):
    """Prompt configuration to use for interacting with an OpenAI model."""

    id: str
    """The unique ID of the prompt."""

    version: NotRequired[str]
    """Optional version of the prompt."""

    variables: NotRequired[dict[str, ResponsesPromptVariables]]
    """Optional variables to substitute into the prompt."""


@dataclass
class GenerateDynamicPromptData:
    """Inputs to a function that allows you to dynamically generate a prompt."""

    context: RunContextWrapper[Any]
    """The run context."""

    agent: Agent[Any]
    """The agent for which the prompt is being generated."""


DynamicPromptFunction = Callable[[GenerateDynamicPromptData], MaybeAwaitable[Prompt]]
"""A function that dynamically generates a prompt."""


def _coerce_prompt_dict(prompt: Prompt | dict[object, object]) -> Prompt:
    """Convert a runtime-validated prompt dict into the Prompt TypedDict view."""
    return cast(Prompt, prompt)


class PromptUtil:
    @staticmethod
    async def to_model_input(
        prompt: Prompt | DynamicPromptFunction | None,
        context: RunContextWrapper[Any],
        agent: Agent[Any],
    ) -> ResponsePromptParam | None:
        # 支持 prompt=None、静态 dict、同步/异步动态函数三种输入，最终统一成 Responses API prompt 参数。
        if prompt is None:
            return None

        resolved_prompt: Prompt
        if isinstance(prompt, dict):
            resolved_prompt = _coerce_prompt_dict(prompt)
        else:
            func_result = prompt(GenerateDynamicPromptData(context=context, agent=agent))
            if inspect.isawaitable(func_result):
                resolved_prompt = await func_result
            else:
                resolved_prompt = func_result
            if not isinstance(resolved_prompt, dict):
                raise UserError("Dynamic prompt function must return a Prompt")

        return {
            "id": resolved_prompt["id"],
            "version": resolved_prompt.get("version"),
            "variables": resolved_prompt.get("variables"),
        }
