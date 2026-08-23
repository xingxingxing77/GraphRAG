#!/usr/bin/env python3
# scripts/export_openapi.py
"""导出 FastAPI OpenAPI schema 到 rag-web/openapi.json。

用途：`pnpm gen:api` 的离线替代（无需启动服务）——
    python scripts/export_openapi.py
    cd rag-web && npx openapi-typescript openapi.json -o src/types/api.ts

契约变更流程见 02 机器契约声明（J25）：生成物禁手改，
变更后端契约须重新生成并提交 types/api.ts。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import app  # noqa: E402  # 依赖上方 sys.path 注入


def main() -> int:
    """导出入口。"""
    out = REPO_ROOT / "rag-web" / "openapi.json"
    out.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ok] OpenAPI schema 已导出: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
