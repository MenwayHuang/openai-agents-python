# HMY OpenAI Agents Python 中文学习导读

> 本文档用于辅助中文阅读本仓库源码。它不改变 SDK 行为，只解释核心抽象、推荐阅读顺序和与自研 PPT Agent 项目的对应关系。

## 先回答：Model 和 ModelProvider 的区别

`Model` 是“已经选好的模型调用器”。它定义 `get_response()` 和 `stream_response()`，负责真正调用某个模型 API，并把 provider 原始响应转换成 SDK 内部统一的 `ModelResponse` 或流式事件。

`ModelProvider` 是“模型工厂和注册表”。它负责根据字符串模型名、默认模型、provider 前缀、base_url、API key、HTTP/WebSocket 传输配置和缓存策略，返回一个具体的 `Model` 实例。

所以不是所有场景都必须用 `ModelProvider`。如果你已经手动创建了一个 `Model` 实例，可以直接传给 `Agent(model=...)` 或 `RunConfig(model=...)`，Runner 会直接使用它。只有当你传的是 `"gpt-5.4-mini"`、`"openai/gpt-5.4-mini"`、`"litellm/..."` 这种字符串时，Runner 才需要通过 `ModelProvider.get_model()` 把字符串解析成可调用的 `Model`。

可以这样理解：

| 抽象 | 像什么 | 负责什么 | 不负责什么 |
|---|---|---|---|
| `Agent` | 角色说明书 | instructions、tools、handoffs、guardrails、默认 model 配置 | 不直接发请求，不跑循环 |
| `Runner` / `AgentRunner` | 执行调度器 | run 状态、turn 循环、session、trace、恢复、中断 | 不关心底层模型 API 细节 |
| `ModelProvider` | 模型工厂/路由表 | 把字符串模型名解析成具体 `Model`，管理默认模型、client、传输和缓存 | 不执行单次 Agent loop |
| `Model` | 模型 API 适配器 | 调用 LLM，返回 `ModelResponse` 或 stream events | 不执行工具，不决定 handoff |

核心调用链是：

```text
Runner.run(...)
  -> AgentRunner.run(...)
  -> run_internal/run_loop.py::run_single_turn(...)
  -> run_internal/turn_preparation.py::get_model(...)
  -> 如果 model 是字符串：run_config.model_provider.get_model(...)
  -> 得到具体 Model 实例
  -> Model.get_response(...) 或 Model.stream_response(...)
  -> turn_resolution 解析模型输出并执行工具、handoff 或最终输出。
```

## 再回答：为什么 Model 抽象里会出现 TResponseInputItem

你看到的疑惑是对的：`TResponseInputItem` 不是一个完全中立的模型输入类型，它在 `src/agents/items.py` 中实际是 OpenAI Python SDK 的类型别名：

```python
from openai.types.responses import ResponseInputItemParam

TResponseInputItem = ResponseInputItemParam
```

所以 `src/agents/models/interface.py` 里的 `Model` 抽象虽然叫“模型抽象”，但它不是完全厂商无关的领域模型接口。它采用了 OpenAI Responses API 的 item 结构作为这个 SDK 的内部统一中间格式。

这对 OpenAI 官方 SDK 是合理的，因为它的默认主线就是 OpenAI Responses API。Chat Completions、LiteLLM、AnyLLM 等其它路径也会在 provider/model adapter 中转换到这个统一格式，再交给 Runner、Tool、Session、Handoff、Tracing 使用。官方文档也把非 OpenAI 模型或混合模型栈放在 provider/adapter 层处理：[Agents models and providers](https://developers.openai.com/api/docs/guides/agents/models#providers-and-transport)。

但你自己的 PPT Agent 项目不建议照搬这一点。更好的做法是先定义自己的中立内部类型，例如 `AgentMessage`、`ToolCall`、`ToolResult`、`ModelRequest`、`ModelResponse`，再让 `OpenAIProvider`、`ClaudeProvider`、`DeepSeekProvider` 各自负责把中立类型转换成对应厂商 API 的请求和响应。

一句话记住：

- 学这个仓库时，把 `TResponseInputItem` 理解成“OpenAI Agents SDK 内部统一消息格式”。
- 做自己的 PPT Agent 时，不要让最底层抽象直接依赖 OpenAI 类型，要把厂商类型隔离在 provider adapter 里。

## 推荐阅读顺序

## 和你当前 agent-service Plan 的对应关系

你现在的 `agent-service` 计划仍然需要翻看本仓库，但要把它当成“成熟实现参考”，不是照抄对象。每个阶段只读对应文件和关键段落即可，不要一上来全仓通读。

| agent-service 阶段 | 本仓库重点文件 | 重点看什么 | 为什么要看 |
|---|---|---|---|
| M2 内部协议 | `src/agents/items.py`、`src/agents/models/interface.py` | `ModelResponse`、`RunItem`、工具调用 item、工具结果 item | 学会把模型输出、工具调用、工具结果统一成内部协议；同时提醒自己不要把 OpenAI 类型直接泄漏到自研核心协议。 |
| M3 Provider 抽象 | `src/agents/models/interface.py`、`src/agents/run_internal/turn_preparation.py`、`src/agents/models/openai_provider.py`、`src/agents/models/multi_provider.py` | `Model` / `ModelProvider` 区别、`get_model()` 如何解析字符串模型名、OpenAIProvider 如何选择 Responses/ChatCompletions/WebSocket | 这是你后续支持 OpenAI、DeepSeek、Claude、自建网关的基础。 |
| M3 OpenAI-compatible 转换 | `src/agents/models/openai_responses.py`、`src/agents/models/chatcmpl_converter.py` | `_build_response_create_kwargs()`、`Converter.convert_tools()`、Chat Completions 与 Responses 的格式互转 | 学 provider adapter 怎么把内部结构转换成某个厂商 API 的 wire format。 |
| M4 工具系统 | `src/agents/tool.py`、`src/agents/function_schema.py`、`src/agents/run_internal/tool_execution.py` | `FunctionTool`、`function_tool()`、函数签名转 JSON Schema、工具失败如何回注模型 | 这是 ReAct 和 PPT 工具链的核心：模型只会“请求工具”，真正执行和错误兜底要靠后端。 |
| M5 上下文构造 | `src/agents/memory/session.py`、`src/agents/memory/sqlite_session.py`、`src/agents/memory/openai_responses_compaction_session.py`、`src/agents/run_internal/turn_preparation.py` | Session 协议、SQLite 存储、长上下文压缩、`call_model_input_filter` | 学会“保存历史”和“构造本轮模型输入”不是一回事；后续 PPT 项目需要 ContextBuilder，而不是简单拼历史。 |
| M6 ReAct Loop | `src/agents/run.py`、`src/agents/run_internal/run_loop.py`、`src/agents/run_internal/turn_resolution.py`、`src/agents/run_internal/run_steps.py` | `Runner.run()`、`run_single_turn()`、`get_new_response()`、`process_model_response()`、`NextStepRunAgain` | 学 Agent runtime 最小状态机：模型响应后到底是 final、tool、handoff、interruption，还是继续下一轮。 |
| M8 Trace / Eval 基础 | `src/agents/tracing/spans.py`、`src/agents/tracing/traces.py`、`src/agents/tracing/span_data.py` | Trace 与 Span 的生命周期、span data 如何区分 agent/function/handoff/generation | 你的简历项目要能定位失败原因，trace 是生产级 Agent 和“调 API 脚本”的重要区别。 |
| M9 状态和恢复 | `src/agents/run_state.py`、`src/agents/run_internal/session_persistence.py`、`src/agents/run_internal/run_steps.py` | RunState、session save/rewind、中断后恢复 | 学会长任务、审批、失败重试不能只靠内存变量；正式产品要有可查询任务状态。 |
| M12 多 Agent handoff | `src/agents/handoffs/__init__.py`、`src/agents/handoffs/history.py`、`src/agents/run_internal/turn_resolution.py` | handoff 的数据结构、历史如何传给下一个 Agent、`NextStepHandoff` | 明确 handoff 是“控制权交接”，不是并发；先做串行可调试版本，再考虑复杂编排。 |
| M15 真实 Provider | `src/agents/models/openai_provider.py`、`src/agents/models/openai_responses.py`、`src/agents/models/chatcmpl_converter.py`、`src/agents/models/multi_provider.py` | 默认模型、base_url、client 复用、retry advice、兼容旧接口 | 这是接 DeepSeek/OpenAI-compatible 网关时最容易踩坑的地方：请求格式、工具能力、重试和错误语义都可能不同。 |
| M17 MCP / 外部工具 | `src/agents/mcp/server.py`、`src/agents/mcp/util.py` | MCP server 生命周期、tool filter、approval、MCP tool 转 FunctionTool | 后续接外部素材库、设计库、文件服务时会用到；但 MVP 阶段可以后置。 |

### 每次阅读的建议节奏

1. 先在 `agent-service/PLAN.md` 找到当前阶段的“先读”清单。
2. 打开上表对应文件，只看类注释、关键方法和我加的中文学习备注。
3. 用自己的话写一句阶段理解，例如“Provider 负责把模型名解析成 Model，Model 负责单次请求”。
4. 再回到 `agent-service` 写测试和实现，不要在 OpenAI 仓库里继续深挖无关分支。

如果某个文件读起来仍然很复杂，优先看我加了中文说明的入口：

- `models/interface.py`：解释抽象边界。
- `run_internal/turn_preparation.py`：解释模型、工具、handoff 是怎么在一轮调用前准备好的。
- `models/openai_provider.py`：解释字符串模型名怎么变成具体 Model。
- `models/openai_responses.py`：解释内部结构怎么转成 Responses API 请求。
- `run_internal/run_loop.py` 和 `turn_resolution.py`：解释 Agent Loop 状态机。

### 第一轮：只看主线

1. `src/agents/agent.py`
   - 看 `Agent` 的字段。
   - 理解 Agent 是配置容器，不是执行器。

2. `src/agents/run.py`
   - 看 `Runner.run()`、`Runner.run_streamed()`、`AgentRunner.run()`。
   - 理解一次 run 如何管理 session、trace、turn、恢复和中断。

3. `src/agents/run_internal/turn_preparation.py`
   - 看 `get_model()`、`get_model_settings()`、`get_all_tools()`、`get_handoffs()`。
   - 重点理解 model 字符串如何通过 provider 解析。

4. `src/agents/models/interface.py`
   - 看 `Model`、`ModelProvider`。
   - 这是模型接入层的抽象边界。

5. `src/agents/models/openai_provider.py`
   - 看 `OpenAIProvider.get_model()`。
   - 理解 provider 如何选择 Responses、Chat Completions 或 WebSocket。

6. `src/agents/models/openai_responses.py`
   - 看 `OpenAIResponsesModel.get_response()` 和 `stream_response()`。
   - 理解 SDK 内部结构如何落到真实 OpenAI Responses API 调用。

### 第二轮：看 Agent Loop 和工具

1. `src/agents/run_internal/run_loop.py`
   - 看 `run_single_turn()` 和 `get_new_response()`。
   - 理解一轮 turn 的结构：准备输入、调用模型、解析结果。

2. `src/agents/run_internal/turn_resolution.py`
   - 看 `process_model_response()` 和 `get_single_step_result_from_response()`。
   - 理解模型输出如何变成 final output、tool call、handoff、interruption 或 run again。

3. `src/agents/run_internal/run_steps.py`
   - 看 `ProcessedResponse`、`NextStepFinalOutput`、`NextStepHandoff`、`NextStepRunAgain`、`NextStepInterruption`。
   - 这是 runtime 状态机的数据结构。

4. `src/agents/tool.py`
   - 看 `FunctionTool` 和 `function_tool()`。
   - 理解 Python 函数如何变成模型可调用的工具。

5. `src/agents/function_schema.py`
   - 看函数签名和 docstring 如何变成 JSON Schema。
   - 这是自研工具系统必须掌握的基础。

### 第三轮：看生产能力

1. `src/agents/handoffs/__init__.py`
   - 理解 handoff 是控制权切换，不是并发。

2. `src/agents/memory/session.py` 和 `src/agents/memory/sqlite_session.py`
   - 理解会话历史如何保存和恢复。

3. `src/agents/tracing/`
   - 理解 Trace、Span、Processor 如何记录运行过程。

4. `src/agents/mcp/`
   - 理解外部 MCP Server 如何暴露工具。

5. `src/agents/realtime/`、`src/agents/voice/`、`src/agents/sandbox/`
   - 这些暂时不是 PPT Agent MVP 的第一优先级，先知道用途即可。

## 与你的 PPT Agent 项目的对应关系

| OpenAI Agents SDK 抽象 | PPT Agent 中可以怎么映射 |
|---|---|
| `Agent` | PlannerAgent、WriterAgent、DesignerAgent、AssemblerAgent 的配置。 |
| `Runner` | agent-service 的执行入口，统一处理 trace、memory、eval 和错误。 |
| `Model` | OpenAI、Claude、国产模型或自建模型网关的统一调用接口。 |
| `ModelProvider` | 根据配置选择模型厂商、模型名、base_url 和传输方式。 |
| `FunctionTool` | 模板检索、模板分析、生成 PPT 项目、图片搜索、素材下载等确定性工具。 |
| `Handoff` | Planner 把大纲交给 Writer，Writer/Designer 把结果交给 Assembler。 |
| `Session` | 用户一次 PPT 项目的多轮需求上下文。 |
| `Trace` / `Span` | 记录每次生成的模型调用、工具调用、handoff、RAG 检索和失败原因。 |

## 学习重点和暂时不用深挖的内容

优先深挖：

- `Agent`、`Runner`、`Model`、`ModelProvider`、`FunctionTool`、`Handoff`、`Session`、`Tracing`。
- `run_internal/run_loop.py` 和 `run_internal/turn_resolution.py`，它们最接近你后续自研 agent runtime。
- `models/openai_responses.py`，它展示了一个完整 provider adapter 如何接入真实模型 API。

暂时知道用途即可：

- `realtime/` 和 `voice/`：实时语音和低延迟交互路径，和 PPT Agent 主线距离较远。
- `sandbox/`：代码执行和文件环境隔离能力，后续如果做代码类 agent 再深入。
- `extensions/sandbox/`、`extensions/experimental/`：扩展和实验能力，先不要作为 MVP 主线。

## 阅读源码时的判断方法

如果一个类只保存字段、配置和校验，它通常是“配置层”。例如 `Agent`、`RunConfig`。

如果一个类负责 `run()`、`while turn`、`NextStep`、`RunState`，它通常是“runtime 层”。例如 `AgentRunner` 和 `run_internal`。

如果一个类负责 `get_response()`、`stream_response()`，它通常是“模型调用层”。例如 `OpenAIResponsesModel`。

如果一个类负责 `get_model(model_name)`，它通常是“provider 层”。例如 `OpenAIProvider` 和 `MultiProvider`。

如果一个类负责 Python 函数签名、JSON Schema、参数校验和执行，它通常是“工具层”。例如 `FunctionTool` 和 `function_tool()`。

## 实践建议

学习时不要先照抄整个 SDK。更适合你的路径是：

1. 先自研一个最小 `Model` 接口，只支持非流式 `chat()`。
2. 再加 `ModelProvider`，让配置字符串可以解析到不同模型实现。
3. 再做 `FunctionTool` 和工具执行器。
4. 再做最小 ReAct loop。
5. 再加 `Session`、`Trace`、`Eval`。
6. 最后再做 handoff、多 Agent、MCP 和部署。

这样你既能学懂 OpenAI Agents SDK 的成熟设计，也不会一开始被完整框架复杂度拖住。
