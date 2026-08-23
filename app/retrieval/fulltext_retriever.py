"""
Neo4j 全文检索器。

使用 Neo4j Lucene 全文索引进行文本搜索。
"""

# --- 本地模块 ---
from app.db.neo4j_client import Neo4jClient
from app.retrieval.dense_retriever import RetrievalResult


class FullTextRetriever:
    """全文检索器。

    利用 Neo4j 的 Lucene 全文索引进行文本搜索，
    作为稀疏向量检索的补充。
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        index_name: str = "entity_fulltext",
    ) -> None:
        """初始化全文检索器。

        Args:
            neo4j_client: Neo4j 客户端。
            index_name: 全文索引名称。
        """
        self.neo4j_client = neo4j_client
        self.index_name = index_name

    async def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """执行全文搜索。

        Args:
            query: 搜索关键词。
            top_k: 返回数量。

        Returns:
            检索结果列表（source="fulltext"）。
        """
        # TODO: 构建 CALL db.index.fulltext.queryNodes Cypher
        # TODO: 执行查询并格式化结果
        raise NotImplementedError
