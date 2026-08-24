"""Agent 状态图结构测试（单元 5.1 S3，07 §5 断言）。

断言：图编译成功；五节点全部注册；全部条件边路径可达
（START 出发可遍历到每个节点）；recursion_limit 常量约定。
"""

# --- 本地模块 ---
from app.agent.graph import RECURSION_LIMIT, build_agent_graph
from app.agent.routers import (
    NODE_GENERATOR,
    NODE_PLANNER,
    NODE_REFLECTOR,
    NODE_SELF_CORRECTION,
    NODE_TOOL_ROUTER,
)


class TestGraphStructure:
    """图注册与可达性（准出：全部条件边路径可达且有测试）。"""

    def test_compiles_with_five_nodes(self) -> None:
        graph = build_agent_graph()
        node_names = set(graph.get_graph().nodes.keys())
        for expected in (
            NODE_PLANNER,
            NODE_TOOL_ROUTER,
            NODE_REFLECTOR,
            NODE_GENERATOR,
            NODE_SELF_CORRECTION,
        ):
            assert expected in node_names

    def test_all_nodes_reachable_from_start(self) -> None:
        """START 出发经边可达全部节点（含条件边目标）。"""
        graph = build_agent_graph().get_graph()
        reachable: set[str] = set()
        stack = ["__start__"]
        while stack:
            current = stack.pop()
            for edge in graph.edges:
                if edge.source == current and edge.target not in reachable:
                    reachable.add(edge.target)
                    stack.append(edge.target)
        for expected in (
            NODE_PLANNER,
            NODE_TOOL_ROUTER,
            NODE_REFLECTOR,
            NODE_GENERATOR,
            NODE_SELF_CORRECTION,
        ):
            assert expected in reachable, f"{expected} 从 START 不可达"

    def test_recursion_limit_convention(self) -> None:
        """M3 约定：recursion_limit=15（reliability.yaml 同源）。"""
        assert RECURSION_LIMIT == 15

    def test_conditional_edges_present(self) -> None:
        """三处条件边绑定存在（tool_router/reflector/self_correction 之后）。"""
        graph = build_agent_graph().get_graph()
        conditional_sources = {
            edge.source for edge in graph.edges if edge.conditional
        }
        assert NODE_TOOL_ROUTER in conditional_sources
        assert NODE_REFLECTOR in conditional_sources
        assert NODE_SELF_CORRECTION in conditional_sources
