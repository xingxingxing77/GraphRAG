# 问题排查记录：no-memory 记忆层降级（langgraph BlockingError）

> **日期**: 2026-08-27 | **状态**: 已修复 | **严重度**: 高（多轮对话记忆失效）
> **关联提交**: b61a8e0 `fix(infra): 消除langgraph阻塞检测的os.getcwd误报`

## 1. 问题现象

Agent 面（langgraph-server）执行对话时，`load_memory` 节点稳定返回
`{"degraded_reasons": ["no-memory"]}`，导致工作记忆注入失效（多轮对话
指代失准），`generator` 节点同步报 `llm-fallback` 降级。业务面 `/ready`
全绿、独立脚本跑 `get_memory_stack` 完全正常，形成「现象只在 langgraph
进程内出现、单测/脚本无法复现」的假象。

## 2. 排查过程（关键步骤与结论）

排查按「可复现 → 定位异常 → 定位调用源 → 修复 → 验证」推进，每一步都
留下了可验证的证据链：

1. **独立复现失败**：`uv run python` 脚本里 `get_memory_stack()` + 
   `build_context()` 全部成功（`text_len=0`），排除 Redis/Qdrant/embedder
   本身的问题——这说明问题只在 langgraph 执行环境里出现。

2. **临时改 `load_memory.py` 返回值注入异常标记**（`LM_EXC_MARKER`），
   但 8001 端口的 stream 仍返回固定 `no-memory`。这揭示了一个**干扰因素**：
   8001 端口被一个「幽灵进程」占用（见 §4），所有请求被路由到旧进程，
   我的代码改动根本没被测试到。

3. **改用全新端口 8002** 启动 langgraph，避开幽灵进程后，`LM_EXC_MARKER`
   才暴露真实异常：`BlockingError: Blocking call to os.getcwd`——这是
   langgraph dev 的「阻塞调用检测」抛出的。

4. **追踪 `os.getcwd` 调用源**（monkeypatch `os.getcwd` + `traceback`）：
   确认调用来自 Python 标准库 `sysconfig._safe_realpath` / `tempfile` /
   `inspect`（依赖库在 async 节点内加载时间接触发），**不是**项目代码的
   `os.getcwd`。

5. **验证修复**：用 `--allow-blocking` 启动 langgraph，`load_memory` 返回
   `null`（正常），`no-memory` 消失。

## 3. 根因

langgraph dev 的「阻塞调用检测」会在 async 节点执行期间，拦截同步阻塞
调用并抛 `BlockingError`。`load_memory` 节点内，`get_settings()` 首次实例化
（经 `pydantic-settings` → `sysconfig._safe_realpath`）以及依赖库加载模型时
（`tempfile`/`inspect`），触发了标准库的 `os.getcwd()` 同步调用——这被
langgraph 误判为「阻塞调用」抛异常 → `load_memory` 的 except 兜底 →
`no-memory` 降级。

`os.getcwd()` 是标准库的合法轻量调用，并非真正的阻塞操作，属 langgraph
检测过于敏感导致的误报。

## 4. 修复方案

**主修复（必须）**：langgraph dev 启动时加 `--allow-blocking`（官方针对
此场景的 dev-only override）：

```bash
uv run langgraph dev --no-browser --allow-blocking --port 8001 --host 0.0.0.0
```

**配套优化（减少 getcwd 触发，已提交 b61a8e0）**：
- `app/core/config.py` 的 `env_file` 由相对路径 `.env` 改为基于
  `os.path.abspath(__file__)` 推导的绝对路径（`Path.resolve()` 在 Windows
  会走 `realpath → getcwd`，反而踩坑，不能用）。
- `get_settings()` 在模块导入期预热一次，把 `sysconfig` 首次 `os.getcwd`
  的同步调用移出 async 节点上下文。

## 5. 遗留问题（环境侧，非代码）

1. **8001 端口幽灵进程**：一个旧 langgraph 进程（PID 33332）占用 8001，
   它 `tasklist`/`ps` 均查不到、`taskkill` 报「没有找到进程」，但 netstat
   显示 LISTENING 且能响应请求（怀疑在 WSL/其他会话）。**需用户手动关闭
   或重启机器**；期间本项目 agent 面改用 **8002** 端口（前端
   `.env.local` 的 `VITE_AGENT_BASE`、`.env` 的 `LANGGRAPH_SERVER_URL` 均
   指向 8002）。
2. **deepseek key 仍为占位符**（`.env` 里 `sk-your-deepseek-key`），导致
   `llm-fallback`。需填入真实 key。

## 6. 问题排查通用模板（后续问题照此记录）

每个问题文档建议固定包含以下小节，便于追溯：

| 小节 | 内容 |
|------|------|
| 现象 | 稳定复现的输入/输出，及「只在 X 环境出现」的边界 |
| 排查过程 | 按「可复现 → 定位 → 验证」推进，每步留可验证证据（命令/日志/文件标记） |
| 根因 | 直接原因 + 为什么之前的假设不成立 |
| 修复方案 | 主修复 + 配套优化，附可复制的命令/代码 |
| 验证 | 修复后的关键证据（如 `load_memory: null`） |
| 遗留问题 | 环境侧未解决项，明确责任边界（代码 vs 环境） |

**排查经验沉淀**：
- 「现象只在某进程出现、单测无法复现」时，优先怀疑**进程架构差异**
  （多进程/多线程/端口路由），而不是业务代码。
- 端口被「幽灵进程」占用时，先用**全新端口**验证排除路由干扰，再定位真异常。
- 用「临时改返回值注入标记」+「monkeypatch 标准库 + traceback」是定位
  「异常被吞/被兜底」类问题的有效手段。
