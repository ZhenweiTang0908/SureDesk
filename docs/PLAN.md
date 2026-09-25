# SureDesk - Implementation Plan

> English | [简体中文](#suredesk-定策---实施计划)

## Requirement Coverage

| Requirement | Description | Task | Verification |
|---|---|---|---|
| **R1** | Access control & IDOR defense | Task 1, Task 5 | Cross-user query throws IDORForbiddenException & logs audit |
| **R2** | Context-aware rewrite & 9-intent recognition | Task 6 | 20-case test suite achieves >= 95% pronoun resolution |
| **R3** | 5 Convergent routing channels | Task 6, Task 7 | Simulated inputs correctly branch into the 5 target routes |
| **R4** | Hybrid retrieval RAG (Dense + BM25 + RRF + Rerank) | Task 3, Task 4 | Automated benchmark evaluator outputs Recall@5 & MRR report |
| **R5** | Pre-generation confidence gate | Task 8, Task 9 | Unverified queries trigger polite rejection & ingest into pool |
| **R6** | Dual-layer conversation memory | Task 8 | Retains near messages; compresses far turns into entity summary |
| **R7** | Secure Function Calling with MCP support | Task 5, Task 7 | Pydantic validation, timeouts, and MCP tool execution |
| **R8** | LangGraph deterministic refund state machine | Task 7 | Handles missing order ID suspension, resume, and 7-day rule |
| **R9** | SSE real-time streaming & Web UI | Task 2, Task 10 | Typewriter streaming response with citation cards |
| **R10** | End-to-end tracing and observability | Task 1, Task 9 | Records Trace ID, stage latency, tokens, and evidence snapshots |
| **R11** | Self-iterating data flywheel loop | Task 9, Task 10 | Rejection -> Review -> Ingestion -> Instant hit verified |
| **R12** | Offline intent classifier pipeline | Task 11 | Standalone training pipeline outputs confusion matrix & F1 |

---

## Task 1: Project Scaffold, Domain Models & Secured Storage
- **Task Goal**: Establish asynchronous database architecture, configuration management, and domain models for User, Order, Logistics, ProblemPool, and AuditLog with row-level security indexes.
- **Relevant Spec Requirements**: R1, R10
- **Expected Files**: `pyproject.toml`, `newcode/core/config.py`, `newcode/core/database.py`, `newcode/models/domain.py`, `scripts/seed_data.py`, `tests/test_models.py`
- **Verification**: `pytest tests/test_models.py` passes.

## Task 2: LLM Client Wrapper, Structured Output & SSE Streaming
- **Task Goal**: Encapsulate unified AsyncOpenAI client, structured parsing with Pydantic validation, and FastAPI SSE streaming router.
- **Relevant Spec Requirements**: R9
- **Expected Files**: `newcode/core/llm.py`, `newcode/schemas/common.py`, `newcode/api/routes/stream.py`, `newcode/main.py`, `tests/test_llm_stream.py`
- **Verification**: `pytest tests/test_llm_stream.py` passes.

## Task 3: Hierarchical Chunking & Hybrid Retrieval Engine
- **Task Goal**: Implement hierarchical Markdown chunking, Dense vector similarity, BM25Okapi sparse recall, RRF fusion, and Cross-Encoder reranker.
- **Relevant Spec Requirements**: R4
- **Expected Files**: `newcode/rag/chunking.py`, `newcode/rag/dense.py`, `newcode/rag/bm25.py`, `newcode/rag/fusion.py`, `newcode/rag/reranker.py`, `newcode/rag/engine.py`, `tests/test_retrieval.py`
- **Verification**: `pytest tests/test_retrieval.py` passes.

## Task 4: RAG Benchmark Dataset & Automated Evaluator
- **Task Goal**: Construct benchmark QA dataset and automated evaluator calculating Recall@5 and MRR metrics comparing Dense, BM25, and Hybrid modes.
- **Relevant Spec Requirements**: R4
- **Expected Files**: `tests/benchmarks/qa_dataset.json`, `knowledge_base/ecommerce_faq.md`, `newcode/rag/evaluator.py`, `scripts/evaluate_rag.py`, `tests/test_evaluator.py`
- **Verification**: `python scripts/evaluate_rag.py` & `pytest tests/test_evaluator.py` pass.

## Task 5: Business Tools, IDOR Protection & MCP Integration Layer
- **Task Goal**: Implement order and shipment tools with mandatory `SecurityContext` validation, 100% IDOR attack defense, and Model Context Protocol adapter.
- **Relevant Spec Requirements**: R1, R7
- **Expected Files**: `newcode/tools/base.py`, `newcode/tools/order_tools.py`, `newcode/tools/logistics_tools.py`, `newcode/tools/mcp_adapter.py`, `newcode/tools/registry.py`, `tests/test_tools.py`
- **Verification**: `pytest tests/test_tools.py` passes with 100% IDOR interception rate.

## Task 6: Context-Aware Query Rewriter & 9-Intent 5-Route Classifier
- **Task Goal**: Implement pronoun resolution across multi-turn context and deterministic routing into 5 execution targets.
- **Relevant Spec Requirements**: R2, R3
- **Expected Files**: `newcode/schemas/intent.py`, `newcode/services/router.py`, `tests/test_intent_router.py`
- **Verification**: `pytest tests/test_intent_router.py` passes with 100% accuracy.

## Task 7: LangGraph Deterministic State Machine & ReAct Agent Loop
- **Task Goal**: Orchestrate hybrid state machine: refund workflow supporting suspension on missing order ID, human-in-the-loop resumption, and 7-day rule enforcement.
- **Relevant Spec Requirements**: R3, R7, R8
- **Expected Files**: `newcode/workflow/state.py`, `newcode/workflow/nodes/refund_workflow.py`, `newcode/workflow/nodes/agent_node.py`, `newcode/workflow/graph.py`, `tests/test_workflow.py`
- **Verification**: `pytest tests/test_workflow.py` passes.

## Task 8: Pre-Generation Confidence Gate & Dual-Layer Memory Management
- **Task Goal**: Implement threshold-based confidence gate before generation to prevent hallucinations, paired with dual-layer near/far conversation memory.
- **Relevant Spec Requirements**: R5, R6
- **Expected Files**: `newcode/guard/confidence_gate.py`, `newcode/services/memory.py`, `tests/test_guard_memory.py`
- **Verification**: `pytest tests/test_guard_memory.py` passes.

## Task 9: Low-Confidence Problem Pool & End-to-End Tracing Observability
- **Task Goal**: Ingest unverified or negative feedback queries via 3 triggers, perform similarity deduplication, and record request-level tracing spans.
- **Relevant Spec Requirements**: R5, R10, R11
- **Expected Files**: `newcode/services/problem_pool.py`, `newcode/core/tracing.py`, `newcode/api/routes/feedback.py`, `tests/test_problem_pool_trace.py`
- **Verification**: `pytest tests/test_problem_pool_trace.py` passes.

## Task 10: Chat UI, Operator Review Workbench & Data Flywheel Closed-Loop
- **Task Goal**: Build customer chat interface with typewriter streaming and citation pill tags, plus operator review workbench for answer adoption and knowledge synchronization.
- **Relevant Spec Requirements**: R9, R11
- **Expected Files**: `newcode/api/routes/workbench.py`, `newcode/ui/static/chat.html`, `newcode/ui/static/workbench.html`, `tests/test_e2e_flywheel.py`
- **Verification**: `pytest tests/test_e2e_flywheel.py` passes closed-loop test.

## Task 11: Offline Intent Classification Model & Fine-Tuning Pipeline
- **Task Goal**: Implement standalone dataset preparation, feature extraction, linear model training, and confusion matrix evaluation.
- **Relevant Spec Requirements**: R12
- **Expected Files**: `newcode/offline/dataset_prep.py`, `newcode/offline/train.py`, `newcode/offline/evaluate.py`, `tests/test_offline_pipeline.py`
- **Verification**: `pytest tests/test_offline_pipeline.py` passes.

## Task 12: End-to-End System Verification & Acceptance Run
- **Task Goal**: Verify all 6 acceptance criteria and requirements R1-R12 across the unified system.
- **Relevant Spec Requirements**: R1 ~ R12, Acceptance Criteria 1 ~ 6
- **Expected Files**: `tests/test_full_acceptance.py`, `docs/ACCEPTANCE_REPORT.md`
- **Verification**: `pytest tests/test_full_acceptance.py` passes (6/6).

---
---

# SureDesk (定策) - 实施计划

## 需求覆盖对照表

| 需求编号 | 需求描述 | 对应 Task | 验证方式 |
|---|---|---|---|
| **R1** | 接入鉴权与用户数据隔离 (IDOR 防御) | Task 1, Task 5 | 跨用户查询订单/物流时抛出 Forbidden 异常并记录审计日志 |
| **R2** | 指代消解与意图识别 Query 改写 | Task 6 | 运行测试集，20 组多轮半截话补全准确率 ≥ 95% |
| **R3** | 路由与五大分流出口 | Task 6, Task 7 | 单元测试模拟 9 类意图输入，准确分流至 5 个预设出口 |
| **R4** | 全链路混合检索 RAG (Dense + BM25 + RRF + Rerank) | Task 3, Task 4 | 运行评估脚本，基准数据集上输出 Recall@5 与 MRR 对比报告 |
| **R5** | 置信度闸门与前置防御 (无证据拒答进池) | Task 8, Task 9 | 构造知识库外冷门问题，100% 触发优雅拒答并入库低置信度池 |
| **R6** | 双层会话上下文管理 (近端精确 + 远端摘要压缩) | Task 8 | 模拟 10 轮对话，验证近端保留精确轮次，远端压缩为结构化实体摘要 |
| **R7** | Function Calling 与工具系统 (MCP 支持) | Task 5, Task 7 | 工具入参 Pydantic 校验、超时重试与 mock MCP 协议调用正常 |
| **R8** | LangGraph 编排与确定性退款状态机 | Task 7 | 测试退款流程缺失单号时的中断挂起、用户补全后的状态恢复与终态扭转 |
| **R9** | 流式响应与现代化 Web 对话界面 | Task 2, Task 10 | 前端通过 SSE 接收逐字流式打字效果与引用来源展示 |
| **R10** | 全链路可观测性 Tracing (Langfuse 契约) | Task 1, Task 9 | 请求完成时记录 Trace ID、各节点耗时、Token 用量与证据快照 |
| **R11** | 数据飞轮闭环与运营审核工作台 | Task 9, Task 10 | 触发拒答 -> 运营后台审核补写标准答案 -> 一键入库 -> 再次提问命中秒答 |
| **R12** | 轻量离线主题分类模型与微调评估管线 | Task 11 | 运行训练/评估独立脚本，输出混淆矩阵与 F1-score 指标 |

— NiuNiu Tang
