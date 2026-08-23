"""
图谱代理端点（02 §3.6，单元 2.4 雏形）。

GET /graph/subgraph —— 后端代理 Cypher 子图查询并序列化为 NVL 格式。
安全约束：bolt 地址与数据库凭证严禁出现在响应或前端代码中。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Depends, Query
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from neo4j.graph import Node, Relationship

# --- 本地模块 ---
from app.api.deps import get_neo4j_client
from app.api.errors import ApiError, ErrorCode
from app.core.models import GraphNode, GraphRelationship, SubgraphResponse
from app.db.neo4j_client import Neo4jClient

router = APIRouter()


def _node_to_graph_node(node: Node) -> GraphNode:
    """将 Neo4j 节点转换为 NVL 节点格式。

    Args:
        node: Neo4j 节点。

    Returns:
        GraphNode（id 取 elementId，label 取 canonical_name/name）。
    """
    props = dict(node)
    label = str(props.get("canonical_name") or props.get("name") or node.element_id)
    zone = str(props.get("zone") or "open")
    if zone not in {"core", "open"}:
        zone = "open"
    node_type = str(props.get("type") or "Other")
    return GraphNode(id=node.element_id, label=label, type=node_type, zone=zone)  # type: ignore[arg-type]


def _rel_to_graph_relationship(rel: Relationship, id_map: dict[str, str]) -> GraphRelationship:
    """将 Neo4j 关系转换为 NVL 关系格式。

    Args:
        rel: Neo4j 关系。
        id_map: elementId → 已收录节点 ID 的映射（端点可见性过滤）。

    Returns:
        GraphRelationship。
    """
    return GraphRelationship(
        source=id_map.get(rel.start_node.element_id, rel.start_node.element_id),
        target=id_map.get(rel.end_node.element_id, rel.end_node.element_id),
        type=rel.type,
    )


@router.get("/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    entity: str = Query(..., description="规范实体名（canonical_name）"),
    depth: int = Query(default=2, le=3, description="扩展深度，上限 3"),
    limit: int = Query(default=50, le=200, description="节点数上限 200"),
    client: Neo4jClient = Depends(get_neo4j_client),
) -> SubgraphResponse:
    """按实体查询可视化子图（@neo4j-nvl/react 直接可用格式）。

    Args:
        entity: 规范实体名（必填）。
        depth: 扩展深度（默认 2，上限 3）。
        limit: 节点数量上限（默认 50，上限 200）。
        client: Neo4j 客户端。

    Returns:
        SubgraphResponse: {nodes[], relationships[]}。

    Raises:
        ApiError: GRAPH_404_ENTITY_NOT_FOUND / GRAPH_503_STORE_UNAVAILABLE。
    """
    # TODO: JWT 鉴权依赖注入（10.2）
    depth = max(1, min(depth, 3))
    # depth 为已校验的小整数，拼接安全；实体名经参数化防注入
    cypher = (
        "MATCH (e:Entity {canonical_name: $entity}) "
        f"OPTIONAL MATCH path = (e)-[*1..{depth}]-(n) "
        "WITH e, collect(path) AS paths "
        "WITH e, reduce(ns = [e], p IN paths | ns + nodes(p)) AS all_nodes, "
        "     reduce(rs = [], p IN paths | rs + relationships(p)) AS all_rels "
        "RETURN all_nodes[0..$limit] AS ns, all_rels AS rs"
    )
    try:
        rows = await client.execute_cypher(cypher, {"entity": entity, "limit": limit})
    except ServiceUnavailable as exc:
        raise ApiError(
            ErrorCode.GRAPH_503_STORE_UNAVAILABLE,
            "Neo4j 不可用（no-graph 降级中）",
        ) from exc
    except Neo4jError as exc:
        raise ApiError(
            ErrorCode.GRAPH_503_STORE_UNAVAILABLE, f"图查询失败: {exc}"
        ) from exc

    if not rows or not rows[0].get("ns"):
        raise ApiError(ErrorCode.GRAPH_404_ENTITY_NOT_FOUND, f"实体未收录: {entity}")

    raw_nodes: list[Node] = rows[0]["ns"]
    raw_rels: list[Relationship] = rows[0]["rs"] or []

    # 去重节点并建立 elementId 映射
    nodes: list[GraphNode] = []
    id_map: dict[str, str] = {}
    for n in raw_nodes:
        if n.element_id in id_map:
            continue
        graph_node = _node_to_graph_node(n)
        id_map[n.element_id] = graph_node.id
        nodes.append(graph_node)
        if len(nodes) >= limit:
            break

    # 关系仅保留两端均可见的边
    relationships = [
        _rel_to_graph_relationship(r, id_map)
        for r in raw_rels
        if r.start_node.element_id in id_map and r.end_node.element_id in id_map
    ]
    return SubgraphResponse(nodes=nodes, relationships=relationships)
