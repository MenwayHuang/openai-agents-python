# 中文学习注释：
# 这个文件只是提供 handoff 场景的推荐 prompt 前缀。
# 它不参与 runtime 逻辑，作用是告诉模型“你属于多 Agent 系统，handoff 是后台行为，不要对用户强调转交过程”。

# A recommended prompt prefix for agents that use handoffs. We recommend including this or
# similar instructions in any agents that use handoffs.
RECOMMENDED_PROMPT_PREFIX = (
    "# System context\n"
    "You are part of a multi-agent system called the Agents SDK, designed to make agent "
    "coordination and execution easy. Agents uses two primary abstraction: **Agents** and "
    "**Handoffs**. An agent encompasses instructions and tools and can hand off a "
    "conversation to another agent when appropriate. "
    "Handoffs are achieved by calling a handoff function, generally named "
    "`transfer_to_<agent_name>`. Transfers between agents are handled seamlessly in the background;"
    " do not mention or draw attention to these transfers in your conversation with the user.\n"
)


def prompt_with_handoff_instructions(prompt: str) -> str:
    """
    Add recommended instructions to the prompt for agents that use handoffs.
    """
    # 简单字符串拼接，把推荐前缀加到用户自己的 prompt 前面。
    return f"{RECOMMENDED_PROMPT_PREFIX}\n\n{prompt}"
