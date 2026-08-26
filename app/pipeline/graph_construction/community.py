"""
G5 社区检测（架构 P7-G5 · J14 · 单元 2.6）。

Leiden 算法对实体-关系图分社区（python-igraph 离线计算），
构建层级社区树（多分辨率扫描 → 粗粒度为父、细粒度为子）。

更新策略（J14）：增量更新时仅重算受影响社区；变更实体占比 > 20%
触发全量重算。社区摘要与存储见 summarizer.py（分层 LLM 摘要 →
Neo4j (:Community) + Qdrant source=global）。
"""

# --- 标准库 ---
import logging

# --- 本地模块 ---
from app.core.models import CommunityRecord

logger = logging.getLogger(__name__)

# J14 全量重算触发阈值：变更实体占比 > 20%
RECOMPUTE_CHANGE_RATIO = 0.20


def should_recompute(member_count: int, changed_count: int) -> bool:
    """判断是否需要全量重算社区（J14）。

    Args:
        member_count: 当前社区体系成员总数。
        changed_count: 增量变更实体数。

    Returns:
        True 表示变更占比 > 20%，需全量重算。
    """
    if member_count <= 0:
        return changed_count > 0
    return changed_count / member_count > RECOMPUTE_CHANGE_RATIO


class LeidenDetector:
    """Leiden 层级社区检测器。

    Attributes:
        fine_resolution: 细粒度（叶子层）分辨率参数。
        coarse_resolution: 粗粒度（父层）分辨率参数。
    """

    def __init__(
        self,
        fine_resolution: float = 1.0,
        coarse_resolution: float = 0.4,
    ) -> None:
        """初始化检测器。

        Args:
            fine_resolution: 细粒度分辨率（越大社区越多越小）。
            coarse_resolution: 粗粒度分辨率。
        """
        self.fine_resolution = fine_resolution
        self.coarse_resolution = coarse_resolution

    def detect(
        self,
        nodes: list[str],
        edges: list[tuple[str, str]],
        community_prefix: str = "community",
    ) -> list[CommunityRecord]:
        """对实体-关系图执行层级社区检测。

        Args:
            nodes: 实体 canonical_name 列表。
            edges: 无向边列表 (head, tail)。
            community_prefix: 社区 ID 前缀。

        Returns:
            CommunityRecord 列表（叶子 level=0，父层 level=1，
            父子的 parent_id 链接完整）。
        """
        # 延迟导入：未安装 pipeline 可选组时给出明确错误
        try:
            import igraph as ig  # type: ignore[import-untyped]
            import leidenalg  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "社区检测依赖未安装（pyproject pipeline 可选组：igraph/leidenalg）"
            ) from exc

        if not nodes:
            return []

        index = {name: i for i, name in enumerate(nodes)}
        graph = ig.Graph(n=len(nodes), directed=False)
        valid_edges = [
            (index[h], index[t]) for h, t in edges if h in index and t in index
        ]
        graph.add_edges(valid_edges)

        # 细粒度叶子社区
        fine_partition = leidenalg.find_partition(
            graph,
            leidenalg.RBConfigurationVertexPartition,
            resolution_parameter=self.fine_resolution,
        )
        fine_membership: list[int] = list(fine_partition.membership)

        records: list[CommunityRecord] = []
        fine_communities = self._group_by_membership(nodes, fine_membership)
        for cid, members in sorted(fine_communities.items()):
            records.append(
                CommunityRecord(
                    community_id=f"{community_prefix}-l0-{cid}",
                    level=0,
                    members=members,
                )
            )

        # 粗粒度父社区（仅当叶子社区 > 1 个时构建层级）
        if len(fine_communities) > 1:
            coarse_partition = leidenalg.find_partition(
                graph,
                leidenalg.RBConfigurationVertexPartition,
                resolution_parameter=self.coarse_resolution,
            )
            coarse_membership: list[int] = list(coarse_partition.membership)
            coarse_communities = self._group_by_membership(nodes, coarse_membership)
            for cid, members in sorted(coarse_communities.items()):
                parent_id = f"{community_prefix}-l1-{cid}"
                records.append(
                    CommunityRecord(
                        community_id=parent_id,
                        level=1,
                        members=members,
                    )
                )
                # 叶子社区按成员多数归属链接父社区
                member_set = set(members)
                for record in records:
                    if record.level != 0 or record.parent_id is not None:
                        continue
                    if any(m in member_set for m in record.members):
                        record.parent_id = parent_id

        logger.info(
            "社区检测完成：%d 节点 → %d 社区", len(nodes), len(records)
        )
        return records

    @staticmethod
    def _group_by_membership(
        nodes: list[str], membership: list[int]
    ) -> dict[int, list[str]]:
        """按 membership 向量分组节点。

        Args:
            nodes: 节点名列表（与 membership 同序）。
            membership: 社区编号向量。

        Returns:
            {社区编号: [成员名, ...]}。
        """
        groups: dict[int, list[str]] = {}
        for name, cid in zip(nodes, membership):
            groups.setdefault(cid, []).append(name)
        return groups
