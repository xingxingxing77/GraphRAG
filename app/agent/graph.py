"""
LangGraph Agent 状态图构建与编译。

定义 Agent 的节点、边和条件路由，编译为可执行的 StateGraph。
"""

# --- 第三方库 ---
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

# --- 本地模块 ---
from app.agent.state import AgentState
from app.agent.nodes.planner import planner_node
from app.agent.nodes.tool_router import tool_router_node
from app.agent.nodes.reflector import reflector_node
from app.agent.nodes.generator import generator_node
from app.agent.nodes.self_correction import self_correction_node


def build_agent_graph() -> CompiledStateGraph:
    """构建并编译 LangGraph Agent 状态图。

    状态图流程:
        START -> Planner -> ToolRouter -> Executor -> Reflector
        Reflector -> (需要更多?) -> Planner (是) / Generator (否)
        Generator -> SelfCorrection -> (通过?) -> END (是) / Generator (否)

    Returns:
        CompiledStateGraph: 编译后的 Agent 状态图。
    """
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("planner", planner_node)
    graph.add_node("tool_router", tool_router_node)
    graph.add_node("reflector", reflector_node)
    graph.add_node("generator", generator_node)
    graph.add_node("self_correction", self_correction_node)

    # 定义边
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "tool_router")
    # TODO: 添加条件边：reflector 根据 needs_more_retrieval 路由
    # TODO: 添加条件边：self_correction 根据 faithfulness_score 路由
    graph.add_edge("generator", "self_correction")

    # TODO: 编译 graph 并返回
    # return graph.compile()
    raise NotImplementedError
