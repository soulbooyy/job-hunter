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

### 5.2 Application

Use Case 表达一次完整业务意图，例如 `ImportJob`、`RunQuickScreen`、`ShortlistJob`、`PrepareMaterials`、`ApproveMaterials` 和 `AuthorizeExecution`。Application 管理事务边界和 port 协作，不拥有外部 SDK 细节。

### 5.3 Domain

Domain 拥有稳定实体、value object 与 policy，包括 Job/JobVersion、Requirement、Evidence、ResumeClaim、Approval、状态迁移、evidence eligibility、deduplication、claim grounding 和 approval validity。

### 5.4 Infrastructure

SQLAlchemy、SQLite、Chroma、LangChain provider、scraper、renderer、artifact store 和 browser 是 adapter。第三方异常必须在 adapter boundary 映射为 Job Hunter error taxonomy。

### 5.5 Port 规则

只为真实替换点或测试 seam 定义 Port，例如 Repository、UnitOfWork、ModelGateway、EvidenceRetriever、Clock、IDGenerator、ArtifactStore、Collector、Renderer 和 Executor。普通内部 helper、policy 或 value object 不创建形式主义 interface。

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

### 9.3 Deterministic Retrieval Policy

- eligible tokens 在校准阈值内：Full Context；
- identifier/certificate/named project/skill：Lexical + Metadata；
- semantic requirement-to-experience：Hybrid；
- 多个条件同时满足时使用固定 precedence。

每次运行记录 policy version、输入统计、selected strategy 和原因。Hybrid 未达到 promotion threshold 时保留为 experimental，并回退到 Full Context 或 Lexical。

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

影响生成、审批或执行的实体采用版本化；snapshot 型记录一旦创建即 immutable。Logical entity 只维护 active-version pointer。用户隐私删除可以真正删除敏感原文或文件，但保留不含敏感内容的 entity/version ID、删除时间、原因和必要 hash tombstone。

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
