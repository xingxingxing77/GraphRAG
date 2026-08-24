#!/usr/bin/env python3
# scripts/agent_selfcheck.py
"""
Agent 收工自检脚本（09 §3）。

提 PR 前必跑，全绿方可提交：
  1. doc-lint（R1/R2 硬错误为 0）
  2. mypy --strict（核心模块）
  3. pytest 全量（含 tests/contract 契约门禁）
  4. 契约冒烟：OpenAPI 与 02 §3 端点对齐（由 tests/contract/openapi_vs_02 承担）

用法:
    python scripts/agent_selfcheck.py [--skip-mypy]
退出码:
    0 = 全绿；非 0 = 存在失败项（输出各项结果汇总）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

# mypy --strict 覆盖模块（随单元推进扩充；未实现骨架模块逐步纳入）
MYPY_TARGETS = [
    "app/core",
    "app/llm",
    "app/agent",
    "app/api/errors.py",
    "app/pipeline/config.py",
    "app/pipeline/ingestion",
    "app/pipeline/parsing",
    "app/pipeline/cleaning",
    "app/pipeline/chunking/markdown_splitter.py",
    "app/pipeline/chunking/recursive_splitter.py",
    "app/pipeline/chunking/context_preserver.py",
    "app/pipeline/chunking/strategy.py",
    "app/pipeline/enrichment/metadata_enricher.py",
    "app/pipeline/enrichment/semantic_enricher.py",
    "app/embedding/ollama_client.py",
    "app/embedding/flag_client.py",
    "app/embedding/service.py",
    "app/embedding/base.py",
    "app/pipeline/graph_construction/schema.py",
    "app/pipeline/graph_construction/entity_resolver.py",
    "app/pipeline/graph_construction/graph_writer.py",
    "app/pipeline/graph_construction/relation_extractor.py",
    "app/pipeline/graph_construction/community.py",
    "app/pipeline/graph_construction/summarizer.py",
    "app/db/neo4j_client.py",
    "app/db/qdrant_client.py",
    "app/db/es_client.py",
    "app/db/redis_client.py",
    "app/pipeline/indexing/vector_indexer.py",
    "app/pipeline/indexing/fulltext_indexer.py",
    "app/retrieval/base.py",
    "app/retrieval/dense_retriever.py",
    "app/retrieval/sparse_retriever.py",
    "app/retrieval/graph_retriever.py",
    "app/retrieval/global_retriever.py",
    "app/retrieval/fulltext_retriever.py",
    "app/retrieval/web_retriever.py",
    "app/retrieval/normalizer.py",
    "app/retrieval/fusion.py",
    "app/retrieval/deduplicator.py",
    "app/api/metrics.py",
    "app/api/endpoints/metrics.py",
    "app/api/endpoints/debug.py",
    "app/reranking/base.py",
    "app/reranking/reranker.py",
    "app/reranking/scoring.py",
    "app/reranking/context_compressor.py",
]


def run_step(name: str, cmd: list[str]) -> bool:
    """执行一个自检步骤并打印结果。

    Args:
        name: 步骤名。
        cmd: 命令参数列表。

    Returns:
        True 表示通过。
    """
    print(f"\n== {name} ==")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-5:]
    for ln in tail:
        print(f"   {ln}")
    ok = proc.returncode == 0
    print(f"   [{'ok' if ok else 'FAIL'}] {name}")
    return ok


def main() -> int:
    """命令行入口：顺序执行全部自检项。"""
    parser = argparse.ArgumentParser(description="Agent 收工自检（09 §3）")
    parser.add_argument("--skip-mypy", action="store_true", help="跳过 mypy 步骤")
    args = parser.parse_args()

    results: list[tuple[str, bool]] = []

    # 1. doc-lint（含 --frontend rag-web 的 R4/R7/R8 校验）
    results.append(
        (
            "doc-lint",
            run_step(
                "doc-lint",
                [PYTHON, "scripts/doc_consistency_lint.py", "--frontend", "rag-web"],
            ),
        )
    )

    # 2. mypy --strict
    if not args.skip_mypy:
        results.append(
            (
                "mypy --strict",
                run_step(
                    "mypy --strict",
                    [PYTHON, "-m", "mypy", "--strict", "--ignore-missing-imports", *MYPY_TARGETS],
                ),
            )
        )

    # 3. pytest 全量（含契约门禁）
    results.append(
        ("pytest", run_step("pytest 全量", [PYTHON, "-m", "pytest", "tests", "-q"]))
    )

    # 汇总
    print("\n== 收工自检汇总（09 §3）==")
    failed = [name for name, ok in results if not ok]
    for name, ok in results:
        print(f"   [{'x' if ok else ' '}] {name}")
    if failed:
        print(f"\n[FAIL] 未通过项: {failed}")
        return 1
    print("\n[ok] 全部通过，可提 PR（记得 PR 描述带子阶段编号与决策引用，AGENT.md §8）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
