"""契约门禁 sse_schema（09 §4）——占位登记。

断言来源：03 §3.3/§3.4 事件序列与载荷（即 07 S-01~S-04）。
依赖流式链路（单元 5.5 Generator 缓冲式流 + 10.3 langgraph-server 接入），
接线前的占位测试保证门禁文件齐备。
"""

# --- 第三方库 ---
import pytest


@pytest.mark.skip(reason="待单元 5.5/10.3 流式链路落地后接线（07 S-01~S-04）")
def test_standard_run_event_sequence() -> None:
    """S-01：metadata→updates 序列→values→end 全帧收齐。"""
    raise NotImplementedError


@pytest.mark.skip(reason="待单元 5.2/6.2 chitchat fast 档落地后接线")
def test_fast_tier_token_stream_frames() -> None:
    """S-02：fast 档出现 messages 逐 token 帧且无 self_correction updates。"""
    raise NotImplementedError
