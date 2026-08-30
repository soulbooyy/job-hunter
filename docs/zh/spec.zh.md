# Job Hunter 产品规格

## 1. 文档职责

本文件是方便开发者阅读的中文副本。上一级目录中的英文版 `../spec.md` 是产品需求与 MVP 范围的权威来源。中文系统设计见 `architecture.zh.md`，开发方式见 `development.zh.md`，量化验收见 `acceptance.zh.md`。

## 2. 产品定义

Job Hunter 是一个面向个人求职的本地优先 AI Job Application Workspace。它通过职位采集或导入、岗位标准化、低成本筛选、人工 shortlist、Career Evidence Retrieval、岗位匹配分析、定制材料生成、事实校验和申请跟踪，降低从发现岗位到材料准备完成的时间，同时保持材料真实性、用户控制和端到端可追溯性。

它不是完全自治的 Auto Apply Agent，也不是单纯的 Resume Generator。

```text
AI 负责
发现、标准化、筛选建议、检索、分析、起草、校验和辅助

Human 负责
最终岗位判断、事实确认、材料修改、材料审批和外部执行授权
```

## 3. 目标与优先级

### 3.1 业务目标

- 降低职位搜索、重复阅读 JD 和初筛成本。
- 快速判断岗位是否值得投入准备时间。
- 从 Candidate Knowledge 中找到与岗位要求相关的可追溯证据。
- 减少逐岗位修改简历与招呼语的重复劳动。
- 统一管理岗位、材料版本、审批和申请状态。

### 3.2 工程与作品集目标

真实展示 LangGraph、Career RAG、Structured Output、受控 Tool Calling、Context Engineering、Human-in-the-loop、Validation/Repair、Traceability、Evaluation、Web/API Integration 和 Backend Engineering。

### 3.3 冲突裁决

真实业务价值拥有最终否决权。Memory、Skills、MCP、Agentic RAG 等能力只有在解决明确且可测量的问题时才进入主链路；否则作为后续能力或独立实验。

## 4. 目标用户与岗位范围

MVP 是 single-user、single-machine 产品，服务项目开发者本人的真实求职流程。

- 地区：深圳。
- 主职位族：AI Agent / LLM Application Engineer。
- 相邻职位族：AI Backend Engineer、AI Full-stack Engineer。
- 目标公司：10–20 家中大型互联网及 AI 企业，优先官方招聘渠道；BOSS 作为首版主要自动采集来源。
- 正式评测：只针对主职位族建立校准与效果声明。相邻职位族共享统一能力维度，通过 role-specific weighting/profile 提供初步评分。

## 5. MVP 主链路

```text
Collect / Import
→ Normalize / Deduplicate
→ Parse Requirements
→ QuickScreen
→ Human Job Triage
→ Shortlisted
→ Evidence Retrieval
→ DeepFitAnalysis
→ Greeting / Resume Preparation
→ Validation / Bounded Repair
→ Human Material Review
→ Ready
```

### 5.1 QuickScreen

QuickScreen 是 triage 前的低成本 screening，只使用：

- normalized job metadata；
- parsed JD/requirements；
- 少量用户确认的 Candidate Profile 稳定事实；
- deterministic 或 bounded screening logic。

输出为 `SCREEN_IN`、`SCREEN_OUT` 或 `UNCERTAIN`。它不运行完整 Career RAG，不输出正式 evidence-grounded fit 结论。系统推荐与用户最终决定必须同时保留。

每个结果保留筛选时实际使用的 Candidate Profile snapshot。创建新 Profile 不会使历史结果失效或改写历史结果；基于旧 snapshot 的结果只是在当前 Profile 语境下变为 stale。产品必须识别该状态、建议重新筛选，同时仍允许用户基于历史结果继续 Human Triage。重新筛选会创建新结果，不覆盖历史。

### 5.2 Human Job Triage

用户可以接受或覆盖 QuickScreen 推荐，最终将岗位标记为 `Shortlisted` 或 `Skipped`。只有 Shortlisted 岗位进入昂贵的 Evidence Retrieval、DeepFitAnalysis 和材料生成。

当 Triage 使用的 QuickScreen 结果并非基于当前 Candidate Profile 时，用户界面必须显式说明。系统建议重新筛选，但不将其设为强制 gate。

### 5.3 DeepFitAnalysis

针对每个 atomic requirement 输出：

- `MATCHED`
- `PARTIAL`
- `MISSING`
- `UNKNOWN`

`MATCHED` 与 `PARTIAL` 必须绑定 supporting EvidenceItemVersion。`MISSING` 表示当前权威 Candidate Knowledge 可以支持“不存在证据”的判断；`UNKNOWN` 表示信息不足，retrieval miss 不得自动解释为 `MISSING`。

### 5.4 Material Preparation

系统基于 JobVersion、DeepFitAnalysis、Candidate Evidence 和 Resume IR 生成：

- 个性化 BOSS 招呼语；
- 一页优先、ATS-friendly 的定制简历；
- PDF 与 PNG artifact；
- Evidence provenance、缺口和风险提示；
- AI 草稿与当前版本的字段级或内容块级 diff。

用户通过结构化编辑器修改 Resume IR，右侧实时显示有限、预定义模板的最终效果。MVP 必须完成 Template A；Template B 为时间允许项，Template C 为 Post-MVP。

## 6. Job Sources

### REQ-JOB-001 — Manual JD Source

系统必须长期支持用户手工输入 JD 文本。

### REQ-JOB-002 — Manual URL Source

系统必须支持保存 Job URL 与用户提供的职位内容。手工来源是正式一级入口，不是临时 fallback。

### REQ-JOB-003 — Boss Source

系统通过受控的 `eatmoreduck/boss-zhipin-scraper` 依赖提供 BOSS 采集能力。依赖固定 immutable commit SHA，通过 Job Hunter 自有 adapter contract 隔离；默认关闭，只有通过独立 Stretch Release Gate 并由用户明确启用后运行。

### REQ-JOB-004 — List-first Collection

BOSS 首次采集优先获取列表数据。规则初筛输出 `PASS`、`REJECT`、`UNCERTAIN`：

- `PASS` 与 `UNCERTAIN` 获取详细 JD；
- 只有高置信硬规则可以直接 `REJECT`；
- 所有过滤结果保留原因、规则版本，并允许恢复和重新运行。

### REQ-JOB-005 — Source Independence

任何 Collector 失败都不得阻断已有岗位、Manual Import、DeepFit、Career RAG、材料生成和 Tracking。

### REQ-JOB-006 — Freshness

职位必须保存 source、captured/collected time、last verification time 和 freshness/stale 状态。历史职位未经重新验证不得伪装为当前有效的新职位。

### REQ-WORKSPACE-001 — Workspace Readback

本地 workspace 必须能够在浏览器刷新后从当前 backend state 重建状态，不依赖 browser persistence。Typed read model 必须暴露 Job 的 active/historical versions、source/freshness lineage、ParsedRequirements、QuickScreen/Triage history，带 active pointer 的 Candidate Profile snapshots，以及包含 immutable version history 的 EvidenceItems。Profile-relative screening freshness 与 Triage eligibility 只是派生 projection，不得替代权威 ID 或历史。

本要求不声明 backend process 重启后的恢复能力。Durable restart recovery 必须由单独获准的 SQLAlchemy/SQLite persistence slice 及其 concurrent-write gate 提供。

## 7. Candidate Knowledge 与 Career RAG

### REQ-KNOW-001 — Candidate Knowledge

MVP 的正式事实来源仅包括：

- 结构化 Candidate Profile；
- 用户录入或从 Markdown/纯文本整理的 EvidenceItem；
- 用户明确确认的 Preferences。

PDF/DOCX 批量摄取、自动去重、事实合并、GitHub MCP ingestion 和模型自由写入长期 memory 均不属于 MVP。

### REQ-KNOW-002 — Evidence Provenance

EvidenceItem 必须拥有稳定 ID、版本、类型、日期、canonical content 和 source/provenance。EvidenceChunk 是可重建的检索派生单元，不能替代 EvidenceItem 成为事实权威。

### REQ-RAG-001 — Retrieval Strategies

统一 `EvidenceRetriever` 边界至少实现：

- eligible Full Context baseline；
- Lexical / Metadata baseline；
- Hybrid Retriever：metadata、lexical、semantic retrieval 与 application-level fusion。

Hybrid RAG 是 MVP 必达能力，但只有通过 promotion threshold 后才能成为对应 workload 的默认策略。

### REQ-RAG-002 — Retrieval Policy

RetrievalPolicy 使用显式、版本化、可 benchmark 的确定性规则选择策略。LLM 不负责首轮 strategy routing。

### REQ-RAG-003 — Bounded Agentic Retrieval

Hybrid workflow 最多允许一次 query reformulation 与一次 supplemental retrieval。第二次仍不足时必须返回 `NO_RELEVANT_EVIDENCE` 或 `INSUFFICIENT_EVIDENCE`。

### REQ-RAG-004 — Eligibility Boundary

所有 Retriever 共享 candidate scope、task type、sensitivity、permission、validity 和 redaction filtering。Full Context 指全部 eligible Evidence；超出预算时必须明确不可执行，禁止隐式截断后仍宣称 Full Context。

## 8. Context Engineering

### REQ-CTX-001 — Context Package

ContextBuilder 必须从 Job Requirements、selected Evidence、用户确认事实、Preferences、task instructions 和最小 workflow projection 构造 versioned ContextPackage，并记录 provenance、选择/排除原因、redaction、token accounting 和版本。

### REQ-CTX-002 — Runtime Context Manager

MVP 必须实现 bounded、typed、deterministic RuntimeContextManager，支持：

- typed ContextEntry 与 priority；
- duplicate/obsolete elimination；
- 大型结果 externalization；
- local Artifact 与 typed ContextReference；
- explicit rehydration；
- versioned priority-based compaction；
- protected context 仍超预算时显式失败。

不实现通用无限对话压缩、递归 LLM summarization、autonomous memory rewriting 或跨任意 workflow 的历史重建。

## 9. LangGraph 与 Tool Calling

### REQ-AGENT-001 — Stateful Material Workflow

LangGraph 只编排：

```text
Parsed Shortlisted Job
→ Retrieve
→ Deep Fit
→ Draft
→ Validate
→ Repair?
→ Human Review interrupt
→ Approved / Revision Requested
```

Requirement Parsing、QuickScreen、Job Triage、Job Discovery、CRUD、Tracking、Rendering 实现和 Browser Execution 不属于 Graph 状态机。Material Review 使用 LangGraph interrupt；Job Triage 使用普通 Application/Domain 的持久化 HITL checkpoint。

### REQ-AGENT-002 — Bounded Repair

最多允许两次 targeted repair；每次只修改获授权的 Resume IR 字段并运行完整 revalidation。不得存在无界循环。

### REQ-AGENT-003 — Capability Policy

每个 Node 声明静态 NodeToolPolicy：allowed tools、resource scope、调用/迭代次数、timeout、token/result-size budget 和 side-effect class。策略由代码强制执行，而非依赖 prompt。

### REQ-AGENT-004 — External Side Effects

普通 Agent tool loop 不得拥有 Browser Executor、外部消息、文件上传、Shell、任意代码执行、任意 SQL 或通用文件系统权限。

## 10. Grounded Resume

### REQ-RESUME-001 — Resume Claim

AI 生成或改写的事实内容必须先表示为 ResumeClaim，至少包含 text、claim type、EvidenceItemVersion references、transformation type 和 validation status。

### REQ-RESUME-002 — Unsupported Claims

没有 Evidence 或验证为 unsupported 的 factual claim 不得进入最终简历。Inference、新增量化结果、扩大责任范围或推断技能熟练程度属于高风险转换，需要明确验证或人工确认。

### REQ-RESUME-003 — Structured Editor

前端必须提供 Structured Resume Editor、实时 preview、有限模板切换能力、字段/内容块 diff、版本保存、PDF 与 PNG 导出。不实现自由拖拽、任意富文本、任意 CSS 或 Canva 式设计器。

## 11. Human-in-the-loop 与审批

### REQ-HITL-001 — Job Triage Gate

QuickScreen 完成后必须由用户决定 Shortlisted 或 Skipped，并保留系统推荐与用户最终决定。

### REQ-HITL-002 — Material Review Gate

Validated Draft 进入 Ready 前必须经过人工 Review。页面展示 DeepFit、Evidence provenance、unsupported/unknown 项、diff、Greeting 与最终简历预览。

### REQ-APPROVAL-001 — MaterialApproval

MaterialApproval 绑定 ResumeVersion、GreetingVersion（如适用）和实际 artifact/hash，只表示用户接受材料并允许进入 Ready，不授予任何外部执行权限。

### REQ-APPROVAL-002 — ExecutionApproval

ExecutionApproval 引用有效 MaterialApproval，并绑定 account、canonical job、action set、artifact versions/hashes、expiry。它必须 single-use、scope-bound、time-bound，只能由 deterministic Browser Executor 消费。

### REQ-APPROVAL-003 — Invalidation

材料内容、版本或 hash 变化必须使相关 MaterialApproval 和未消费的 ExecutionApproval 失效。MaterialApproval 不得被 Executor 当作执行授权。

## 12. Application Tracking

MVP 业务生命周期为：

```text
Imported
→ Screened
→ Shortlisted / Skipped
→ Preparing
→ Ready
```

不同渠道可以产生非线性业务里程碑：

- BOSS：`Contacted`、`MaterialsSent`；
- 企业 ATS：`Applied`；
- Email：`MaterialsSent`。

`Rejected` 与 `Withdrawn` 为终态。`Ready` 不表示已经授权或执行外部动作。浏览器点击、输入、上传、验证码、限流和失败属于 ExecutionEvent/execution state，不扩张 ApplicationStatus。

## 13. Stretch Goal — Browser Executor

核心 MVP 不依赖真实投递成功。Stretch Executor 若实现，只支持：

- 一个已批准任务；
- 用户显式开始；
- visible browser；
- 单岗位执行；
- 白名单业务动作；
- 每步 read-back；
- 任一未知或异常立即停止；
- 无自动 retry；
- PARTIAL 后只允许新的、范围更窄的 ExecutionApproval 继续缺失步骤。

验证码、限流、登录异常、页面结构无法识别、连续验证失败或账号安全提示必须触发熔断。不得绕过验证码、突破平台限额、切换账号继续或实现主动反检测。

## 14. 数据、安全与隐私

- MVP 为 localhost 单机应用：React SPA、FastAPI、SQLite、Chroma 和本地 artifact store。
- 完整职业资料、联系方式、凭证、Cookie、Token、Chrome Profile 和浏览器 Session 默认留在本地。
- 第三方模型只获得完成任务所需的最小、经 redaction 的 ContextPackage。
- 外部 trace 默认只包含 ID、版本、结构、token、latency 和错误分类；高敏感调用可以隐藏输入输出或关闭外部 tracing。
- 原始 prompt、response、diagnostic artifact 和局部截图采用本地短期 retention；Executor 截图默认 7 天。
- 用户可以删除敏感原文；系统只保留不含敏感内容的 tombstone 与 deletion audit。

## 15. Traceability

系统必须建立可遍历的权威 lineage：

```text
SourceSnapshot
→ JobVersion
→ ParsedRequirement
→ RetrievalRun
→ EvidenceChunk / EvidenceItemVersion
→ ContextPackage
→ ModelInvocation
→ ResumeClaim
→ ValidationResult
→ ResumeVersion
→ MaterialApproval
→ ExecutionApproval / ExecutionEvent
```

Domain Lineage 是权威事实；LangSmith 和系统 observability 不能替代它。

## 16. 明确非目标

- 无人值守或长期批量 Auto Apply；
- 自动最终提交或自动外部通信；
- 验证码破解、风险码绕过、主动反检测；
- 全互联网职位 Crawling；
- 任意文档批量 ingestion 与自动事实合并；
- 模型自由写入 Candidate Facts 或通用长期 memory；
- 动态 Skill Runtime、插件市场或通用 MCP 平台；
- Shell、通用代码执行或 OS/container sandbox；
- SaaS、多租户、Redis、Celery、微服务、Kubernetes；
- 外部向量服务、完整监控平台、Electron、Cloud Control Plane；
- 自由排版简历设计器。

## 17. 延后能力

- GitHub read-only MCP Client，经人工确认生成 Evidence Draft；
- versioned Skill Registry 与 progressive disclosure；
- Interview Preparation、Application Questions、Company Research；
- 多模板扩展、Electron shell；
- 企业官网/ATS Connector；
- 小批量 Executor；
- Experience Memory；
- Cloud Control Plane + Local Execution Agent；
- PostgreSQL、远程 Executor 与生产级 observability。
