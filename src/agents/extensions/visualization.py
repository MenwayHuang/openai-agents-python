from __future__ import annotations

import graphviz  # type: ignore

from agents import Agent
from agents.handoffs import Handoff

# 学习提示：这个扩展用 graphviz 生成 Agent/工具/Handoff 的关系图。
# graphviz 是第三方绘图库，这里先生成 DOT 文本，再由 graphviz.Source 渲染图片。
# 对复杂 PPT Agent 编排很有帮助：可以把“规划 Agent -> 模板 Agent -> 质检 Agent”画出来。


def get_main_graph(agent: Agent) -> str:
    """
    Generates the main graph structure in DOT format for the given agent.

    Args:
        agent (Agent): The agent for which the graph is to be generated.

    Returns:
        str: The DOT format string representing the graph.
    """
    parts = [
        """
    digraph G {
        graph [splines=true];
        node [fontname="Arial"];
        edge [penwidth=1.5];
    """
    ]
    # DOT 图由节点和边两部分组成；这里分别递归收集。
    parts.append(get_all_nodes(agent))
    parts.append(get_all_edges(agent))
    parts.append("}")
    return "".join(parts)


def get_all_nodes(
    agent: Agent, parent: Agent | None = None, visited: set[str] | None = None
) -> str:
    """
    Recursively generates the nodes for the given agent and its handoffs in DOT format.

    Args:
        agent (Agent): The agent for which the nodes are to be generated.

    Returns:
        str: The DOT format string representing the nodes.
    """
    if visited is None:
        visited = set()
    # visited 防止 handoff 形成环时递归无限循环。
    if agent.name in visited:
        return ""
    visited.add(agent.name)

    parts = []

    # Start and end the graph
    if not parent:
        parts.append(
            '"__start__" [label="__start__", shape=ellipse, style=filled, '
            "fillcolor=lightblue, width=0.5, height=0.3];"
            '"__end__" [label="__end__", shape=ellipse, style=filled, '
            "fillcolor=lightblue, width=0.5, height=0.3];"
        )
        # Ensure parent agent node is colored
        parts.append(
            f'"{agent.name}" [label="{agent.name}", shape=box, style=filled, '
            "fillcolor=lightyellow, width=1.5, height=0.8];"
        )

    for tool in agent.tools:
        parts.append(
            f'"{tool.name}" [label="{tool.name}", shape=ellipse, style=filled, '
            f"fillcolor=lightgreen, width=0.5, height=0.3];"
        )

    for mcp_server in agent.mcp_servers:
        parts.append(
            f'"{mcp_server.name}" [label="{mcp_server.name}", shape=box, style=filled, '
            f"fillcolor=lightgrey, width=1, height=0.5];"
        )

    for handoff in agent.handoffs:
        if isinstance(handoff, Handoff):
            # Handoff 是封装后的交接对象，里面记录目标 agent_name。
            parts.append(
                f'"{handoff.agent_name}" [label="{handoff.agent_name}", '
                f"shape=box, style=filled, style=rounded, "
                f"fillcolor=lightyellow, width=1.5, height=0.8];"
            )
        if isinstance(handoff, Agent):
            # handoffs 也允许直接放 Agent 对象，所以要继续递归它的工具和子 handoff。
            if handoff.name not in visited:
                parts.append(
                    f'"{handoff.name}" [label="{handoff.name}", '
                    f"shape=box, style=filled, style=rounded, "
                    f"fillcolor=lightyellow, width=1.5, height=0.8];"
                )
            parts.append(get_all_nodes(handoff, agent, visited))

    return "".join(parts)


def get_all_edges(
    agent: Agent, parent: Agent | None = None, visited: set[str] | None = None
) -> str:
    """
    Recursively generates the edges for the given agent and its handoffs in DOT format.

    Args:
        agent (Agent): The agent for which the edges are to be generated.
        parent (Agent, optional): The parent agent. Defaults to None.

    Returns:
        str: The DOT format string representing the edges.
    """
    if visited is None:
        visited = set()
    # 边的生成也要防环，逻辑和节点类似。
    if agent.name in visited:
        return ""
    visited.add(agent.name)

    parts = []

    if not parent:
        parts.append(f'"__start__" -> "{agent.name}";')

    for tool in agent.tools:
        parts.append(f"""
        "{agent.name}" -> "{tool.name}" [style=dotted, penwidth=1.5];
        "{tool.name}" -> "{agent.name}" [style=dotted, penwidth=1.5];""")

    for mcp_server in agent.mcp_servers:
        parts.append(f"""
        "{agent.name}" -> "{mcp_server.name}" [style=dashed, penwidth=1.5];
        "{mcp_server.name}" -> "{agent.name}" [style=dashed, penwidth=1.5];""")

    for handoff in agent.handoffs:
        if isinstance(handoff, Handoff):
            parts.append(f"""
            "{agent.name}" -> "{handoff.agent_name}";""")
        if isinstance(handoff, Agent):
            parts.append(f"""
            "{agent.name}" -> "{handoff.name}";""")
            parts.append(get_all_edges(handoff, agent, visited))

    if not agent.handoffs:
        parts.append(f'"{agent.name}" -> "__end__";')

    return "".join(parts)


def draw_graph(agent: Agent, filename: str | None = None) -> graphviz.Source:
    """
    Draws the graph for the given agent and optionally saves it as a PNG file.

    Args:
        agent (Agent): The agent for which the graph is to be drawn.
        filename (str): The name of the file to save the graph as a PNG.

    Returns:
        graphviz.Source: The graphviz Source object representing the graph.
    """
    dot_code = get_main_graph(agent)
    graph = graphviz.Source(dot_code)

    if filename:
        # render 会调用本机 graphviz 可执行文件；环境没有安装 graphviz 时这里可能失败。
        graph.render(filename, format="png", cleanup=True)

    return graph
