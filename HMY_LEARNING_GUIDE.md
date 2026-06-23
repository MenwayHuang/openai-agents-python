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

## 关键输入参数速查

这一节是给你以后“边看源码边对照参数”的。先把主链路参数看懂，再去看实现细节，会轻松很多。

### `Agent(...)`：定义一个 Agent 角色

源码位置：`src/agents/agent.py`

| 参数 / 字段 | 中文理解 | 什么时候重点关注 | 对你的 PPT Agent 怎么用 |
|---|---|---|---|
| `name` | Agent 名字，也会出现在 trace、handoff、日志里。 | 多 Agent 和调试时。 | 例如 `PlannerAgent`、`DesignerAgent`、`AssemblerAgent`。 |
| `instructions` | 系统提示词，可以是字符串，也可以是动态函数。 | 角色行为不稳定、输出不符合预期时。 | 规划 Agent 负责大纲，设计 Agent 负责组件布局，不要一个 prompt 混所有职责。 |
| `prompt` | OpenAI Responses API 的 Prompt 配置，可能由服务端管理。 | 使用 OpenAI 平台 Prompt 管理时。 | MVP 阶段可先不用，优先把 prompt 放在自己代码和配置里。 |
| `model` | 模型配置，可以是字符串，也可以是 `Model` 实例。 | Provider 抽象、模型切换、mock 测试时。 | 正式项目建议先用字符串配置，例如 `openai/gpt-4.1`、`deepseek/deepseek-chat`。 |
| `model_settings` | 温度、top_p、max tokens、tool_choice、retry 等模型参数。 | 输出不稳定、成本过高、工具调用不受控时。 | 规划/结构化输出适合低温度；创意文案可适当提高温度。 |
| `tools` | 本地函数工具列表。 | ReAct、PPT 后端工具调用时。 | 模板检索、组件组合、生成 PPT、图片搜索都应包装成工具。 |
| `mcp_servers` | 外部 MCP 工具服务器列表。 | 后续接素材库、文件系统、设计服务时。 | MVP 可后置；生产环境必须配合白名单和审批。 |
| `handoffs` | 可以转交给哪些 Agent。 | 多 Agent 编排时。 | Planner 规划后可 handoff 给 Writer/Designer/Assembler。 |
| `input_guardrails` | 模型运行前的输入检查。 | 防止非法需求、越权文件路径、敏感输入时。 | 检查用户是否要求读取不允许路径、是否包含危险指令。 |
| `output_guardrails` | 最终输出后的检查。 | 输出必须符合业务规则时。 | 检查 PPT 大纲字段完整、页数范围、组件 id 是否存在。 |
| `output_type` | 最终输出结构，可以是 Pydantic/dataclass/TypedDict。 | 需要结构化结果时。 | PPT 大纲、组件组合计划、任务报告都建议定义结构化类型。 |
| `hooks` | 生命周期回调。 | 需要日志、监控、调试时。 | 可记录每个 Agent 开始/结束、模型调用、工具调用。 |
| `tool_use_behavior` | 工具执行后是继续让 LLM 总结，还是工具结果直接作为最终输出。 | 工具结果是否还需要模型加工时。 | 大多数 PPT 工具先用 `run_llm_again`；导出文件类工具可考虑直接返回结果。 |
| `reset_tool_choice` | 工具调用后是否重置 tool_choice。 | 防止模型被迫一直调用同一个工具时。 | 生产项目通常保持默认 `True`。 |

### `Runner.run(...)`：启动一次 Agent 执行

源码位置：`src/agents/run.py`

| 参数 | 中文理解 | 容易误解的点 | 对你的 PPT Agent 怎么用 |
|---|---|---|---|
| `starting_agent` | 从哪个 Agent 开始执行。 | 后续 handoff 可能切换当前 Agent。 | 通常从 Planner 或入口 Orchestrator 开始。 |
| `input` | 用户输入，可以是字符串、input item list，也可以是恢复用的 `RunState`。 | 字符串只是最简单入口；恢复中断时会传 `RunState`。 | 前端用户需求先转成字符串或内部消息结构。 |
| `context` | 运行时上下文对象，会传给工具、handoff、guardrail。 | 它不是聊天历史，而是业务上下文。 | 放 user_id、project_id、tenant_id、trace_id、资产库权限等。 |
| `max_turns` | 最大模型轮次，防止无限循环。 | 一轮通常指一次模型调用，不等于一次工具调用。 | MVP 可设 6-10；发现循环时必须看 trace。 |
| `hooks` | run 级别生命周期回调。 | 和 Agent 自己的 hooks 作用域不同。 | 统一写结构化日志、成本统计、trace 事件。 |
| `run_config` | 全局运行配置，覆盖模型、provider、trace、工具策略等。 | 优先级通常高于 Agent 默认配置。 | 按环境切 OpenAI/DeepSeek，按用户套餐控制模型。 |
| `error_handlers` | 运行错误处理器。 | 不是普通 try/except 的替代，而是运行框架内的策略入口。 | 可把模型错误、工具错误转换成可展示任务状态。 |
| `previous_response_id` | OpenAI Responses API 的上一轮 response id。 | 强依赖 OpenAI 服务端状态，不适合所有 provider。 | 自研中立 Provider 初期可不用。 |
| `auto_previous_response_id` | 自动使用 response id 串联服务端历史。 | 混合 provider 时容易造成历史不一致。 | 早期建议用自己的 ContextBuilder 管历史。 |
| `conversation_id` | OpenAI 服务端 conversation id。 | 官方服务端管理历史，不等于你自己的项目会话表。 | 正式 PPT 项目建议自建任务/消息/项目存储。 |
| `session` | 本地/数据库 Session，保存对话 input items。 | Session 只管历史，不等于 Agent memory/RAG。 | 可以映射到项目会话历史；长期生产建议用数据库实现。 |

### `Model.get_response(...)`：非流式模型调用接口

源码位置：`src/agents/models/interface.py`

| 参数 | 中文理解 | 为什么重要 | 自研项目建议 |
|---|---|---|---|
| `system_instructions` | 本轮发给模型的系统提示词。 | 决定角色行为，是 ContextBuilder 的重要输出。 | 从 Agent 配置、任务阶段、用户上下文组合生成。 |
| `input` | 本轮模型输入。官方 SDK 用 Responses input item。 | 这是你疑惑过的地方：它不是完全厂商无关。 | 自研项目应定义自己的中立 `ModelInput` / `AgentMessage`。 |
| `model_settings` | 温度、max_tokens、tool_choice、retry 等参数。 | 影响质量、成本、工具调用策略。 | 不同 Agent 应有不同默认参数。 |
| `tools` | 本轮可用工具。 | 模型只能调用这里暴露的工具。 | 每轮按权限和阶段裁剪工具，不要全量暴露。 |
| `output_schema` | 最终输出结构约束。 | 适合让模型直接产出结构化结果。 | PPT 大纲、组件计划、评分报告都可用。 |
| `handoffs` | 本轮可用 handoff。 | 在模型视角通常也是特殊 function tool。 | 先做串行 handoff，动态路由后置。 |
| `tracing` | 是否记录输入输出和调用数据。 | 生产系统要能排查，但不能泄露隐私。 | 默认记录 metadata/usage，敏感内容要脱敏。 |
| `previous_response_id` | OpenAI 服务端历史衔接。 | 可少传历史，但绑定 OpenAI Responses 能力。 | 不作为自研核心协议的一部分。 |
| `conversation_id` | OpenAI 服务端会话。 | 由 OpenAI 管历史，不等于业务数据库。 | PPT 项目应优先自建 run/message/project 表。 |
| `prompt` | OpenAI Prompt 管理配置。 | 服务端 prompt 可能管理模型和工具。 | MVP 可先不引入，避免调试边界变复杂。 |

### `OpenAIResponsesModel._build_response_create_kwargs(...)`：把内部请求转成 OpenAI API 请求

源码位置：`src/agents/models/openai_responses.py`

| 参数 | 中文理解 | 阅读重点 |
|---|---|---|
| `system_instructions` | 转成 Responses API 的 `instructions`。 | 系统提示词不应混进普通 user message。 |
| `input` | 转成 Responses API 的 `input`。 | 先统一格式，再清理不兼容字段。 |
| `model_settings` | 展开成 `temperature`、`top_p`、`tool_choice`、`reasoning`、`metadata` 等。 | Provider 负责把通用设置翻译成厂商字段。 |
| `tools` | 交给 `Converter.convert_tools()` 变成 OpenAI `tools` payload。 | 模型看到的是 schema，不是 Python 函数。 |
| `output_schema` | 转成 `text.format=json_schema`。 | 结构化最终输出和工具参数是两种机制。 |
| `handoffs` | 转成特殊 function tool。 | handoff 在 API 层像工具，在 runtime 层会切换 Agent。 |
| `previous_response_id` / `conversation_id` | OpenAI 服务端状态字段。 | 自研中立协议不要依赖它们。 |
| `stream` | 是否请求流式响应。 | 流式只是传输方式，最终仍要进入 turn resolution。 |
| `prompt` | OpenAI 服务端 Prompt 配置。 | 初期可以不学太深。 |

### `FunctionTool` 和 `function_tool(...)`：把 Python 函数暴露给模型

源码位置：`src/agents/tool.py`

| 参数 / 字段 | 中文理解 | 生产注意点 |
|---|---|---|
| `name` / `name_override` | 模型看到的工具名。 | 名字要稳定，别随意改，否则 trace、eval、历史回放都会受影响。 |
| `description` / `description_override` | 模型看到的工具用途说明。 | 描述越清晰，模型越不容易乱用工具。 |
| `params_json_schema` | 工具参数 JSON Schema。 | 这是模型生成参数和后端校验参数的契约。 |
| `on_invoke_tool` | 真正执行 Python 逻辑的函数。 | 所有副作用、鉴权、超时、错误处理都要在这里或执行器里管住。 |
| `strict_json_schema` / `strict_mode` | 是否使用严格 schema。 | 建议默认严格，能减少模型输出脏参数。 |
| `is_enabled` | 工具是否对当前上下文可用。 | 可按用户权限、项目状态、阶段动态控制。 |
| `needs_approval` | 工具执行前是否需要审批。 | 文件写入、外部发送、支付、删除等高风险动作应需要审批。 |
| `tool_input_guardrails` | 工具执行前检查参数。 | 防路径穿越、非法模板 id、越权素材库访问。 |
| `tool_output_guardrails` | 工具执行后检查结果。 | 防工具返回不合法结构或敏感数据。 |
| `timeout` / `timeout_behavior` | 工具超时和超时后的处理方式。 | 生产系统必须有超时，否则一次工具卡死会拖垮 run。 |
| `failure_error_function` | 工具异常如何转成模型可读错误。 | 好的错误回注能让模型自我修正，而不是整个任务失败。 |
| `defer_loading` | 是否延迟加载工具定义。 | 大规模工具库才需要；MVP 先不用。 |

### `Handoff`：一个 Agent 把控制权交给另一个 Agent

源码位置：`src/agents/handoffs/__init__.py`

| 参数 / 字段 | 中文理解 | 对你的项目怎么用 |
|---|---|---|
| `tool_name` | 模型调用 handoff 时看到的工具名。 | 例如 `transfer_to_designer_agent`。 |
| `tool_description` | 告诉模型什么时候应该转交。 | 描述越清楚，handoff 越可控。 |
| `input_json_schema` | handoff 工具参数 schema。 | 只描述转交参数，不是下一个 Agent 的全部上下文。 |
| `on_invoke_handoff` | 执行转交，返回目标 Agent。 | 可以根据上下文选择具体子 Agent。 |
| `agent_name` | 目标 Agent 名字。 | 用于 trace、日志、工具输出。 |
| `input_filter` | 过滤/改写交给下一个 Agent 的历史。 | 防止把无关工具结果或敏感历史传给下游 Agent。 |
| `nest_handoff_history` | 是否嵌套整理 handoff 历史。 | 多 Agent 历史复杂时再看，MVP 可先保持简单。 |
| `strict_json_schema` | handoff 参数是否严格校验。 | 建议保持严格。 |
| `is_enabled` | 当前是否允许这个 handoff。 | 可按阶段、权限、产品功能开关控制。 |

### `Session` / `SQLiteSession`：保存会话历史

源码位置：`src/agents/memory/session.py`、`src/agents/memory/sqlite_session.py`

| 方法 / 参数 | 中文理解 | 对你的项目怎么用 |
|---|---|---|
| `session_id` | 会话唯一标识。 | 可映射到 `project_id`、`run_id` 或用户会话 id。 |
| `get_items(limit)` | 取最近 N 条历史。 | ContextBuilder 会从这里取历史，但还要再裁剪和摘要。 |
| `add_items(items)` | 保存新消息、工具调用、工具结果。 | 每轮结束后持久化，便于恢复和审计。 |
| `pop_item()` | 弹出最后一条历史。 | 重试、回滚、测试时有用。 |
| `clear_session()` | 清空会话。 | 谨慎暴露，生产环境需要权限和审计。 |
| `db_path` | SQLite 文件路径。 | 本地开发可用 SQLite；生产建议 PostgreSQL。 |
| `sessions_table` / `messages_table` | 表名配置。 | 只能来自可信配置，不要用用户输入拼 SQL 表名。 |

### `MCPServer`：外部工具服务接入

源码位置：`src/agents/mcp/server.py`、`src/agents/mcp/util.py`

| 参数 / 方法 | 中文理解 | 生产注意点 |
|---|---|---|
| `connect()` | 建立和 MCP server 的连接。 | 只连服务，不执行工具。 |
| `cleanup()` | 清理连接、子进程、HTTP session。 | 防止资源泄露。 |
| `list_tools()` | 发现外部工具。 | 不能全量暴露，必须做白名单/权限过滤。 |
| `call_tool()` | 真正调用外部工具。 | 副作用入口，要有鉴权、超时、审批、错误脱敏。 |
| `tool_filter` | 静态或动态过滤工具。 | 生产默认白名单，不要只靠黑名单。 |
| `require_approval` | 工具调用审批策略。 | 高风险工具必须审批。 |
| `failure_error_function` | MCP 工具失败如何回注模型。 | 让模型可修正，同时不要泄露内部异常。 |
| `cache_tools_list` | 是否缓存工具列表。 | 缓存可降延迟，但权限和工具版本变化时要小心。 |
| `MCPServerStdio` | 本地子进程 MCP。 | 命令、cwd、env 必须来自可信配置。 |
| `MCPServerSse` | HTTP + SSE MCP。 | 需要认证、HTTPS、超时。 |
| `MCPServerStreamableHttp` | 新版 HTTP MCP。 | 更适合未来内网服务和 Go 网关治理。 |

## 当前中文备注覆盖边界

我已经把你当前学习和 `agent-service` 计划最相关的主线补了中文备注，包括：

- Agent 配置层：`agent.py`。
- Runner 入口和单轮循环：`run.py`、`run_internal/run_loop.py`、`run_internal/turn_resolution.py`、`run_internal/run_steps.py`。
- 模型抽象和 Provider：`models/interface.py`、`models/openai_provider.py`、`models/multi_provider.py`、`models/openai_responses.py`、`models/chatcmpl_converter.py`。
- 工具系统：`tool.py`、`function_schema.py`、`run_internal/tool_execution.py`。
- 记忆和上下文：`memory/session.py`、`memory/sqlite_session.py`、`memory/openai_responses_compaction_session.py`。
- Trace：`tracing/spans.py`、`tracing/traces.py`、`tracing/span_data.py`。
- Handoff：`handoffs/__init__.py`。
- MCP：`mcp/server.py`、`mcp/util.py`。

暂时没有逐行重注释的目录包括 `realtime/`、`voice/`、`sandbox/`、大量 examples 和测试文件。它们不是你 9 月前 PPT Agent 主线的第一优先级。等你后续计划真正进入 MCP、沙箱或实时语音，再按阶段继续补。

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
