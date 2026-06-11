"""中文学习提示：sandbox memory 的结构化输出协议。

Phase one 调模型抽取记忆时，会要求模型按这里的 JSON Schema 返回 rollout_slug、
rollout_summary 和 raw_memory。核心思想是：让模型生成记忆也要有明确 schema，
不能只靠自由文本。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RolloutExtractionArtifacts(BaseModel):
    """Phase one 从单次 rollout 中抽出的三类记忆材料。"""

    rollout_slug: str
    rollout_summary: str
    raw_memory: str


ROLLOUT_EXTRACTION_ARTIFACTS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rollout_slug": {"type": "string"},
        "rollout_summary": {"type": "string"},
        "raw_memory": {"type": "string"},
    },
    "required": ["rollout_slug", "rollout_summary", "raw_memory"],
}

ROLLOUT_EXTRACTION_ARTIFACTS_TEXT_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "name": "sandbox_memory_rollout_extraction_artifacts",
    "description": "Sandbox memory rollout extraction artifacts.",
    "schema": ROLLOUT_EXTRACTION_ARTIFACTS_JSON_SCHEMA,
    "strict": True,
}

ROLLOUT_EXTRACTION_ARTIFACTS_TEXT_CONFIG: dict[str, Any] = {
    "format": ROLLOUT_EXTRACTION_ARTIFACTS_TEXT_FORMAT
}
