# Python 导入包中文学习说明

这份说明面向 Python 新手，帮助你读 `openai-agents-python` 源码时先知道每类包大概做什么。
源码里看到 `import xxx` 或 `from xxx import yyy` 时，可以先来这里对照。

## 先理解 import

- `import asyncio`：导入整个模块，使用时写 `asyncio.create_task(...)`。
- `from dataclasses import dataclass`：只导入模块里的某个对象，使用时直接写 `@dataclass`。
- `from .tool import FunctionTool`：`.` 代表当前包内的相对导入，这是项目自己的模块。
- `from ..errors import UserError`：`..` 代表上一级包，也是项目内部模块。
- `if TYPE_CHECKING:` 里面的导入只给类型检查器和 IDE 看，运行时不会真正导入，常用于避免循环导入。
- `from __future__ import annotations` 是 Python 官方特性，让类型注解延迟解析，减少循环引用和运行时开销。

## 重要使用方法速查

这一节不是完整 API 文档，而是面向新手的“常用写法地图”。你后续做 PPT Agent 时，可以先按这些模式把功能跑通，再回头深入读源码。

### 1. 最小 Agent 怎么写

`Agent` 可以先理解成“一个智能体的配置对象”，里面放名称、提示词、模型、工具和输出格式。`Runner.run(...)` 是真正开始执行的入口，返回值里的 `final_output` 是最终答案。

```python
import asyncio

from agents import Agent, Runner


agent = Agent(
    name="中文助手",
    instructions="用中文简洁回答用户问题。",
)


async def main() -> None:
    result = await Runner.run(agent, "你好，请介绍一下你自己")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
```

你需要记住三件事：

- `Agent(...)` 只是定义，不会立刻调用模型。
- `await Runner.run(...)` 才会真正调用模型、工具和任务转移。
- `result.final_output` 通常是你要返回给前端或继续处理的数据。

### 2. 异步和同步运行怎么选

`Runner.run(...)` 是异步方法，适合 FastAPI、WebSocket、后台任务和需要并发的服务。`Runner.run_sync(...)` 是同步方法，适合命令行脚本、一次性测试和最小 demo。

```python
from agents import Agent, Runner


agent = Agent(name="脚本助手", instructions="回答要短。")

result = Runner.run_sync(agent, "用一句话解释什么是 Agent")
print(result.final_output)
```

常见坑：

- 在 `async def` 里面用 `await Runner.run(...)`。
- 在普通脚本里面可以用 `Runner.run_sync(...)`。
- 在已经运行事件循环的环境里，不要再套一层 `asyncio.run(...)`，否则可能报 event loop 相关错误。

### 3. 普通 Python 函数怎么变成工具

`@function_tool` 是最常用的工具写法。它会读取函数名、参数类型、返回值和 docstring，然后把这个函数包装成模型可以调用的工具。

```python
from agents import Agent, Runner, function_tool


@function_tool
def get_template_summary(template_id: str) -> str:
    """根据模板 ID 返回 PPT 模板摘要。"""
    return f"模板 {template_id} 适合科技产品发布会。"


agent = Agent(
    name="PPT 策划助手",
    instructions="根据用户需求选择合适的 PPT 模板。",
    tools=[get_template_summary],
)

result = Runner.run_sync(agent, "帮我找一个适合 AI 创业路演的模板")
print(result.final_output)
```

写工具时建议：

- 参数尽量写类型注解，例如 `template_id: str`、`limit: int`。
- docstring 写清楚工具做什么，模型会参考这些说明决定何时调用。
- 工具内部可以查数据库、读模板、调你自己的 API，但不要把密钥写死在函数里。

### 4. 结构化输出怎么用

如果你希望模型稳定返回 JSON 结构，不要只靠提示词要求“请输出 JSON”。更推荐用 Pydantic 定义输出类型，再传给 `Agent(output_type=...)`。

```python
from pydantic import BaseModel, Field

from agents import Agent, Runner


class SlideOutline(BaseModel):
    title: str = Field(description="整页幻灯片标题")
    bullets: list[str] = Field(description="这一页的要点列表")


class PPTOutline(BaseModel):
    topic: str
    slides: list[SlideOutline]


agent = Agent(
    name="PPT 大纲生成器",
    instructions="把用户需求拆成适合套版的 PPT 大纲。",
    output_type=PPTOutline,
)

result = Runner.run_sync(agent, "生成一个 5 页的 AI 教育产品路演大纲")
outline = result.final_output
print(outline.topic)
print(outline.slides[0].title)
```

对 PPT 项目来说，结构化输出特别适合：

- 生成页面大纲、章节、标题、要点。
- 生成模板槽位映射，例如哪个文案填到哪个 placeholder。
- 做质量检查结果，例如是否缺标题、是否文字过长、是否模板不匹配。

### 5. 多轮对话怎么延续

最简单的方式是把上一次结果转换成下一次输入列表：

```python
from agents import Agent, Runner


agent = Agent(name="助手", instructions="记住上下文。")

first = Runner.run_sync(agent, "我的项目叫 PPT AI Assistant")
second = Runner.run_sync(
    agent,
    first.to_input_list() + [{"role": "user", "content": "我刚才说项目叫什么？"}],
)

print(second.final_output)
```

这种方式适合你想完全手动控制历史记录。缺点是你要自己保存和裁剪历史。

### 6. 用 Session 保存会话

`SQLiteSession` 会帮你把多轮对话存在本地 SQLite 里。新手阶段可以先用它，后续生产系统再换 Redis、PostgreSQL、MongoDB 或你自己的 Session 实现。

```python
from agents import Agent, Runner, SQLiteSession


agent = Agent(name="PPT 助手", instructions="持续帮助用户完善 PPT。")
session = SQLiteSession("user_123_project_456")

first = Runner.run_sync(agent, "我想做一个 AI 教育产品路演 PPT", session=session)
print(first.final_output)

second = Runner.run_sync(agent, "继续帮我细化第 2 页", session=session)
print(second.final_output)
```

设计 PPT 项目时，可以把 session id 和用户、项目绑定起来，例如 `user_id + project_id`。这样用户多次打开同一个项目时，Agent 能继续理解上下文。

### 7. 流式输出怎么接前端

前端聊天窗口通常希望边生成边显示，这时用 `Runner.run_streamed(...)`。它会返回一个流式结果，你需要持续消费 `stream_events()`。

```python
import asyncio

from openai.types.responses import ResponseTextDeltaEvent

from agents import Agent, Runner


agent = Agent(name="流式助手", instructions="输出适合实时展示。")


async def main() -> None:
    result = Runner.run_streamed(agent, "写一个 3 页 PPT 大纲")

    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            print(event.data.delta, end="", flush=True)


asyncio.run(main())
```

在 Web 服务里，你通常会把这些事件转换成 SSE 或 WebSocket 消息发给前端。注意必须把 `stream_events()` 消费完，一次流式运行才算真正结束。

### 8. ModelSettings 常用来调什么

`ModelSettings` 是模型调用参数。你可以在 `Agent` 上设置，也可以在 `RunConfig` 里覆盖单次运行。

```python
from agents import Agent, ModelSettings


agent = Agent(
    name="PPT 文案助手",
    instructions="生成正式、清晰、适合商业路演的文案。",
    model_settings=ModelSettings(
        temperature=0.3,
        max_tokens=1200,
        tool_choice="auto",
    ),
)
```

经验建议：

- 创意发散、标题脑暴可以适当提高 `temperature`。
- 结构化输出、质量检查、模板映射应降低 `temperature`。
- 希望强制模型调用某个工具时，再研究 `tool_choice`。
- 不同模型对参数支持程度不同，生产前要用目标模型真实验证。

### 9. Trace 怎么用于排查问题

Trace 可以记录一次 Agent 运行里的模型调用、工具调用、任务转移和错误。开发 PPT Agent 时，建议给关键流程加上明确的工作流名和项目 ID。

```python
from agents import Agent, Runner, trace


agent = Agent(name="PPT 生成器", instructions="生成 PPT 大纲。")
project_id = "project_456"

with trace("PPT 生成流程", group_id=project_id):
    result = Runner.run_sync(agent, "生成一个 AI 产品发布会大纲")
    print(result.final_output)
```

你可以用 trace 回答这些问题：

- 模型为什么没有调用某个工具？
- 哪个工具参数错了？
- 多智能体之间是否发生了任务转移？
- 某次 PPT 生成为什么慢或失败？

生产环境要注意敏感信息，必要时通过 `RunConfig.trace_include_sensitive_data=False` 或环境变量减少 trace 中记录的输入输出内容。

### 10. MCP 怎么接外部工具

MCP 可以理解成“给模型接工具的一套标准协议”。如果你已有文件系统、浏览器、数据库、企业系统等 MCP 服务，可以通过 `mcp_servers` 暴露给 Agent。

```python
import asyncio

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


async def main() -> None:
    async with MCPServerStdio(
        name="本地文件系统 MCP",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "./sample_files"],
        },
    ) as server:
        agent = Agent(
            name="文件阅读助手",
            instructions="使用 MCP 工具读取文件后回答。",
            mcp_servers=[server],
        )
        result = await Runner.run(agent, "列出可以读取的文件")
        print(result.final_output)


asyncio.run(main())
```

接 MCP 时要特别关注边界：

- 只暴露必要工具，不要把危险操作默认给模型。
- 文件系统、数据库、支付、部署等工具要有审批、白名单、超时和审计。
- 本地 demo 可以先跑通 stdio MCP，生产环境再考虑 Streamable HTTP、鉴权和网络隔离。

### 11. 沙箱 Agent 什么时候需要

普通 `Agent` 适合聊天、结构化输出、工具调用和业务编排。`SandboxAgent` 适合需要隔离文件系统、执行命令、修改文件、生成工件的任务。

对 PPT 项目来说，可以先不急着上沙箱。先把下面链路跑通更重要：

1. 用户需求转结构化 PPT 大纲。
2. 后端工具读取模板信息。
3. Agent 输出模板槽位映射。
4. 后端服务把内容填充进模板。
5. 质量检查工具检查标题、页数、字数和图片缺失。

等你需要让 Agent 自己分析一堆文件、调用命令、批量修改项目文件或生成复杂工件时，再深入 `agents.sandbox`。

### 12. 常见错误和排查顺序

新手最容易遇到这些问题：

- `OPENAI_API_KEY` 没设置：先在终端设置环境变量，不要写死到源码。
- 没装 optional 依赖：例如 MCP、Redis、数据库、沙箱 provider 需要额外安装对应 extra 或包。
- 在异步函数里用了 `Runner.run_sync(...)`：优先改成 `await Runner.run(...)`。
- 工具函数缺类型注解：补上参数类型和返回类型，schema 会更稳定。
- 结构化输出失败：先简化 Pydantic 模型，字段描述写清楚，再逐步加复杂字段。
- Agent 没有调用工具：检查工具 docstring、`instructions` 是否明确，以及 `tool_choice` 是否需要调整。
- 流式接口没有结束：确认完整消费了 `result.stream_events()`。

建议你调试时按这个顺序看：

1. 先看报错堆栈最底部是哪一行。
2. 再看是否是环境变量、依赖或网络问题。
3. 再打开 trace 看模型输入、工具调用和工具返回。
4. 最后再读 `src/agents/run.py`、`src/agents/tool.py`、`src/agents/models/` 里的内部实现。

### 13. 做 PPT Agent 的推荐组合

如果你要从这个 SDK 出发实现生产级 PPT Agent，可以把能力拆成下面几个层次：

| 层次 | SDK 写法 | 在 PPT 项目里的作用 |
| --- | --- | --- |
| 对话入口 | `Agent` + `Runner.run` / `Runner.run_streamed` | 接收用户需求，返回计划或生成进度。 |
| 业务工具 | `@function_tool` | 查询模板、读取项目、保存大纲、触发套版。 |
| 结构化结果 | `output_type=BaseModel` | 生成可校验的大纲、槽位映射、质检报告。 |
| 多轮记忆 | `SQLiteSession` / 其他 Session | 保存用户在同一个 PPT 项目中的持续上下文。 |
| 可观测性 | `trace(...)` / `RunConfig` | 排查模型调用、工具调用、失败原因和耗时。 |
| 外部能力 | MCP / 沙箱 | 接文件、浏览器、命令执行、复杂工件处理。 |

一个成熟的 PPT Agent 不应该只靠一个超长 prompt。更稳的方式是：Agent 负责理解、规划和决策；后端工具负责模板解析、文件生成、存储和可验证的确定性操作。

## Python 官方标准库

这些包随 Python 自带，不需要额外安装。

| 包 | 作用 | 源码里常见用途 |
| --- | --- | --- |
| `abc` | 定义抽象基类和抽象方法 | 规定 Model、Tool、Session 等接口必须实现哪些方法。 |
| `asyncio` | Python 异步编程核心库 | 并发调用模型、工具、MCP、沙箱命令和流式输出。 |
| `contextlib` | 上下文管理工具 | 管理 `async with`、资源清理、临时上下文。 |
| `contextvars` | 异步上下文变量 | 在异步调用链中保存当前 trace、run context 等状态。 |
| `dataclasses` | 快速定义数据类 | 保存轻量配置、运行状态、工具结果。 |
| `datetime` | 时间日期处理 | 记录事件时间、memory rollout 更新时间。 |
| `enum` | 枚举类型 | 表示固定选项，例如重试策略、状态类型。 |
| `functools` | 函数工具 | 缓存 prompt 模板、包装装饰器。 |
| `inspect` | 运行时检查函数签名和类型 | 从 Python 函数自动推断工具 schema。 |
| `io` | 文件流抽象 | 在沙箱读写文件、归档、图片时处理 bytes stream。 |
| `json` | JSON 编解码 | 解析工具参数、模型结构化输出、trace 和 memory 文件。 |
| `logging` | 日志 | 输出 SDK 内部调试和错误日志。 |
| `pathlib` | 面向对象路径处理 | 比字符串拼路径更安全，常用于 workspace 文件路径。 |
| `re` | 正则表达式 | 校验 ID、slug、解析文本。 |
| `shlex` | shell 参数转义 | 构造命令时避免空格和特殊字符破坏命令。 |
| `tarfile` / `zipfile` | 压缩包处理 | 沙箱 workspace 快照、上传归档和安全解压。 |
| `tempfile` | 临时文件和临时目录 | 中转归档、沙箱本地 workspace。 |
| `threading` / `concurrent.futures` | 线程和线程池 | Docker 后端、阻塞 I/O 和后台读取输出。 |
| `typing` / `collections.abc` | 类型注解 | 让复杂 Agent、Tool、Model 接口更容易被 IDE 和 mypy 检查。 |
| `uuid` | 生成唯一 ID | session、trace、事件、rollout 文件名。 |
| `weakref` | 弱引用 | 缓存运行时对象但不阻止对象被释放。 |

## OpenAI 官方包

| 包 | 作用 | 源码里常见用途 |
| --- | --- | --- |
| `openai` | OpenAI Python SDK | 创建 `AsyncOpenAI` client，调用 Responses、Chat Completions、Realtime 等 API。 |
| `openai.types.responses` | OpenAI SDK 自动生成的 Responses API 类型 | 表示消息、工具调用、reasoning、stream event、web search 等结构。 |
| `openai.types.shared` | OpenAI SDK 共享类型 | 例如 `Reasoning`，用于配置推理模型参数。 |
| `openai._types` | OpenAI SDK 内部类型 | 例如 `Body`、`Query`，用于传递额外请求体或 query 参数。 |

阅读建议：业务层先看 `src/agents/models/openai_responses.py` 和 `src/agents/models/openai_chatcompletions.py`，它们展示 Agents SDK 如何把内部 Agent 输入转换成 OpenAI API 请求。

## Pydantic 相关包

| 包 | 作用 | 源码里常见用途 |
| --- | --- | --- |
| `pydantic` | 数据校验和类型模型库 | 定义 `BaseModel`、校验工具参数、生成 JSON Schema。 |
| `pydantic.dataclasses` | Pydantic 版 dataclass | 让 dataclass 同时具备参数校验能力。 |
| `pydantic_core` | Pydantic 底层核心 | 自定义类型校验 schema 时使用。 |

阅读建议：如果你看到 `BaseModel`，可以理解成“带类型校验的数据类”；如果看到 `TypeAdapter`，可以理解成“把某个类型单独拿出来做校验或 JSON schema 生成”。

## 类型兼容包

| 包 | 作用 | 源码里常见用途 |
| --- | --- | --- |
| `typing_extensions` | 给旧 Python 版本补新类型特性 | `TypedDict`、`NotRequired`、`TypeVar`、`Self`、`Unpack` 等。 |
| `exceptiongroup` | 给旧 Python 补异常组类型 | MCP/anyio 里可能同时聚合多个异步异常。 |

## HTTP、异步和协议包

| 包 | 作用 | 源码里常见用途 |
| --- | --- | --- |
| `httpx` | 现代 HTTP 客户端 | MCP Streamable HTTP、SSE 等网络请求。 |
| `requests` | 经典同步 HTTP 客户端 | 部分同步工具或兼容代码。 |
| `aiohttp` | 异步 HTTP 客户端/服务端库 | Blaxel、Cloudflare 等 sandbox provider 的异步 HTTP 通信。 |
| `anyio` | 同时兼容 asyncio/trio 的异步抽象层 | MCP client 内部使用。 |
| `websockets` | WebSocket 通信 | Realtime、Responses WebSocket、语音或实时事件流。 |
| `mcp` | Model Context Protocol 官方 Python SDK | 连接 MCP server，列工具、调用工具、处理 approval。 |

## 数据库、缓存和服务集成

这些是可选依赖，只有安装对应 extra 或运行对应功能时才需要。

| 包 | 作用 | 源码里常见用途 |
| --- | --- | --- |
| `aiosqlite` | SQLite 的异步封装 | 异步 session 存储。 |
| `sqlite3` | Python 自带 SQLite | 本地轻量会话存储。 |
| `sqlalchemy` | ORM/数据库抽象 | SQLAlchemy session 扩展。 |
| `asyncpg` | PostgreSQL 异步驱动 | SQLAlchemy 异步 PostgreSQL 场景。 |
| `redis` | Redis 客户端 | Redis session 或缓存扩展。 |
| `pymongo` | MongoDB 客户端 | MongoDB session 扩展。 |
| `dapr` / `grpcio` | Dapr 和 gRPC 集成 | 分布式服务、状态存储或 sidecar 通信。 |
| `cryptography` | 加密库 | 加密 session 或密钥相关扩展。 |

## 沙箱和云执行 provider

| 包 | 作用 | 源码里常见用途 |
| --- | --- | --- |
| `docker` | Docker Python SDK | 创建容器、执行命令、复制文件、管理 volume。 |
| `blaxel` | Blaxel 沙箱平台 SDK | 创建/连接 Blaxel sandbox。 |
| `daytona` | Daytona 沙箱平台 SDK | 创建/连接 Daytona sandbox。 |
| `e2b` / `e2b-code-interpreter` | E2B 沙箱和代码解释器 SDK | 远端代码执行沙箱。 |
| `modal` | Modal 云运行平台 SDK | Modal sandbox/provider。 |
| `runloop_api_client` | Runloop 平台客户端 | Runloop sandbox/provider。 |
| `vercel` | Vercel sandbox 相关 SDK | Vercel sandbox/provider。 |
| `boto3` | AWS Python SDK | S3 或 AWS 资源访问。 |

阅读建议：先读 `src/agents/sandbox/session/base_sandbox_session.py` 理解抽象，再读 `src/agents/sandbox/sandboxes/docker.py` 理解一个具体后端，最后再看 `extensions/sandbox/*` 的平台适配。

## 文档、示例和开发工具包

| 包 | 作用 | 源码里常见用途 |
| --- | --- | --- |
| `griffe` / `griffelib` | 解析 Python docstring 和签名 | 从函数注释生成工具 schema。 |
| `graphviz` | 画图工具 | 可视化 Agent 流程或图结构。 |
| `rich` | 终端美化输出 | 示例里的进度、彩色日志、spinner。 |
| `fastapi` | Web API 框架 | Realtime/Twilio 示例服务。 |
| `pytest` / `pytest-asyncio` | 测试框架 | 运行同步/异步测试。 |
| `mypy` / `pyright` | 静态类型检查 | 检查类型注解是否正确。 |
| `ruff` | Python lint/format 工具 | 检查 import 顺序、代码风格、潜在问题。 |

## 项目内部包怎么读

| 内部模块 | 作用 |
| --- | --- |
| `agents.agent` | Agent 配置模型，描述提示词、工具、handoff、guardrail。 |
| `agents.run` | 公开运行入口，`Runner.run` 从这里进入。 |
| `agents.run_internal` | 运行时内部细节，业务代码不要直接依赖。 |
| `agents.tool` | 工具系统，把 Python 函数、内置工具、MCP 工具包装成模型可调用对象。 |
| `agents.models` | 不同模型后端适配，例如 Responses API 和 Chat Completions。 |
| `agents.mcp` | MCP server 连接和工具桥接。 |
| `agents.tracing` | trace/span 观测能力。 |
| `agents.memory` | 会话历史和压缩记忆。 |
| `agents.sandbox` | 沙箱运行、文件、命令、快照和 provider。 |

## 新手阅读顺序

1. 先读 `src/agents/__init__.py`，知道公开 API 从哪里导出。
2. 再读 `src/agents/agent.py`，理解 Agent 是怎么被定义的。
3. 再读 `src/agents/run.py`，理解 Runner 怎么启动执行。
4. 再读 `src/agents/tool.py`，理解 Python 函数怎么变成模型工具。
5. 再读 `src/agents/models/openai_responses.py`，理解最终怎么调用 OpenAI API。
6. 如果你要做复杂工具或外部系统集成，再读 `mcp/`、`tracing/`、`memory/`、`sandbox/`。
