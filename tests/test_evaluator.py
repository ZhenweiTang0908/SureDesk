"""
Unit tests for RAGEvaluator logic.
"""
from newcode.rag.chunking import Chunk
from newcode.rag.engine import HybridRetrievalEngine
from newcode.rag.evaluator import RAGEvaluator

def test_evaluator_metrics():
    engine = HybridRetrievalEngine()
    c1 = Chunk(chunk_id="c1", content="7天无理由退货运费买家承担", title_path="服务手册 > 7天无理由退货")
    c2 = Chunk(chunk_id="c2", content="常规订单48小时发货", title_path="服务手册 > 发货承诺时效")
    engine.add_chunks([c1, c2])

    evaluator = RAGEvaluator(engine)
    res = evaluator.evaluate_query(
        query_id="t1",
        query="7天退货运费谁出",
        expected_title="7天无理由退货",
        category="售后",
        k=2,
        mode="hybrid"
    )

    assert res.hit_at_k is True
    assert res.rank == 1
    assert res.reciprocal_rank == 1.0

