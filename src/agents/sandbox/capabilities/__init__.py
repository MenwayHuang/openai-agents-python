"""中文学习提示：sandbox capabilities 包的统一导出口。

Capability 可以理解成“给沙箱中的 agent 开启的一类能力”，例如读写文件、
执行命令、压缩上下文、读取长期记忆或加载技能。阅读时从 `Capabilities.default()`
开始，再分别看具体能力类如何返回可被模型调用的 Tool。
"""

from .capabilities import Capabilities
from .capability import Capability
from .compaction import (
    Compaction,
    CompactionModelInfo,
    CompactionPolicy,
    DynamicCompactionPolicy,
    StaticCompactionPolicy,
)
from .filesystem import Filesystem, FilesystemToolSet
from .memory import Memory
from .shell import Shell, ShellToolSet
from .skills import LazySkillSource, LocalDirLazySkillSource, Skill, SkillMetadata, Skills

__all__ = [
    "Capability",
    "Capabilities",
    "Compaction",
    "CompactionModelInfo",
    "CompactionPolicy",
    "DynamicCompactionPolicy",
    "FilesystemToolSet",
    "LazySkillSource",
    "LocalDirLazySkillSource",
    "Memory",
    "Shell",
    "ShellToolSet",
    "Skill",
    "SkillMetadata",
    "Skills",
    "StaticCompactionPolicy",
    "Filesystem",
]
