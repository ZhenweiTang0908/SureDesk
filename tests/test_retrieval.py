"""
Unit tests for Hierarchical Chunking, BM25, Dense, RRF Fusion, and HybridRetrievalEngine.
"""
import pytest
from newcode.rag.chunking import HierarchicalMarkdownChunker, Chunk
from newcode.rag.bm25 import BM25Retriever, tokenize
from newcode.rag.dense import DenseRetriever, simple_semantic_vector
from newcode.rag.fusion import rrf_fusion
from newcode.rag.reranker import CrossEncoderReranker
from newcode.rag.engine import HybridRetrievalEngine

SAMPLE_POLICY = """# 商城服务政策指南

## 售后服务政策

### 7天无理由退货
自商品签收之日起7日内（含7日），在保证商品完好、包装齐全且不影响二次销售的前提下，支持无理由退货。
退货运费需由买家自行承担，除非商品存在质量缺陷或与描述严重不符。

### 退款到账时效
退款申请审核通过后，款项将在1至3个工作日内原路退回至支付账户。银行卡快捷支付通常需3至5个工作日。

| 支付渠道 | 预计退款时效 | 备注 |
| :--- | :--- | :--- |
| 微信支付 | 1-2个工作日 | 零钱实时到账 |
| 支付宝 | 1-2个工作日 | 余额实时到账 |
| 银行卡 | 3-5个工作日 | 视各发卡行处理速度而定 |

## 物流配送规则

### 发货承诺时效
常规现货订单在买家付款成功后48小时内完成打包并发货。大促活动期间承诺72小时内发出。
顺丰速运支持全国次日达或隔日达。

### 物流轨迹异常
若物流信息超过48小时未更新，系统将自动发起催件通知并派发物流专员协助排查。
"""


def test_hierarchical_chunking():
    chunker = HierarchicalMarkdownChunker(target_chunk_size=300)
    chunks = chunker.chunk_document(SAMPLE_POLICY, source_doc="政策指南")

    assert len(chunks) >= 4
    # Check title hierarchy preservation
    refund_chunk = next(c for c in chunks if "7日内" in c.content)
    assert refund_chunk.title_path == "商城服务政策指南 > 售后服务政策 > 7天无理由退货"
    assert refund_chunk.is_table is False

    # Check table preservation
    table_chunk = next(c for c in chunks if c.is_table)
    assert "预计退款时效" in table_chunk.content
    assert table_chunk.title_path == "商城服务政策指南 > 售后服务政策 > 退款到账时效"


def test_tokenize():
    tokens = tokenize("我想退货，7天退款什么时候到账？")
    assert "退" in tokens or "退货" in tokens
    assert "7" in tokens or "7天" in tokens


def test_bm25_retriever():
    chunker = HierarchicalMarkdownChunker()
    chunks = chunker.chunk_document(SAMPLE_POLICY)
    retriever = BM25Retriever(chunks)

    results = retriever.retrieve("7天无理由退货条件", top_k=3)
    assert len(results) > 0
    top_chunk_id, score = results[0]
    top_chunk = retriever.chunk_map[top_chunk_id]
    assert "7天无理由退货" in top_chunk.title_path
    assert score > 0.0


def test_dense_retriever():
    chunker = HierarchicalMarkdownChunker()
    chunks = chunker.chunk_document(SAMPLE_POLICY)
    retriever = DenseRetriever(chunks)

    results = retriever.retrieve("物流发货需要几天送达？", top_k=3)
    assert len(results) > 0
    top_chunk_id, score = results[0]
    top_chunk = retriever.chunk_map[top_chunk_id]
    assert "物流配送规则" in top_chunk.title_path or "发货承诺" in top_chunk.content


def test_rrf_fusion():
    list1 = [("doc1", 0.9), ("doc2", 0.8), ("doc3", 0.7)]
    list2 = [("doc2", 15.0), ("doc1", 12.0), ("doc4", 10.0)]

    fused = rrf_fusion([list1, list2], k=60)
    # doc1: 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.01639 + 0.01613 = 0.03252
    # doc2: 1/(60+2) + 1/(60+1) = 0.03252
    doc_ids = [d for d, _ in fused]
    assert doc_ids[0] in ["doc1", "doc2"]
    assert doc_ids[1] in ["doc1", "doc2"]
    assert "doc4" in doc_ids


def test_cross_encoder_reranker():
    reranker = CrossEncoderReranker()
    c1 = Chunk(chunk_id="1", content="支持7天无理由退换货", title_path="售后政策")
    c2 = Chunk(chunk_id="2", content="顺丰速运48小时发货", title_path="物流规则")

    ranked = reranker.rerank("退换货政策要求", [c1, c2], top_k=2)
    assert ranked[0][0].chunk_id == "1"
    assert ranked[0][1] > ranked[1][1]


def test_hybrid_retrieval_engine():
    engine = HybridRetrievalEngine()
    engine.add_markdown_document(SAMPLE_POLICY, source_doc="商城政策")

    # Query 1: return policy
    results1 = engine.retrieve("我想申请7天退货，运费谁出？", top_k=3)
    assert len(results1) > 0
    assert "7天无理由退货" in results1[0].chunk.title_path
    assert results1[0].rerank_score > 0.0

    # Query 2: logistics table
    results2 = engine.retrieve("银行卡退款到账需要多少天？", top_k=3)
    assert len(results2) > 0
    matched_content = " ".join([r.chunk.content for r in results2])
    assert "银行卡" in matched_content

