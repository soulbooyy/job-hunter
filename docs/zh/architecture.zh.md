# Job Hunter 系统架构

## 1. 文档职责

本文件是方便开发者阅读的中文副本。上一级目录中的英文版 `../architecture.md` 是当前生效架构与技术边界的权威来源。中文产品需求见 `spec.zh.md`，开发规范见 `development.zh.md`，验收门槛见 `acceptance.zh.md`。

## 2. 架构原则

1. Business First：业务价值可否决技术展示。
2. Local First：MVP 的数据、身份状态、浏览器和 artifact 默认留在本机。
3. Read/Write Separation：只读采集与外部写执行物理、权限和状态分离。
4. Human Authority：岗位选择、事实确认、材料批准和外部动作授权属于用户。
5. Evidence Grounding：事实性输出必须绑定 Candidate Evidence。
6. Fail Closed：权限、schema、页面结果或 provenance 无法确认时停止。
7. Deterministic Control Plane：状态、预算、审批、幂等与安全由代码强制，而非 prompt。
8. Bounded Agency：检索、tool loop 和 repair 都有明确上限。
9. Traceability by Design：lineage 是领域数据，不是日志的副产品。
10. Design for Change, Implement for Today：保留正确 seam，不预实现未来 adapter。

## 3. 系统上下文

```text
User
  │
  ▼
React + TypeScript + Vite SPA
  │ HTTP; SSE/WebSocket only when a use case requires streaming
  ▼
FastAPI Application
  ├── Job Acquisition and Screening
  ├── Candidate Knowledge and Retrieval
  ├── LangGraph Material Workflow
  ├── Resume Rendering
  ├── Approval and Tracking
  └── Domain Lineage
  │
  ├── SQLite authoritative data
  ├── Chroma rebuildable vector index
  ├── Local artifact store
  ├── LLM Provider via LangChain model interface
  └── Optional local processes
      ├── Boss Collector
      └── Local Browser Executor (Stretch, default off)
```

MVP 是单机 localhost 应用，不开放局域网或公网访问，不做多设备同步。运行环境相关信息通过 typed Runtime Configuration 管理；业务逻辑不得依赖 repository cwd、硬编码端口或本机路径。

FastAPI 与独立本地进程默认只绑定 `127.0.0.1`。CORS 只允许已配置的 Job Hunter 前端 origin；涉及 mutation 的本地 API 使用明确的 origin/request protection。Browser Executor 即使只监听 loopback，也必须使用随机、短权限的本地鉴权令牌，并且不提供 Cookie、Shell、JavaScript 或通用浏览器 RPC 接口。MVP 不实现产品账号体系，但“本机可访问”不能被视为无限信任。

## 4. Repository Topology

```text
job-hunter/
├── backend/
│   ├── src/job_hunter/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── api/
│   │   ├── ingestion/
│   │   ├── knowledge/
│   │   ├── retrieval/
│   │   ├── context/
│   │   ├── workflows/
│   │   ├── rendering/
│   │   ├── execution/
│   │   ├── observability/
│   │   └── infrastructure/
│   ├── tests/{unit,integration,contract}/
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── src/
│   ├── tests/
│   └── package.json
├── evals/{datasets,rubrics,runners,reports}/
├── docs/
├── scripts/
├── third-party/
├── .github/
├── AGENTS.md
└── README.md
```

根目录是产品 workspace。`backend/` 与 `frontend/` 是真实 toolchain/runtime boundary，但整个 MVP 仍是模块化单体，不建立 `apps/packages/services/platform/shared` 等通用 monorepo 层级。

## 5. 分层与依赖方向

```text
API / UI / CLI
      ↓
Application Use Cases
      ↓
Domain Policies / Entities
      ↓
Ports
      ↑
Infrastructure Adapters
```

### 5.1 API

FastAPI route 只负责 request validation、local request context、调用 use case、response mapping 和错误映射。它不得直接写 SQL、查询 Chroma、调用 LLM、运行 scraper 或操作浏览器。

调用同步 SQLAlchemy application graph 的 route 使用同步 FastAPI handler，使 blocking database I/O 由 framework-managed worker thread 而非 event loop 执行。Async handler 只保留给真正的 async boundary。

Workspace readback 使用 resource-oriented GET contract，分别读取 Job collection、单个完整 Job read model、Candidate Profile snapshots 与 Evidence histories。Job read model 包含版本/source/Requirement lineage 以及 QuickScreen/Triage history；API 不直接暴露 Domain object，也不提供 catch-all `/workspace` dump。包含 Candidate Knowledge 或 Job content 的响应必须设置 `Cache-Control: no-store`。

### 5.2 Application

Use Case 表达一次完整业务意图，例如 `ImportJob`、`RunQuickScreen`、`ShortlistJob`、`PrepareMaterials`、`ApproveMaterials` 和 `AuthorizeExecution`。Application 管理事务边界和 port 协作，不拥有外部 SDK 细节。

获取 UnitOfWork 本身属于 Application failure boundary。未知的 factory 或 port 异常必须转换为稳定的 Job Hunter error；只有成功获取 UnitOfWork 后才允许尝试 rollback。

`WorkspaceQueries` 从一个 UnitOfWork snapshot 构造每个 read model。SQLite adapter 在第一次 SELECT 前显式开始 database transaction，使同一 UnitOfWork 的所有 repository read 观察同一个 committed snapshot。它 deterministic 地排序 immutable history，并依据权威 active pointer 派生 `current/stale` 与 Triage-eligibility 字段。这些字段仅是 projection，不得写回 Domain State。

### 5.3 Domain

Domain 拥有稳定实体、value object 与 policy，包括 Job/JobVersion、Requirement、Evidence、ResumeClaim、Approval、状态迁移、evidence eligibility、deduplication、claim grounding 和 approval validity。

### 5.4 Infrastructure

SQLAlchemy、SQLite、Chroma、LangChain provider、scraper、renderer、artifact store 和 browser 是 adapter。第三方异常必须在 adapter boundary 映射为 Job Hunter error taxonomy。

### 5.5 Port 规则

只为真实替换点或测试 seam 定义 Port，例如 Repository、UnitOfWork、ModelGateway、EvidenceRetriever、Clock、IDGenerator、ArtifactStore、Collector、Renderer 和 Executor。普通内部 helper、policy 或 value object 不创建形式主义 interface。

当生产环境只有一个实现，且基于继承的测试替身已经满足真实 seam 时，API composition 可以直接依赖具体 Application Use Case。只有出现必须遵守同一 contract 的第二个非子类实现或替身时，才引入 application-level Protocol。通过 dynamic framework state 读取 lifespan-managed dependency 时，API boundary 必须执行 runtime validation；未经检查的 `cast()` 不属于 validation。若未来由 Protocol 承担该运行时边界，必须明确其 runtime-checking semantics，不得通过放宽或删除 guard 解决。

必须共享同一 transaction 或 repository graph 的 application-scoped use case，应作为一个完整 typed bundle 进行 composition 与 override。除非 use case 被明确证明彼此独立，否则不支持逐项 partial override；composition 不得静默组合由不同 store 支撑的 dependency。

## 6. 核心领域模型

### 6.1 Job 与版本

```text
Job
├── job_id                     logical identity
├── active_version_id
├── source references[]
└── lifecycle status

JobVersion
├── immutable normalized facts
├── normalized company/title/city
├── JD content
├── freshness
└── source snapshot references
```

来源内身份：

```text
source_identity = platform + source_job_id
```

跨 posting 去重候选：

```text
dedup_fingerprint = normalized_company
                  + normalized_title
                  + city
                  + description_signature
```

高置信重复可自动关联或合并；模糊结果只标记 `possible_duplicate`，由用户确认。

### 6.2 SourceSnapshot 与临时字段

原始采集结果先成为隔离的 SourceSnapshot，经 adapter validation 和 normalization 后才能形成 JobVersion。BOSS `security_id`、`lid` 等临时字段只存在于带 `captured_at`、TTL 和 source 的 SourceSnapshot/ExecutionContext；不参与 canonical identity，执行前重新获取或验证。

### 6.3 Requirement

ParsedRequirement 是 JobVersion 下的稳定、原子化需求，包含 requirement ID、文本、类型、priority（`REQUIRED/PREFERRED/UNSPECIFIED`）和 parser provenance。复合要求尽量拆分，但必须保留原文映射。

初始 deterministic baseline 保留标准化后的 JD 行边界，并将每个非空 bullet/line 作为一个 source unit。它只移除已识别的 bullet prefix、去重完全相同的标准化行、通过显式关键词规则判断类型与 priority，并记录 parser name/version。Requirement ID 对每个 immutable JobVersion 只分配一次，后续 QuickScreen rerun 复用这些 ID。该 baseline 用于建立 deterministic workflow test；在 dataset/evaluation 切片完成前不声明 parser quality，model parsing 与 bounded repair 仍不在当前范围内。

### 6.4 Candidate Knowledge

```text
CandidateProfile
EvidenceItem
├── evidence_id
├── active_version_id
└── versions[]

EvidenceItemVersion
├── canonical content
├── type/date/source/provenance
├── sensitivity/validity
└── metadata

EvidenceChunk
├── chunk_id
├── parent evidence_version_id
├── chunk_policy_version
└── retrieval text/index metadata
```

EvidenceItemVersion 是事实权威；EvidenceChunk 是可重建的派生索引单元。最终 ResumeClaim 绑定 EvidenceItemVersion，而不是易变化的 chunk。

当前 CandidateProfile 输入是 immutable、human-confirmed 的 screening snapshot，只包含 target-role keyword、skill keyword 和 preferred city。创建新 snapshot 会更新 active profile projection，但不会删除旧 snapshot；每个 QuickScreenResult 引用实际使用的 profile ID。Evidence 继续保持独立，不会自动提升为 Profile fact，也不会被 QuickScreen 自动消费。

### 6.5 Resume 与 Claim

Resume IR 是 canonical resume content。Template 只负责 presentation，不改变 canonical content。

```text
ResumeClaim
├── claim_id
├── text
├── claim_type
├── evidence_version_ids[]
├── matched_requirement_ids[]
├── transformation_type
├── author_type
└── validation_status
```

`author_type` 区分 AI-generated、AI-rewritten、human-authored 和 human-edited。人工内容不伪造 ModelInvocation，但仍遵守 evidence grounding 与 validation。

### 6.6 审批

```text
MaterialApproval
├── material bundle versions/hashes
├── user decision
└── validity

ExecutionApproval
├── material_approval_id
├── account_id
├── canonical_job_id
├── action_set
├── artifact versions/hashes
├── expires_at
├── single_use
└── consumed_at
```

Ready 只表示材料批准，不表示执行授权。Material mutation 创建新版本并使相关 MaterialApproval 以及未消费的 ExecutionApproval 失效。

## 7. Job Acquisition Architecture

### 7.1 Static Adapter Registry

```text
JobSource protocol
└── JobSourceRegistry
    ├── ManualJDSource
    ├── ManualURLSource
    └── BossSource
```

这里的 plugin 仅指通过配置启停的可替换 adapter，不是动态安装系统、Codex Skill 或 MCP Server。

### 7.2 Boss Third-party Dependency

`eatmoreduck/boss-zhipin-scraper` 运行在独立 Python 环境，通过 immutable commit SHA、dependency/hash lock、allowlisted CLI invocation 和 Job Hunter-owned contract 管理。

禁止跟随 `master` 或把上游自报版本当成稳定 API。默认不依赖其内部 Python module API。只有 CLI 无法满足且用户明确批准时，才允许以可追溯 patch/fork 修改；必须记录上游 SHA、patch 原因、影响范围、批准和 contract-test 结果。

### 7.3 Collector Contract

```json
{
  "contract_version": "1",
  "run_id": "...",
  "status": "succeeded|partial|failed",
  "jobs": [],
  "warnings": [],
  "error": null,
  "source_metadata": {}
}
```

BossCollectorAdapter 管理 subprocess 生命周期、临时输出、timeout、exit code、原始 JSON/CSV、normalization、schema validation、stderr redaction 和错误分类。异常原始结果只能成为 diagnostic artifact，不得直接进入 domain database。

### 7.4 Safety Policy

Collector 默认关闭；用户可配置采集条件、最大岗位数和受安全下限约束的间隔。CAPTCHA、风险码、登录异常、账号验证、严重 schema drift、连续异常或未知结果必须立即停止。不得自动复制 Cookie，不实现验证码破解、风险码绕过或反检测增强。

## 8. Screening 与 Fit

### 8.1 QuickScreen

QuickScreen 运行在 Human Triage 前，目标是低成本减少后续工作量。它使用 Job metadata、ParsedRequirement、少量 Candidate Profile 稳定事实和受限规则/模型逻辑，输出 `SCREEN_IN/SCREEN_OUT/UNCERTAIN` 与理由。它不是 Career RAG，也不输出正式 requirement-level fit。

`quick-screen-v1` 是 deterministic 且刻意保守的 policy：岗位城市不在非空 preferred-city set 中时输出 `SCREEN_OUT`；城市可接受，且 title 命中 target role、ParsedRequirements 中至少包含一个已确认 skill keyword 时输出 `SCREEN_IN`；其他情况全部输出 `UNCERTAIN`。结果记录 active JobVersion、准确的 CandidateProfile snapshot、Requirement IDs、reason codes、policy version、run ID 与 correlation ID。

运行 QuickScreen 会创建新的 append-only recommendation，并将 Job 移至 `Screened`。Human Triage 另行记录引用最新 recommendation 的 append-only `Shortlisted` 或 `Skipped` decision；用户之后可以覆盖任一决定。新 active JobVersion 会把 Job 返回 `Imported`，Triage 必须拒绝属于旧 JobVersion 或已经不是最新一次的 recommendation。

Candidate Profile freshness 是派生的 read concern，而不是 `QuickScreenResult` 上的可变状态：通过比较结果所引用的准确 `profile_id` 与 active Candidate Profile ID，报告 `current` 或 `stale`。激活新 Profile 不得删除、改写或使历史 screening lineage 失效。当 stale-profile result 仍是 active JobVersion 的最新结果时，它仍可用于 Human Triage，但面向用户的 read model 必须显式标记并建议重新筛选。重新筛选只追加新结果，不替换旧结果。

### 8.2 DeepFitAnalysis

只有 Shortlisted Job 进入 DeepFit。流程先检索 Evidence，再逐 Requirement 产生 `MATCHED/PARTIAL/MISSING/UNKNOWN`、supporting Evidence 与风险。DeepFit 是 Q71 指标和 grounding gate 的唯一正式 Fit artifact。

## 9. Retrieval Architecture

### 9.1 Eligibility First

```text
Candidate Knowledge
→ candidate/task scope
→ permission/sensitivity/validity
→ redaction
→ eligible Evidence set
→ RetrievalPolicy
```

任何 Retriever 都不得绕过 eligibility boundary。

### 9.2 Strategies

```text
EvidenceRetriever
├── FullContextRetriever
├── LexicalMetadataRetriever
└── HybridRetriever
    ├── SQLite metadata / FTS5
    ├── Chroma semantic index
    └── application-level fusion
```

SQLite 保存 authoritative Evidence 与 metadata。Chroma 只保存可重建向量索引，并记录 embedding model/provider、dimension、chunk policy 和 index version。正式采用 Chroma 前必须完成 local feasibility spike：persistence、metadata filtering、update/delete、rebuild、packaging 和 benchmark。

首个 retrieval baseline 只处理从 authoritative repository 取得的 active EvidenceItemVersion。Application boundary 在 eligibility 或 retrieval 前验证每个返回 version 同时匹配所属 EvidenceItem ID 与 active-version pointer。共享 eligibility policy 仅允许 caller 明确授权 sensitivity 的 `VALID` Evidence；被排除的 ID 和原因保留在 RetrievalRun lineage 中。Retriever output 与 evaluation report 只记录稳定 ID、rank、score、reason 和版本 metadata，不复制 Candidate Evidence 内容。

`FullContextRetriever` 以确定性顺序返回全部 eligible Evidence；当版本化 deterministic token estimate 超出预算时返回明确 `NOT_EXECUTABLE`。Application 与 Domain validation 分别拒绝未精确覆盖 eligible set 却声称 completed 的 Full Context result。`LexicalMetadataRetriever` 使用版本化 exact-phrase、normalized-token 与 metadata matching，并用稳定 ID 打破并列；它按 `top_k` 与 retrieval `max_tokens` 共同约束选择 ranked prefix，不会跳过超预算的高排名 Evidence 去接纳更弱 Evidence。零信号明确返回 `NO_RELEVANT_EVIDENCE`，有信号但最高排名项也无法纳入预算时返回 `NOT_EXECUTABLE`。

每个 RetrievalRun 分别记录完整 eligible Evidence set 与 selected Evidence 的 token estimate；completed retrieval 的 selected estimate 必须不超过 `max_tokens`。这只是 retrieval-selection budget；未来 ContextBuilder 加入 Requirement、instruction 与 packaging overhead 后，另行负责最终 ContextPackage hard budget。

### 9.3 Deterministic Retrieval Policy

- eligible tokens 在校准阈值内：Full Context；
- identifier/certificate/named project/skill：Lexical + Metadata；
- semantic requirement-to-experience：Hybrid；
- 多个条件同时满足时使用固定 precedence。

每次运行记录 policy version、输入统计、selected strategy 和原因。Hybrid 未达到 promotion threshold 时保留为 experimental，并回退到 Full Context 或 Lexical。

Baseline slice 不实现自动 strategy selection。Application use case 接收一个已配置的 `EvidenceRetriever`，强制 Job 为 Shortlisted 且 Requirement 属于当前 JobVersion，并持久化不可变 RetrievalRun，将 Requirement 关联到实际返回的 EvidenceItemVersion。

### 9.3.1 Evaluation Boundary

`evals/datasets/` 下的 versioned JSON 属于不可信 IO，runner 构造 typed evaluation case 前必须通过 Pydantic validation。Dataset loader 拒绝重复 case ID、悬空或重复 judgment、指向该 case eligible Evidence universe 之外的 relevance judgment，以及未人工确认的 No-Evidence 标签。Retrieval Recall@5 在存在 relevant judgment 的 case 上做 macro average；Direct-Evidence MRR 在至少有一个 `DIRECT` judgment 的 case 上计算；No-Evidence Accuracy 只统计明确人工确认的 No-Evidence case。Parser atomic precision/recall 使用 exact normalized-text matching；priority per-class precision、recall、F1、support 与 Macro-F1 只对已匹配 atomic requirement 计算。QuickScreen 单独报告 exact-label accuracy 和 raw confusion counts，并与 production execution 共用同一个 policy-version constant。每个 metric 都包含 numerator/denominator 或 confusion count。Replay model output 仅限 evaluation，不得进入 Domain State，也不得调用 live provider。

### 9.4 Bounded Agentic RAG

```text
Initial Retrieval
→ Structured Sufficiency Assessment
→ At most one Query Reformulation
→ Supplemental Retrieval
→ Final Sufficiency Decision
```

预算耗尽或仍不充分时返回正常的 no/insufficient evidence 状态，不能降低相关性门槛或继续搜索直到找到支持。

## 10. Context Engineering

### 10.1 Context Construction

ContextBuilder 产生 immutable、versioned ContextPackage：

```text
Job Requirements
+ selected Evidence and provenance
+ approved Candidate facts/preferences
+ task instructions
+ minimal workflow projection
+ redaction and token budget
→ ContextPackage
```

它记录输入版本、选择/排除原因、token estimate、redaction、policy/prompt version，禁止注入其他岗位材料、完整对话历史或整个 Career Vault。

### 10.2 Runtime Context Manager

ContextEntry 至少包含 type、source、token estimate、priority、provenance、retention class、protected flag 和 rehydratable flag。

Deterministic compaction 顺序由 versioned CompactionPolicy 控制：去重/过期消除、低优先级裁剪、大型结果 externalization。ArtifactReference 必须类型化并可显式 rehydrate。Protected entries 不能静默丢失；若安全压缩后仍超预算，返回 `CONTEXT_BUDGET_EXCEEDED`。

Compaction 改变模型可见 representation，不修改 Candidate Knowledge、User Preference 或 domain authority。

## 11. Memory 与 Capability Plane

必须区分：

- Agent Context：当前消息、必要历史、Job、retrieved Evidence、Tool Results；
- Candidate Knowledge：Profile 与 Evidence；
- User Memory：仅用户明确确认的 Preferences；
- Workflow/Domain State：Job、Resume、Approval、checkpoint、execution record；
- Capability Plane：Tool、未来 Skill、未来 MCP。

模型不得自由写入 Candidate Knowledge 或长期 User Memory。Checkpoint、Cookie、Token、browser session 和 infrastructure state 默认不可见；只有最小、语义化 projection 可以进入 ContextPackage。

MVP 不实现 Skill Runtime 或 MCP。未来 Skill 采用 versioned registry 与 progressive disclosure；首个 MCP 候选是 allowlisted、read-only GitHub Client，输出只成为待人工确认的 Evidence Draft。

## 12. LangGraph Runtime

### 12.1 Graph Boundary

```text
Parsed Shortlisted Job
→ Retrieve
→ Deep Fit
→ Draft
→ Validate
→ Repair? (max 2)
→ Material Review interrupt
→ Approved / Revision Requested
```

Requirement Parsing 与 QuickScreen 在 Human Job Triage 前由普通 Application Service 完成。只有 Shortlisted Job 进入 Graph。Graph node 粗粒度，对应有意义的 typed state transition。Node 不直接写 SQL、操作浏览器或运行外部进程；通过 application service/port 获取能力。

两个 Human Gate 使用不同的持久化机制：Job Triage 是 Application/Domain workflow checkpoint，负责 `Screened → Shortlisted/Skipped`；Material Review 是 LangGraph interrupt/checkpoint，负责 validated material 到 Approved/Revision Requested。两者都必须支持 durable resume 和审计，但不能为了统一形式把 Job Triage 强行塞入 LangGraph。

### 12.2 Structured Output

Job Hunter 使用 LangChain 现有模型接口，不重新封装供应商 SDK。ModelProfile/Factory 声明 provider、model、credential reference、base URL、timeout 和必要参数。MVP 正式回归一个 primary provider/model，允许显式配置切换 LangChain-supported provider，但不实现自动 fallback 或动态 routing。

进入 domain state 的模型输出必须经过 Pydantic structured-output contract。裸文本不能直接成为 Job、FitAnalysis、ResumeClaim 或 ValidationResult。

### 12.3 Capability Policy

每个 node 声明 NodeToolPolicy：allowed tools、resource scope、max calls/iterations、timeout、token/cost/result-size budget 和 side-effect class。

工具按 `READ_ONLY`、`LOCAL_REVERSIBLE_WRITE`、`LOCAL_PERSISTENT_WRITE`、`EXTERNAL_SIDE_EFFECT` 分类。普通 tool loop 只允许预授权的 read/local capability；external side effect 永不进入 Graph。

### 12.4 Validation and Repair

Deterministic checks 负责 schema、field constraints、provenance、approval/rendering invariants；bounded semantic checks 负责 claim-evidence support。Repair 只接收明确错误、目标字段和相关 Evidence，输出 structured patch。每次 patch 后进行完整 revalidation，最多两次，之后进入人工处理或失败。

## 13. Resume Rendering

Template renderer 从 Resume IR 生成 HTML/CSS、PDF 和 PNG。Template A 为 MVP 必达；模板切换只改变 presentation。

Determinism 定义为相同 IR/template/renderer 得到一致语义内容与布局，而非 PDF byte-level equality。实际 artifact 仍生成 immutable hash，MaterialApproval 绑定用户看到的具体 artifact。

## 14. Browser Execution Boundary

Browser Executor 是独立 deterministic service，不属于 LangGraph。它只暴露窄业务命令，例如 `OpenJob`、`SendApprovedGreeting`、`SendApprovedResume` 和 `VerifyOutreachResult`，不得暴露任意 selector click、JavaScript、Shell、Cookie export、MITM 或通用私有协议。

```text
ExecutionApproval verification
→ Idempotency check
→ Precondition/read-current-state
→ One allowlisted browser action
→ Read-back verification
→ Append-only ExecutionEvent
```

幂等键为 `platform + account_id + canonical_job_id`。PARTIAL 保存 `last_verified_step`；已验证动作不得 replay。继续缺失步骤需要新的窄 ExecutionApproval。

MVP 只实现 LocalBrowserExecutor；不创建 RemoteExecutor 或 OfficialAPIExecutor 空壳。若新第三方 executor 满足许可证、维护、固定版本、适配性、安全边界和窄命令 admission gate，才可替代自有最小 Playwright/CDP adapter。

## 15. Persistence、版本与删除

持久化通过 Repository + Unit of Work 进入 SQLAlchemy/SQLite。不得承诺 SQLite 到 PostgreSQL 零成本切换，也不预实现 PostgreSQL adapter。

默认本地 adapter 使用一个由 lifespan 管理的同步 SQLAlchemy engine/session factory，并为每个 UnitOfWork 创建一个短生命周期 Session。SQLite driver transaction control 被禁用，SQLAlchemy 为 read/write 显式发送 deferred `BEGIN`；这既保留 concurrent reader，也使第一次 SELECT 建立 UnitOfWork snapshot。Application use case 继续拥有 transaction boundary，且每个 UnitOfWork（包括成功的 read-only operation）都必须显式 close。Alembic 是唯一 schema creation path：setup 或显式 database-upgrade command 执行 migration；application startup 只校验 schema head，不得静默调用 `create_all()` 或自动迁移。

Mutable logical root（`Job`、`EvidenceItem` 和 Candidate Profile active-pointer state）使用 infrastructure-owned optimistic revision。`Job` 同时拥有 authoritative latest-QuickScreen pointer：每次 re-screen 都改变该 pointer，新 JobVersion 清空它，Triage 保留它。SQL Repository 在 hydrate/read root 时捕获 expected revision，并在 flush/commit 使用 database compare-and-swap update，因此基于同一 Job revision 的 concurrent re-screen 与 Triage 不可能同时提交。Revision metadata 不进入 Domain model 或 HTTP contract。Immutable version 与 lineage row 保持 append-only，并随失败 transaction 一起 rollback。

初始 adapter 将经过 runtime validation 的 immutable value payload 以 JSON text 保存，同时使用 normalized relational column 表达 identity、ownership、lineage、deterministic write order、active pointer 与 revision。Hydration 必须交叉验证所有重复 identity/ownership field；mismatch 或非法 payload 均 fail closed。这些 payload 只是内部 persistence representation，不是另一套 Domain 或 API contract；Domain shape 变化时，除 schema change 外还必须提供 Alembic data migration。

QuickScreen-to-Requirement 与 RetrievalRun-to-Evidence lineage 使用 normalized ordered association row 保存，而不是只存在 serialized payload 中。Composite ownership constraint 与 hydration check 强制 Job → JobVersion → Requirement、Triage → QuickScreen → Job、RetrievalRun → Requirement → JobVersion，以及 EvidenceItem → EvidenceItemVersion relationship。Payload 与 association row 必须描述同一 lineage；不一致时 fail closed。

影响生成、审批或执行的实体采用版本化；snapshot 型记录一旦创建即 immutable。Logical entity 只维护 active-version pointer。用户隐私删除可以真正删除敏感原文或文件，但保留不含敏感内容的 entity/version ID、删除时间、原因和必要 hash tombstone。

### 15.1 并发写入边界

当前内存 Repository/UoW 是用于开发的 deterministic single-writer adapter。单个 UoW 会原子提交其 Job、JobVersion 与 SourceSnapshot 状态，但重叠 UoW 可能相互覆盖，因为该 adapter 不提供事务隔离或 lost-update prevention。不得将其描述为生产事务实现，也不得在允许 mutation 重叠的运行配置中使用。

以下任一能力进入默认运行路径前，必须完成并发写入设计：

- SQLAlchemy/SQLite 或其他持久化 Repository/UoW adapter；
- 并行 mutation use case、后台 writer，或共享权威状态的独立本地进程；
- 多 API worker，或任何可能发生写入重叠的其他配置。

获准进入默认路径的设计必须防止 silent lost update。基于版本化状态的 mutation 必须携带明确的 expected revision 或 expected active-version identifier；stale writer 必须按稳定的 conflict/stale-version taxonomy 失败，同时保持已提交版本历史和权威 lineage 完整。持久化切片可以根据 SQLite 选择数据库约束、optimistic revision check、compare-and-swap 或 serialization，但必须先冻结可观察的事务与冲突语义，再选择实现机制。仅有进程内锁不能证明具备多进程保证。

获准 SQLite adapter 使用 foreign-key enforcement、WAL mode、bounded busy timeout 与 SQLAlchemy optimistic version check。Compare-and-swap 失败或 stale SQLite snapshot 转换为稳定 `stale_write` conflict；其他 database availability failure 保持 dependency-unavailable。Boundary error 与 SQL log 不得包含 SQL statement、parameter、Candidate content 或本地 database path。

## 16. Traceability 与 Observability

### 16.1 Domain Lineage

权威 lineage 存储在 Job Hunter 数据库中：

```text
SourceSnapshot → JobVersion → ParsedRequirement
→ RetrievalRun → EvidenceChunk/EvidenceItemVersion
→ ContextPackage → ModelInvocation
→ ResumeClaim → ValidationResult → ResumeVersion
→ MaterialApproval → ExecutionApproval/ExecutionEvent
```

每层使用 stable IDs、parent references、version/hash、policy/prompt/model version、timestamp、run ID 与 correlation ID。

### 16.2 Agent / LLM Trace

LangSmith 负责 LangGraph node、LLM invocation、tool call、token、latency 和错误。通过 metadata 与 domain IDs 关联，但不是业务 provenance 权威。默认 masking，敏感调用隐藏输入输出或关闭外部 tracing。

### 16.3 System Observability

MVP Hard Requirement 是 structured local logs、correlation/run IDs、liveness/readiness 和 privacy-safe LangSmith。OpenTelemetry 保留 seam；基础 FastAPI/SQLAlchemy spans 与少量 metrics 为时间允许项，不建设外部 backend、dashboard 或 alerting。

### 16.4 Retention

长期保存最小 lineage metadata。原始 prompt/response、ContextPackage diagnostic snapshot 和页面局部截图本地短期保存；Executor screenshot 默认 7 天。Cookie、Token、密码、Session secret 和无关页面内容禁止进入日志、trace 和 metrics。

## 17. 技术选型

| 技术 | 职责与边界 |
|---|---|
| Python 3.12 | Backend runtime |
| FastAPI | HTTP/API boundary，不承载领域逻辑 |
| Pydantic | 外部边界与 structured-output runtime validation |
| SQLAlchemy + SQLite | Authoritative relational persistence |
| Alembic | Schema migration |
| LangGraph | Bounded stateful material workflow |
| LangChain model interface | Provider/model integration，不做自动 routing |
| Chroma local persistent | 可重建 semantic vector index，不是事实来源 |
| LangSmith | Agent/LLM tracing，不是 domain lineage |
| React + TypeScript + Vite | Local SPA |
| Playwright | Web E2E/visual tests；Stretch browser adapter 的候选技术 |
| uv / Ruff / Pyright / pytest | Python reproducibility、style、typing、testing |
| ESLint / typescript-eslint / Prettier | Frontend lint/type-aware rules/formatting |

## 18. 演进边界

未来可能演进为 packaged local application，再到 Cloud Control Plane + Local Execution Agent。此时云端只下发窄业务意图；Cookie、Session 与本地文件仍不上传。当前不创建未来类或服务空壳，演进依靠 typed config、ports、versioned contracts、authoritative domain model 和可迁移数据。
