# 电商 AI 智能客服系统（MewHelp）实施计划 (Implementation Plan)

## Requirement Coverage

| Requirement | Description | Task | Verification |
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

---

## Task 1: Project Scaffold, Domain Models & Secured Storage

### Task Goal
搭建项目核心目录骨架、配置管理体系，并基于 SQLAlchemy (aiosqlite/SQLite) 实现包含 User、Order、Logistics、Session、Message、ProblemPool 和 AuditLog 的持久化数据模型与初始种子数据。

### Relevant Spec Requirements
- **R1**（接入与鉴权隔离基础）
- **R10**（审计与日志基础）

### Expected Files / Components
- `pyproject.toml`: 项目依赖管理（FastAPI、SQLAlchemy、aiosqlite、pydantic 等）
- `mewhelp/core/config.py`: 环境变量与全局配置（基于 pydantic-settings）
- `mewhelp/core/database.py`: 异步 DB 引擎与 Session 依赖注入
- `mewhelp/models/base.py`, `mewhelp/models/domain.py`: ORM 实体定义（User, Order, Logistics, ChatSession, ChatMessage, ProblemPool, AuditLog）
- `scripts/seed_data.py`: 初始化测试种子数据（典型用户、多种状态订单与物流轨迹、初始 FAQ 文档）
- `tests/test_models.py`: 数据模型 CRUD 与多租户/用户过滤验证

### Dependencies
None

### Implementation Scope
1. 规范化 Python 异步工程结构，配置 SQLite/aiosqlite 异步引擎。
2. 建立符合业务场景的数据库表，在 Order/Logistics 等业务表上强约束 `user_id` 外键关联与复合索引。
3. 编写种子数据生成脚本，预置 3 个典型买家测试账号、5 笔不同状态（已支付未发货、运输中、已签收超过7天、已退款）订单。

### Verification
- 运行 `pytest tests/test_models.py`，确认所有表异步建表成功，CRUD 操作无阻塞，查询条件严格隔离。

---

## Task 2: LLM Client Wrapper, Structured Parsing & SSE Streaming

### Task Goal
封装统一的 LLM 客户端层（兼容 OpenAI 协议与主流 API），实现健壮的结构化输出解析器，并基于 FastAPI 搭建可逐字推送的 SSE (Server-Sent Events) 端点。

### Relevant Spec Requirements
- **R9**（流式响应基础）

### Expected Files / Components
- `mewhelp/core/llm.py`: 统一的大模型客户端封装（支持 ChatCompletion、Streaming、JSON Schema 约束）
- `mewhelp/schemas/common.py`: 统一请求/响应体结构与流式 Event 载荷定义
- `mewhelp/api/routes/stream.py`: FastAPI SSE 流式路由
- `mewhelp/main.py`: FastAPI 顶层应用入口
- `tests/test_llm_stream.py`: 流式输出与异常兜底测试

### Dependencies
- Task 1

### Implementation Scope
1. 抽象 LLM 接口，封装重试、超时、流式 Token 回调与 Usage 统计。
2. 实现基于 Pydantic 的安全结构化输出提取器（带 Markdown 代码块自动清理与容错重试）。
3. 构建 `/api/chat/stream` 端点，支持输出思考过程（thought）与正文回答（answer）的分片事件推送。

### Verification
- 编写测试用例验证客户端接收 SSE 流，断言首包响应时间、分片拼装完整性以及中断情况下的连接清理。

---

## Task 3: Hierarchical Chunking & Hybrid Retrieval Engine (Dense + BM25 + RRF + Cross-Encoder Rerank)

### Task Goal
实现面向电商知识库的层次化切分器（保留 Markdown 标题层级与表格完整性），构建 Dense 向量与 BM25 稀疏检索的双路召回，并运用 RRF 算法与 Cross-Encoder Reranker 完成精准重排。

### Relevant Spec Requirements
- **R4**（全链路混合检索 RAG 与重排）

### Expected Files / Components
- `mewhelp/rag/chunking.py`: Markdown 结构感知与层级元数据切分器
- `mewhelp/rag/dense.py`: 向量化嵌入与相似度检索
- `mewhelp/rag/bm25.py`: 关键词稀疏检索器
- `mewhelp/rag/fusion.py`: RRF (Reciprocal Rank Fusion) 倒数排名融合算法实现
- `mewhelp/rag/reranker.py`: Cross-Encoder 精排打分器封装（支持轻量本地模型或轻量推理）
- `mewhelp/rag/engine.py`: 统一混合检索外观接口 (HybridRetrievalEngine)
- `tests/test_retrieval.py`: 切分与各路召回、融合排序的单测

### Dependencies
- Task 1

### Implementation Scope
1. 实现支持标题上下文继承的文档分块器，确保切片元数据带有所属层级路径（如 `售前规则 > 优惠券使用`）与表格标记。
2. 实现内存/本地轻量向量检索与 BM25 索引。
3. 实现标准 RRF 公式：`Score(d) = sum(1 / (k + rank_i(d)))`，融合双路候选。
4. 接入精排 Reranker，对 Top-N 候选进行语义相关度交叉打分，截取 Top-K 证据块。

### Verification
- 运行 `pytest tests/test_retrieval.py`，对比输入测试 Query 时单路 Dense、单路 BM25 与 RRF+Rerank 的排序结果，验证表格未被截断且元数据层级完整。

---

## Task 4: RAG Benchmark Dataset & Automated Evaluator (Recall@5 & MRR)

### Task Goal
构建包含真实电商场景多桶分类的评测基准数据集（含商品规则、售后政策、物流时效、冷门边界问题），并编写自动化评估器计算 Recall@5 与 MRR 指标，量化验证混合检索收益。

### Relevant Spec Requirements
- **R4**（检索质量自动化评估）

### Expected Files / Components
- `tests/benchmarks/qa_dataset.json`: 包含 query、ground_truth_chunk_ids、category 的评测集
- `mewhelp/rag/evaluator.py`: Recall@K 与 MRR (Mean Reciprocal Rank) 评测核心类
- `scripts/evaluate_rag.py`: 独立评估运行脚本，输出各检索模式详细指标对照表
- `tests/test_evaluator.py`: 评测逻辑单测

### Dependencies
- Task 3

### Implementation Scope
1. 编写包含不少于 30 个典型 Query 的基准评测数据集，涵盖直接匹配、同义转述、跨段落推理与边界场景。
2. 实现自动化评测脚本，对比运行三种检索策略：
   - 纯 Dense 向量召回
   - 纯 BM25 稀疏召回
   - 混合检索 + RRF + Cross-Encoder Rerank
3. 自动生成包含各模式对比的 Markdown 评估报告。

### Verification
- 运行 `python scripts/evaluate_rag.py`，成功输出基准评测报告，混合检索模式的 Recall@5 与 MRR 较单路召回呈现明显提升。

---

## Task 5: Business Tools, IDOR Protection & MCP Integration Layer

### Task Goal
实现电商核心业务工具库（订单详情查询、物流轨迹追踪、商品信息咨询），嵌入强制性 `user_id` 身份所有权隔离校验以杜绝越权访问（IDOR），并提供支持标准 MCP 协议外部工具的接入适配层。

### Relevant Spec Requirements
- **R1**（接入与鉴权隔离）
- **R7**（Function Calling 与工具系统）

### Expected Files / Components
- `mewhelp/tools/base.py`: 统一 Tool 基类与安全上下文定义 (SecurityContext)
- `mewhelp/tools/order_tools.py`: 订单查询与订单状态判断工具
- `mewhelp/tools/logistics_tools.py`: 物流轨迹与签收时效查询工具
- `mewhelp/tools/mcp_adapter.py`: 标准 MCP (Model Context Protocol) 外部服务适配器
- `mewhelp/tools/registry.py`: 工具注册表与执行调度器（含超时、重试与审计日志记录）
- `tests/test_tools.py`: 业务工具功能测试与非法越权查单攻击防御测试

### Dependencies
- Task 1

### Implementation Scope
1. 定义带有强类型 Pydantic Schema 的工具注册体系，每个工具调用必须注入当前请求的 `SecurityContext(user_id=...)`。
2. 在数据库查询层面施加行级限制（如 `WHERE order_id = :oid AND user_id = :uid`），一旦用户试图通过工具访问非本人订单，直接抛出越权拦截错误并在 AuditLog 表写入安全违规审计。
3. 实现对 MCP 工具协议的标准化包装与异常处理机制。

### Verification
- 运行 `pytest tests/test_tools.py`：
  - 用户 A 查询本人订单物流正常返回详情。
  - 用户 A 传入用户 B 的有效 `order_id`，100% 触发越权拒绝并产生一条审计日志。

---

## Task 6: Context-Aware Query Rewriter & 9-Intent 5-Route Classifier

### Task Goal
构建结合多轮历史的指代消解与语义补全模块，精准识别 9 类细分意图（商品咨询、售前规则、订单查询、物流进度、退款申请、投诉/转人工、闲聊、敏感违规、未决追问），并将意图精准映射至 5 大执行分流出口。

### Relevant Spec Requirements
- **R2**（指代消解与意图识别 Query 改写）
- **R3**（路由与五大分流出口）

### Expected Files / Components
- `mewhelp/schemas/intent.py`: 9 类细分意图枚举与 5 大出口路由定义
- `mewhelp/services/rewriter.py`: 基于前序会话的指代消解与完整 Query 重构器
- `mewhelp/services/router.py`: 意图分类与出口分流决策器
- `tests/test_intent_router.py`: 针对 20 组复杂半截话、省略句与多意图输入的测试用例集

### Dependencies
- Task 1, Task 2

### Implementation Scope
1. 设计带 Few-shot 的改写与分类 Prompt，输出包含 `rewritten_query`、`intent_type`、`route_target` 与 `missing_entities` 的结构化 JSON。
2. 实现出口映射收敛逻辑：
   - 闲聊、敏感违规 -> 快速兜底回复出口
   - 投诉、强烈情绪 -> 转人工/工单出口
   - 缺少单号等必要要素 -> 信息追问出口
   - 退款、退货规则操作 -> 确定性 Workflow 出口
   - 业务政策与商品知识问答 -> 主力 Agent/RAG 知识检索出口

### Verification
- 运行 `pytest tests/test_intent_router.py`，验证“那这个保修多久？”在带上下文时被正确补齐为主语并分类为售前规则，无上下文模糊输入正确分流至追问出口。

---

## Task 7: LangGraph Deterministic State Machine & ReAct Agent Loop

### Task Goal
基于 LangGraph 搭建全局状态图，实现“确定性骨架 + 开放式 Agent 循环”的混合编排：涵盖意图分流、退款退货确定性子状态机（支持缺单号暂停与用户补齐恢复）以及主力 ReAct 问答循环。

### Relevant Spec Requirements
- **R3**（路由出口收敛）
- **R7**（工具调度执行）
- **R8**（LangGraph 编排与确定性状态机）

### Expected Files / Components
- `mewhelp/workflow/state.py`: 状态机 State 契约定义（消息链、实体槽位、当前路由、退款上下文）
- `mewhelp/workflow/nodes/router_node.py`: 路由调度节点
- `mewhelp/workflow/nodes/refund_workflow.py`: 确定性退款业务状态机（订单状态校验、期限核查、凭证签发、挂起等待单号）
- `mewhelp/workflow/nodes/agent_node.py`: 主力 ReAct Agent 执行循环
- `mewhelp/workflow/graph.py`: 全局 StateGraph 组装与 Checkpointer 持久化配置
- `tests/test_workflow.py`: 完整状态流转、退款条件拦截与多轮中断恢复单测

### Dependencies
- Task 2, Task 5, Task 6

### Implementation Scope
1. 定义全局 AgentState，利用 MemorySaver/SqliteSaver 支持会话状态持久化。
2. 构建退款 Workflow 确定性分支：
   - 检查是否提供 `order_id`，未提供时中断执行并向用户追问；
   - 用户下一轮输入单号后恢复执行，校验订单签收是否超过 7 天、商品状态是否支持退款；
   - 不符合退款条件时硬规则拒绝，严禁 Agent 自由决策承诺。
3. 组装 ReAct Agent 节点，负责通用查询与知识问答。

### Verification
- 运行 `pytest tests/test_workflow.py`：
  - 模拟退款对话，先提“我要退款”，流程暂停等待单号；补充超时订单单号，确定性拒绝退款；补充符合条件订单，成功生成退款凭证。

---

## Task 8: Pre-Generation Confidence Gate & Dual-Layer Memory Management

### Task Goal
在 LLM 生成答案前构建置信度校验闸门（综合 Rerank 分数与证据覆盖度进行阈值研判），拦截无据幻觉；同时实现近端滑窗与远端轻量压缩的双层会话记忆机制。

### Relevant Spec Requirements
- **R5**（置信度闸门与前置防御）
- **R6**（双层会话上下文管理）

### Expected Files / Components
- `mewhelp/guard/confidence_gate.py`: 置信度打分模型与放行/拒答拦截决策器
- `mewhelp/services/memory.py`: 双层记忆管理器（近端保留原始消息，远端触发异步结构化摘要）
- `mewhelp/workflow/nodes/guard_node.py`: 挂载在 RAG 检索之后、LLM 生成之前的守卫节点
- `tests/test_guard_memory.py`: 闸门拦截阈值测试与长对话上下文压缩验证

### Dependencies
- Task 3, Task 7

### Implementation Scope
1. 闸门逻辑：当 Rerank 最大分数低于设定的置信度阈值（如 < 0.65）或关键实体未覆盖时，直接阻断进入生成节点，输出标准优雅拒答，并将拦截信息打标为 `CONFIDENCE_GATE_BLOCKED`。
2. 记忆管理：设置近端滑窗大小（例如最近 4 轮），超过部分自动提取为结构化事实摘要（如用户偏好、已讨论订单号等），兼顾长程连贯性与 Token 消耗控制。

### Verification
- 运行 `pytest tests/test_guard_memory.py`：
  - 输入离谱/知识库完全无记载的问题，100% 触发优雅拒答，拦截耗时 < 50ms。
  - 连续推入 10 轮对话，检查上下文组装结果，确认早期轮次被精准压缩为摘要且关键实体保留。

---

## Task 9: Low-Confidence Problem Pool & End-to-End Tracing Observability

### Task Goal
实现低置信度问题入库管道（覆盖置信度闸门拦截、生成后自评未过、前端用户点踩三大入口），支持文本相似度查重合并；接入全链路 Trace 追踪系统，记录耗时、Token 用量与证据快照。

### Relevant Spec Requirements
- **R5**（拒答问题自动进池）
- **R10**（全链路可观测性 Tracing）
- **R11**（数据飞轮问题池服务）

### Expected Files / Components
- `mewhelp/services/problem_pool.py`: 问题池管理服务（去重查重、进池存储、相似度匹配、状态流转）
- `mewhelp/core/tracing.py`: 链路追踪抽象（支持 Langfuse 契约或本地结构化持久化）
- `mewhelp/api/routes/feedback.py`: 前端用户点赞/点踩与反馈收集端点
- `tests/test_problem_pool_trace.py`: 三入口进池与查重、链路追踪数据完整性测试

### Dependencies
- Task 1, Task 8

### Implementation Scope
1. 问题池去重机制：新问题进池时，通过文本相似度计算检查是否存在未处理的相近问题，若命中则合并频次并追加关联 Session，避免重复堆叠。
2. 构建完整的 Trace 收集器：追踪每次交互的 Trace ID、各阶段（改写、路由、检索、闸门、工具、生成）的耗时与 Token 消耗，并快照最终命中的 Chunk 证据。
3. 提供 `/api/feedback` 接口，用户一旦点踩，立即异步将该轮问题与回答追加打标入库。

### Verification
- 运行 `pytest tests/test_problem_pool_trace.py`：
  - 验证触发闸门拦截与用户点踩时，数据库 ProblemPool 记录正确写入；
  - 检查 Tracing 记录，验证包含完整的输入、输出、耗时和证据 ID。

---

## Task 10: Chat UI, Operator Review Workbench & Data Flywheel Closed-Loop

### Task Goal
提供现代化响应式 Web 对话交互界面（支持流式打字机、引用来源气泡折叠与点赞点踩反馈），构建运营人员审核工作台，支持低置信度问题审查、答案补录与一键向量化回流到知识库，完成数据飞轮全闭环。

### Relevant Spec Requirements
- **R9**（现代化对话界面与流式交互）
- **R11**（数据飞轮闭环与运营工作台）

### Expected Files / Components
- `mewhelp/api/routes/workbench.py`: 运营工作台 API（问题池列表、详情、审核采纳、忽略、回流入库）
- `mewhelp/ui/static/`: 静态前端工程资源（支持对话界面与运营审核后台）
  - `chat.html`, `chat.js`: 终端买家对话端
  - `workbench.html`, `workbench.js`: 运营人员工作台
- `tests/test_e2e_flywheel.py`: 端到端数据飞轮完整闭环自动化测试

### Dependencies
- Task 2, Task 9

### Implementation Scope
1. 买家端界面：简洁流畅的 Chat 对话框，对接 SSE 接口，展示打字动画、引用的政策条款来源，并提供有用/无用反馈按钮。
2. 运营端工作台：表格化展示待审核问题、命中相似度、出现频次；支持运营编辑标准解答，点击“采纳并同步”后自动分块并追加写入向量库。
3. 闭环联动测试：编写 E2E 测试脚本，模拟“提问未知问题 -> 触发拒答进池 -> 运营接口补填答案并同步 -> 再次提问该问题 -> 成功给出新补充的答案”。

### Verification
- 运行 `pytest tests/test_e2e_flywheel.py`，全流程测试通过，闭环验证完成。

---

## Task 11: Offline Intent Classification Model & Fine-Tuning Pipeline

### Task Goal
构建基于轻量文本分类器（如 RoBERTa 或同等预训练模型架构）的离线训练、验证与评估管线，用于离线批处理工单打标、旁路意图聚类与分析。

### Relevant Spec Requirements
- **R12**（轻量主题分类模型 / 微调评估链路）

### Expected Files / Components
- `mewhelp/offline/dataset_prep.py`: 样本数据清洗与划分器 (Train / Val / Test)
- `mewhelp/offline/train.py`: 轻量模型训练与微调管线
- `mewhelp/offline/evaluate.py`: 离线评估脚本，输出混淆矩阵与分类报告
- `tests/test_offline_pipeline.py`: 离线管线单测

### Dependencies
- Task 6

### Implementation Scope
1. 编写意图数据集生成与预处理逻辑，支持从标注数据转换分类特征。
2. 封装标准的训练循环或微调流程，配置合理的超参数与早停策略。
3. 输出包含 Precision、Recall、F1-score 及混淆矩阵的评估报告。

### Verification
- 运行 `pytest tests/test_offline_pipeline.py`，确认管线能够在微型样本集上完成快速训练与评估输出。

---

## Task 12: End-to-End System Verification & Acceptance Run

### Task Goal
针对功能规格说明书（Spec）中的全部 6 项验收标准与 R1~R12 功能项，执行全链路综合验收与集成测试，产出系统完整就绪报告。

### Relevant Spec Requirements
- **R1 ~ R12** 全量覆盖
- 规格说明书第 5 节全部验收标准 (Acceptance Criteria 1~6)

### Expected Files / Components
- `tests/test_full_acceptance.py`: 综合验收测试套件
- `docs/ACCEPTANCE_REPORT.md`: 最终验收测试数据与实测指标记录

### Dependencies
- Tasks 1 through 11

### Implementation Scope
1. 自动化串联执行所有核心业务用例：
   - 越权查单攻击防御 (100% 拦截率)
   - 半截话与指代消解 (准确率测试)
   - 混合检索收益评估 (对比报告)
   - 知识库外问题防幻觉拒答与进池
   - 超期订单退款强拦截
   - 运营回流后秒级生效
2. 验证全链路高可用性与系统日志审计完整性。

### Verification
- 运行 `pytest tests/test_full_acceptance.py` 全部通过，生成验收通过报告。

— NiuNiu Tang

