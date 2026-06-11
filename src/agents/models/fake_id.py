FAKE_RESPONSES_ID = "__fake_id__"
"""This is a placeholder ID used to fill in the `id` field in Responses API related objects. It's
useful when you're creating Responses objects from non-Responses APIs, e.g. the OpenAI Chat
Completions API or other LLM providers.
"""

# 学习提示：一些内部流程统一按 Responses 对象处理，但 Chat Completions 或第三方模型
# 不一定真的返回 Responses 的 id。这里用固定假 id 补齐结构，表示“只是适配占位”。
