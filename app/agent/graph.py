"""
LangGraph Agent 状态图构建与编译（05 §5.3 组装顺序）。

节点注册 + 条件边绑定；条件边路由函数集中于 `app/agent/routers.py`
（消费 AgentState ★ 字段）。完整链路（load_memory/query_understanding
前置节点、检索子图化、写侧尾节点）随阶段 5/8/10 单元逐步接入。
"""

# --- 第三方库 ---
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

# --- 本地模块 ---
from app.agent.nodes.generator import generator_node
from app.agent.nodes.planner import planner_node
from app.agent.nodes.reflector import reflector_node
from app.agent.nodes.self_correction import self_correction_node
from app.agent.nodes.tool_router import tool_router_node
from app.agent.routers import (
    NODE_GENERATOR,
    NODE_PLANNER,
    NODE_REFLECTOR,
    NODE_SELF_CORRECTION,
    NODE_TOOL_ROUTER,
    route_after_reflector,
    route_after_self_correction,
    route_after_tool_router,
)
from app.agent.state import AgentState

# recursion_limit 编译期约定值（M3，05 §5.3）：正常路径不允许触达，
# 仅作为最后防线；run 调用时经 config={"recursion_limit": RECURSION_LIMIT} 生效
RECURSION_LIMIT = 15


def build_agent_graph() -> CompiledStateGraph[AgentState]:
    """构建并编译 LangGraph Agent 状态图。

    状态图流程（05 §5.3，骨架阶段为五节点主环）:
        START -> planner -> tool_router
        tool_router -> [cond] 直答/B4 预算耗尽 -> generator
                    -> 其余 -> reflector
        reflector -> [cond needs_more_retrieval && rounds<3] -> planner(增量补计划)
                  -> 否则 -> generator
        generator -> self_correction -> [cond score<阈值 && retries<1] -> generator
                                     -> 否则 -> END

    Returns:
        CompiledStateGraph: 编译后的 Agent 状态图。
    """
    graph = StateGraph(AgentState)

    # --- 节点注册 ---
    graph.add_node(NODE_PLANNER, planner_node)
    graph.add_node(NODE_TOOL_ROUTER, tool_router_node)
    graph.add_node(NODE_REFLECTOR, reflector_node)
    graph.add_node(NODE_GENERATOR, generator_node)
    graph.add_node(NODE_SELF_CORRECTION, self_correction_node)

    # --- 边绑定 ---
    graph.add_edge(START, NODE_PLANNER)
    graph.add_edge(NODE_PLANNER, NODE_TOOL_ROUTER)
    # 直答单步(J9) / B4 预算耗尽 -> generator；其余 -> reflector
    graph.add_conditional_edges(
        NODE_TOOL_ROUTER,
        route_after_tool_router,
        {NODE_GENERATOR: NODE_GENERATOR, NODE_REFLECTOR: NODE_REFLECTOR},
    )
    # 回环补检索（上限 3 轮）或进入生成
    graph.add_conditional_edges(
        NODE_REFLECTOR,
        route_after_reflector,
        {NODE_PLANNER: NODE_PLANNER, NODE_GENERATOR: NODE_GENERATOR},
    )
    graph.add_edge(NODE_GENERATOR, NODE_SELF_CORRECTION)
    # 忠实度不达标且重试未耗尽 -> 重生成；否则结束
    graph.add_conditional_edges(
        NODE_SELF_CORRECTION,
        route_after_self_correction,
        {NODE_GENERATOR: NODE_GENERATOR, END: END},
    )

    return graph.compile()
