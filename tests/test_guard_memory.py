"""
Unit tests for Confidence Gate and Dual-Layer Memory Management.
"""
from newcode.rag.chunking import Chunk
from newcode.rag.engine import ScoredChunk
from newcode.guard.confidence_gate import ConfidenceGate
from newcode.services.memory import DualLayerMemoryManager


def test_confidence_gate_rejection_empty_evidence():
    gate = ConfidenceGate(score_threshold=0.55)
    decision = gate.evaluate("火星基地的收件地址能包邮送达吗？", [])
    assert decision.passed is False
    assert decision.confidence_score == 0.0
    assert "暂未收录" in decision.rejection_answer


def test_confidence_gate_rejection_low_score():
    gate = ConfidenceGate(score_threshold=0.55)
    c = Chunk(chunk_id="1", content="常规订单48小时发货", title_path="发货时效")
    sc = ScoredChunk(
        chunk=c,
        score=0.32,  # Below 0.55 threshold
        rrf_score=0.01,
        dense_score=0.3,
        bm25_score=1.0,
        rerank_score=0.32,
    )
    decision = gate.evaluate("火星基地的收件地址能包邮送达吗？", [sc])
    assert decision.passed is False
    assert "未能找到完全符合您提问的官方政策依据" in decision.rejection_answer


def test_confidence_gate_passed():
    gate = ConfidenceGate(score_threshold=0.55)
    c = Chunk(chunk_id="1", content="支持7天无理由退货", title_path="售后政策")
    sc = ScoredChunk(
        chunk=c,
        score=0.88,
        rrf_score=0.03,
        dense_score=0.85,
        bm25_score=12.0,
        rerank_score=0.88,
    )
    decision = gate.evaluate("支持7天无理由退货吗？", [sc])
    assert decision.passed is True
    assert decision.rejection_answer is None


def test_dual_layer_memory_short_conversation():
    mem = DualLayerMemoryManager(near_window_turns=3)
    history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "您好！"},
        {"role": "user", "content": "我想咨询蓝牙音箱"},
        {"role": "assistant", "content": "蓝牙音箱音质非常好"},
    ]
    ctx = mem.process_messages(history)
    assert len(ctx.near_messages) == 4
    assert ctx.summary == ""
    assert "蓝牙音箱" in ctx.entities["products"]


def test_dual_layer_memory_long_conversation_compression():
    mem = DualLayerMemoryManager(near_window_turns=2)  # Window = 4 messages
    long_history = [
        {"role": "user", "content": "我上一笔订单是 ord_8888，购买了无线耳机"},
        {"role": "assistant", "content": "已查到您的无线耳机订单"},
        {"role": "user", "content": "我想问下退款政策"},
        {"role": "assistant", "content": "支持7天无理由退货"},
        {"role": "user", "content": "发货是顺丰吗"},
        {"role": "assistant", "content": "是的，顺丰速运"},
        {"role": "user", "content": "到北京几天"},
        {"role": "assistant", "content": "预计隔天到达"},
    ]
    ctx = mem.process_messages(long_history)
    # Near messages should be last 4 messages
    assert len(ctx.near_messages) == 4
    assert ctx.near_messages[0]["content"] == "发货是顺丰吗"

    # Far messages should be compressed into summary
    assert "[历史压缩摘要]" in ctx.summary
    assert "ord_8888" in ctx.summary or "无线耳机" in ctx.summary

    # Entity preservation across whole conversation
    assert "ord_8888" in ctx.entities["order_ids"]
    assert "无线耳机" in ctx.entities["products"]

