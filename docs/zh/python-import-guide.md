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
