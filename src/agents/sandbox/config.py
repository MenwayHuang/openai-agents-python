from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from openai.types.shared import Reasoning

from ..model_settings import ModelSettings
from ..models.interface import Model

DEFAULT_PYTHON_SANDBOX_IMAGE: Final = "python:3.14-slim"

# 学习提示：sandbox 配置集中在这里，包括默认镜像和 memory 生成配置。
# 这些配置偏 SDK 内部能力，当前 PPT Agent 只需理解“运行环境配置”和“记忆生成配置”分离即可。


def _default_memory_phase_one_model_settings() -> ModelSettings:
    return ModelSettings(reasoning=Reasoning(effort="medium"))


def _default_memory_phase_two_model_settings() -> ModelSettings:
    return ModelSettings(reasoning=Reasoning(effort="medium"))


@dataclass
class MemoryLayoutConfig:
    """Filesystem layout for sandbox-backed memory generation."""

    memories_dir: str = "memories"
    """Directory used for consolidated memory files."""

    sessions_dir: str = "sessions"
    """Directory used for per-rollout JSONL artifacts."""


@dataclass
class MemoryGenerateConfig:
    """Configuration for sandbox-backed memory extraction and consolidation.

    Run segments are appended during the sandbox session. Extraction and consolidation run when
    the sandbox session closes.
    """

    max_raw_memories_for_consolidation: int = 256
    """Maximum number of recent raw memories considered during consolidation."""

    phase_one_model: str | Model = "gpt-5.4-mini"
    """Model used for phase-1 single-rollout extraction."""

    phase_one_model_settings: ModelSettings | None = field(
        default_factory=_default_memory_phase_one_model_settings
    )
    """Model settings used for phase-1 single-rollout extraction."""

    phase_two_model: str | Model = "gpt-5.5"
    """Model used for phase-2 memory consolidation."""

    phase_two_model_settings: ModelSettings | None = field(
        default_factory=_default_memory_phase_two_model_settings
    )
    """Model settings used for phase-2 memory consolidation."""

    extra_prompt: str | None = None
    """Optional developer-specific guidance appended to memory extraction and consolidation
    prompts.

    Use this to tell memory what extra details are important to preserve for future runs, in
    addition to the standard user preferences, failure recovery, and task summary signals.
    Prefer a few targeted bullet points or short paragraphs, not pages of extra instructions.
    Try to keep it under about 5k tokens, and usually much shorter.
    The phase-one memory generator already receives a large built-in prompt plus a truncated
    conversation in a single model context window, so oversized extra prompts can crowd out the
    evidence you actually want it to summarize.
    """

    def __post_init__(self) -> None:
        # __post_init__ 做配置边界校验，避免运行到后面才发现阈值不合理。
        if self.max_raw_memories_for_consolidation <= 0:
            raise ValueError(
                "MemoryGenerateConfig.max_raw_memories_for_consolidation must be greater than 0."
            )
        if self.max_raw_memories_for_consolidation > 4096:
            raise ValueError(
                "MemoryGenerateConfig.max_raw_memories_for_consolidation "
                "must be less than or equal to 4096."
            )


@dataclass
class MemoryReadConfig:
    """Configuration for sandbox-backed memory reads."""

    live_update: bool = True
    """Whether the agent may update stale memory files in place during a run."""
