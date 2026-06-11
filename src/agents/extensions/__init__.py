"""Agents 扩展包入口。

学习提示：这里导出非核心但常用的扩展能力。当前只有 ToolOutputTrimmer，
其它扩展分散在 experimental、memory、models、sandbox 等子包中。
"""

from .tool_output_trimmer import ToolOutputTrimmer

__all__ = ["ToolOutputTrimmer"]
