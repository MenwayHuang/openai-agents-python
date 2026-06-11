"""中文学习提示：Shell 执行能力。

这个 capability 把 `exec_command` 和可选的 `write_stdin` 暴露给模型。它同时给模型
追加命令行使用规范，例如优先 rg、TTY 进程如何中断等。PPT Agent 以后如果允许
agent 调工具跑脚本，也需要类似的能力声明和安全边界。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from textwrap import dedent
from typing import Literal

from pydantic import Field

from ...tool import Tool
from ..manifest import Manifest
from .capability import Capability
from .tools import ExecCommandTool, WriteStdinTool

_SHELL_INSTRUCTIONS = dedent(
    """
    When using the shell:
    - Use `exec_command` for shell execution.
    - If available, use `write_stdin` to interact with or poll running sessions.
    - To interrupt a long-running process via `write_stdin`, start it with `tty=true` and send \
Ctrl-C (`\\u0003`).
    - Prefer `rg` and `rg --files` for text/file discovery when available.
    - Avoid using Python scripts just to print large file chunks.
    """
).strip()


@dataclass
class ShellToolSet:
    """Mutable bundle of tools exposed by the shell capability."""

    exec_command: ExecCommandTool
    write_stdin: WriteStdinTool | None


ShellToolConfigurator = Callable[[ShellToolSet], None]


class Shell(Capability):
    """Shell 能力：按 session 创建命令执行工具。"""

    type: Literal["shell"] = "shell"
    configure_tools: ShellToolConfigurator | None = Field(default=None, exclude=True)
    """Optional callback that can customize or replace bundled shell tools."""

    def tools(self) -> list[Tool]:
        """返回命令执行工具；只有支持 PTY 的 session 才暴露 write_stdin。"""

        if self.session is None:
            raise ValueError("Shell capability is not bound to a SandboxSession")
        toolset = ShellToolSet(
            exec_command=ExecCommandTool(session=self.session, user=self.run_as),
            write_stdin=WriteStdinTool(session=self.session)
            if self.session.supports_pty()
            else None,
        )
        if self.configure_tools is not None:
            self.configure_tools(toolset)
        tools: list[Tool] = [toolset.exec_command]
        if toolset.write_stdin is not None:
            tools.append(toolset.write_stdin)
        return tools

    async def instructions(self, manifest: Manifest) -> str | None:
        """给模型补充命令行工具的使用规则。"""

        _ = manifest
        return _SHELL_INSTRUCTIONS
