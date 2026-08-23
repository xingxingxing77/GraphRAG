"""
Neo4j 图数据库客户端封装（04 §5 · 单元 2.4）。

封装 Neo4j 异步驱动的初始化、连接管理与 Cypher 执行；
ensure_constraints 落地 04 §5.3 约束与索引 DDL（DBA 执行清单）。
全文检索外置 Elasticsearch（J5），本客户端不建全文索引。
"""

# --- 标准库 ---
import logging
from typing import Any, Optional

# --- 第三方库 ---
from neo4j import AsyncDriver, AsyncGraphDatabase

logger = logging.getLogger(__name__)

# 04 §5.3 约束与索引 DDL（DBA 执行清单，逐条幂等执行）
_CONSTRAINT_DDLS: tuple[str, ...] = (
    "CREATE CONSTRAINT entity_canonical IF NOT EXISTS "
    "FOR (e:Entity) REQUIRE e.canonical_name IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS "
    "FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT community_id IF NOT EXISTS "
    "FOR (m:Community) REQUIRE m.community_id IS UNIQUE",
    "CREATE INDEX entity_type IF NOT EXISTS "
    "FOR (e:Entity) ON (e.type)",
    "CREATE INDEX entity_zone_status IF NOT EXISTS "
    "FOR (e:Entity) ON (e.zone, e.status)",
    "CREATE INDEX chunk_docid IF NOT EXISTS "
    "FOR (c:Chunk) ON (c.doc_id)",
    "CREATE INDEX community_level IF NOT EXISTS "
    "FOR (m:Community) ON (m.level)",
)


class Neo4jClient:
    """Neo4j 异步客户端封装。

    Attributes:
        uri: Neo4j 连接 URI。
        user: Neo4j 用户名。
        password: Neo4j 密码。
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        """初始化 Neo4j 客户端。

        Args:
            uri: Neo4j 连接 URI，如 ``bolt://localhost:7687``。
            user: 用户名。
            password: 密码。
        """
        self.uri = uri
        self.user = user
        self.password = password
        self._driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        """建立 Neo4j 异步驱动连接并验证可达。

        Raises:
            neo4j.exceptions.ServiceUnavailable: 无法连接到 Neo4j。
        """
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        """关闭 Neo4j 驱动连接，释放连接池。"""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def _ensure_driver(self) -> AsyncDriver:
        """确保驱动已建立。

        Returns:
            AsyncDriver 实例。
        """
        if self._driver is None:
            await self.connect()
        assert self._driver is not None
        return self._driver

    async def execute_cypher(
        self,
        query: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """执行 Cypher 查询并返回结果列表。

        Args:
            query: Cypher 查询语句。
            parameters: 查询参数。

        Returns:
            查询结果的字典列表。

        Raises:
            neo4j.exceptions.Neo4jError: Cypher 执行失败。
        """
        driver = await self._ensure_driver()
        async with driver.session() as session:
            result = await session.run(query, parameters or {})
            return [record.data() async for record in result]

    async def ensure_constraints(self) -> None:
        """落地 04 §5.3 约束与索引（幂等，IF NOT EXISTS）。

        Raises:
            neo4j.exceptions.Neo4jError: DDL 执行失败。
        """
        for ddl in _CONSTRAINT_DDLS:
            await self.execute_cypher(ddl)
        logger.info("Neo4j 约束与索引就绪（%d 条 DDL）", len(_CONSTRAINT_DDLS))

    async def find_entities(
        self,
        entity_names: list[str],
        relationship_depth: int = 2,
    ) -> list[dict[str, Any]]:
        """根据实体名称列表查询相关子图（Local Search，04 §5.4）。

        Args:
            entity_names: 实体名称列表（canonical_name）。
            relationship_depth: 关系扩展深度（跳数）。

        Returns:
            匹配的实体及其关系的字典列表。
        """
        # TODO(阶段 3 graph_retriever): 04 §5.4 Local Search 模板
        #   MATCH (e:Entity {canonical_name: $entity})-[r]-(n) RETURN e, r, n
        raise NotImplementedError

    async def check_health(self) -> bool:
        """检查 Neo4j 连接健康状态。

        Returns:
            True 表示连接正常，False 表示异常。
        """
        try:
            rows = await self.execute_cypher("RETURN 1 AS ok")
            return bool(rows) and rows[0].get("ok") == 1
        except Exception:  # noqa: BLE001 - 健康检查不抛错
            return False
