# GraphRAG 后端镜像: 业务面(FastAPI) 与 Agent 面(langgraph-server) 共用
# 依赖分层缓存: 仅 requirements.txt 变更时才重建依赖层
FROM python:3.13-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app/ ./app/
COPY config/ ./config/
COPY langgraph.json ./

# 默认业务面; agent 服务在 compose 中覆盖 command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
