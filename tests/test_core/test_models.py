"""契约模型测试（单元 0.1/0.2 S3，07 §5）。

断言 app/core/models.py 全部契约模型的 pydantic 序列化往返、
字段默认值与字面量枚举约束。
"""

# --- 标准库 ---
from datetime import datetime, timezone

# --- 第三方库 ---
import pytest
from pydantic import ValidationError

# --- 本地模块 ---
from app.core.models import (
    ChatRequest,
    Chunk,
    Citation,
    CleanedDocument,
    EnrichedChunk,
    EntityMention,
    ErrorBody,
    IntentType,
    LatencyTier,
    Paged,
    ParsedDocument,
    PlanStep,
    PositionMeta,
    RawDocument,
    ReflectFeedback,
    RelationTriple,
    RetrievalResult,
    SourceKind,
    StructureNode,
    TokenUsage,
)


def _make_raw_document() -> RawDocument:
    return RawDocument(
        doc_id="doc-001",
        source_path="menu/HowToCook/dishes/aquatic/清蒸鲈鱼/清蒸鲈鱼.md",
        raw_bytes="清蒸鲈鱼".encode("utf-8"),
        mime_type="text/markdown",
        timestamp=datetime(2026, 8, 23, tzinfo=timezone.utc),
        content_hash="sha256:deadbeef",
    )


class TestDocumentFamily:
    """Document 模型族（架构 §3.1）往返与约束。"""

    def test_raw_document_roundtrip(self) -> None:
        doc = _make_raw_document()
        restored = RawDocument.model_validate(doc.model_dump())
        assert restored == doc
        assert restored.schema_version == "1"

    def test_parsed_document_defaults(self) -> None:
        doc = ParsedDocument(doc_id="doc-001", text="正文")
        assert doc.structure_tree == []
        assert doc.format_meta == {}
        assert doc.schema_version == "1"

    def test_structure_tree_roundtrip(self) -> None:
        doc = ParsedDocument(
            doc_id="doc-001",
            text="正文",
            structure_tree=[StructureNode(level=1, title="清蒸鲈鱼", start_offset=0)],
        )
        restored = ParsedDocument.model_validate(doc.model_dump())
        assert restored.structure_tree[0].title == "清蒸鲈鱼"

    def test_cleaned_document_quality_bounds(self) -> None:
        doc = CleanedDocument(doc_id="doc-001", text="正文", quality_score=0.9)
        assert doc.quality_score == 0.9
        with pytest.raises(ValidationError):
            CleanedDocument(doc_id="doc-001", text="正文", quality_score=1.5)

    def test_chunk_roundtrip(self) -> None:
        chunk = Chunk(
            chunk_id="doc-001-0",
            doc_id="doc-001",
            seq=0,
            content="大火蒸 8 分钟",
            title_path=["清蒸鲈鱼", "操作步骤", "蒸制"],
            position=PositionMeta(start_char=0, end_char=8),
        )
        restored = Chunk.model_validate(chunk.model_dump())
        assert restored.title_path == ["清蒸鲈鱼", "操作步骤", "蒸制"]
        assert restored.position.end_char == 8

    def test_enriched_chunk_roundtrip(self) -> None:
        chunk = Chunk(
            chunk_id="doc-001-0",
            doc_id="doc-001",
            seq=0,
            content="内容",
            position=PositionMeta(start_char=0, end_char=2),
        )
        enriched = EnrichedChunk(
            chunk=chunk,
            keywords=["鲈鱼", "蒸制"],
            entities=[EntityMention(name="鲈鱼", type="Ingredient", span=[0, 2])],
            relations=[
                RelationTriple(
                    head="清蒸鲈鱼",
                    relation="REQUIRES",
                    tail="鲈鱼",
                    evidence_chunk_id="doc-001-0",
                )
            ],
        )
        restored = EnrichedChunk.model_validate(enriched.model_dump())
        assert restored.entities[0].normalized_to is None
        assert restored.summary is None
        assert restored.relations[0].head == "清蒸鲈鱼"


class TestRetrievalModels:
    """检索侧与编排模型（架构 §3.3）默认值与枚举。"""

    def test_retrieval_result_source_enum(self) -> None:
        result = RetrievalResult(
            result_id="dense:abc",
            content="内容",
            score=0.9,
            source="dense",
        )
        assert result.source == SourceKind.DENSE
        assert result.chunk_id is None
        assert result.doc_id is None
        assert result.metadata == {}

    def test_retrieval_result_rejects_unknown_source(self) -> None:
        with pytest.raises(ValidationError):
            RetrievalResult(
                result_id="x:1", content="内容", score=0.1, source="unknown"
            )

    def test_source_kind_six_members(self) -> None:
        assert {m.value for m in SourceKind} == {
            "dense",
            "sparse",
            "graph",
            "global",
            "fulltext",
            "web",
        }

    def test_citation_roundtrip(self) -> None:
        citation = Citation(marker=1, result_ids=["dense:abc"], quote="大火蒸 8 分钟")
        restored = Citation.model_validate(citation.model_dump())
        assert restored.marker == 1

    def test_token_usage_defaults(self) -> None:
        usage = TokenUsage(model="deepseek-chat")
        assert usage.prompt_tokens == 0
        assert usage.latency_ms == 0

    def test_plan_step_defaults(self) -> None:
        step = PlanStep(step_id="step-1", tool="dense", query="清蒸鲈鱼做法")
        assert step.depends_on == []
        assert step.status == "pending"

    def test_plan_step_direct_answer_literal(self) -> None:
        step = PlanStep(step_id="step-1", tool="direct_answer", query="你好")
        assert step.tool == "direct_answer"

    def test_plan_step_status_literal_constraint(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(step_id="step-1", tool="dense", query="q", status="invalid")

    def test_reflect_feedback_roundtrip(self) -> None:
        feedback = ReflectFeedback(
            sufficient=False,
            missing_aspects=["蒸制时间"],
            followup_queries=["清蒸鲈鱼需要蒸多久"],
        )
        restored = ReflectFeedback.model_validate(feedback.model_dump())
        assert restored.sufficient is False
        assert restored.followup_queries == ["清蒸鲈鱼需要蒸多久"]


class TestApiContracts:
    """API 契约模型（架构 §3.6 + 02 §5）。"""

    def test_chat_request_defaults(self) -> None:
        request = ChatRequest(query="清蒸鲈鱼怎么做？")
        assert request.latency_tier == "auto"
        assert request.model is None
        assert request.stream is True

    def test_chat_request_query_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ChatRequest(query="")
        with pytest.raises(ValidationError):
            ChatRequest(query="x" * 2001)

    def test_latency_tier_enum(self) -> None:
        assert [m.value for m in LatencyTier] == ["fast", "standard", "deep"]

    def test_intent_type_enum(self) -> None:
        assert {m.value for m in IntentType} == {
            "fact",
            "multi_hop",
            "comparison",
            "chitchat",
        }

    def test_paged_generic_roundtrip(self) -> None:
        paged = Paged[Citation](
            items=[Citation(marker=1, result_ids=["r_1"])],
            next_cursor="c_2",
        )
        restored = Paged[Citation].model_validate(paged.model_dump())
        assert restored.items[0].marker == 1
        assert restored.next_cursor == "c_2"

    def test_error_body_shape(self) -> None:
        body = ErrorBody(code="CHAT_400_EMPTY_QUERY", message="空查询")
        assert body.model_dump() == {
            "code": "CHAT_400_EMPTY_QUERY",
            "message": "空查询",
            "detail": None,
        }
