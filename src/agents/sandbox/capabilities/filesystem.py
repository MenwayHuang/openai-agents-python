"""中文学习提示：文件系统能力。

这个 capability 把 `view_image` 和 `apply_patch` 两类工具交给模型。它不是直接操作
宿主机路径，而是通过绑定的 SandboxSession 执行读写，因此后续设计 PPT Agent 的
文件读写能力时，应学习这种“工具 -> session -> 受控工作区”的边界。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from ...tool import Tool
from .capability import Capability
from .tools import SandboxApplyPatchTool, ViewImageTool


@dataclass
class FilesystemToolSet:
    """Mutable bundle of tools exposed by the filesystem capability."""

    view_image: ViewImageTool
    apply_patch: SandboxApplyPatchTool


FilesystemToolConfigurator = Callable[[FilesystemToolSet], None]


class Filesystem(Capability):
    """文件系统能力：创建并返回模型可调用的文件工具。"""

    type: Literal["filesystem"] = "filesystem"
    configure_tools: FilesystemToolConfigurator | None = Field(default=None, exclude=True)
    """Optional callback that can customize or replace bundled filesystem tools."""

    def tools(self) -> list[Tool]:
        """按当前 session 构造文件工具，并允许调用方通过回调定制工具。"""

        if self.session is None:
            raise ValueError("Filesystem capability is not bound to a SandboxSession")

        toolset = FilesystemToolSet(
            view_image=ViewImageTool(session=self.session, user=self.run_as),
            apply_patch=SandboxApplyPatchTool(session=self.session, user=self.run_as),
        )
        if self.configure_tools is not None:
            self.configure_tools(toolset)

        return [toolset.view_image, toolset.apply_patch]
