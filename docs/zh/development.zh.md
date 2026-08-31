# Job Hunter 开发规范

## 1. 文档职责

本文件是方便开发者阅读的中文副本。上一级目录中的英文版 `../development.md` 是开发流程、TDD 策略、工程约束和开发命令的权威来源。架构规则参见中文版 `architecture.zh.md`；机器配置仍是格式、lint 和类型细节的最终权威。

## 2. 开发原则

1. 从可用纵向切片开始，不按技术层横向堆积。
2. Feasibility before dependency commitment。
3. TDD-first，但测试方式与系统层次匹配。
4. Deterministic control before probabilistic quality。
5. 数据集、rubric 与 baseline 先于 prompt 调优。
6. 每次实现必须保留 requirement、test/eval 和 traceability 的映射。
7. 核心 MVP 优先；Collector 与 Executor 不能阻塞材料工作区。
8. 未通过 admission/release gate 的能力默认关闭。

## 3. 实现依赖顺序

以下是依赖顺序，不绑定日期或每日工时：

1. Repository scaffold、toolchain、CI、typed config 与核心 IDs。
2. Domain model、versioning、lineage、Repository/UoW 与 Manual Job Sources。
3. Candidate Profile、EvidenceItem/Version、Requirement parsing、QuickScreen 与 Workspace readback。
4. Evaluation datasets、fake model、baseline retrievers 与 metric runners。
5. SQLAlchemy/SQLite persistence、Alembic migration、restart durability 与 concurrent-write admission。
6. Chroma feasibility、Hybrid Retriever、RetrievalPolicy 与 ContextBuilder。
7. RuntimeContextManager、Capability Policy 与 LangGraph typed workflow。
8. DeepFit、ResumeClaim、validation/repair 与 MaterialApproval。
9. Structured Resume Editor、Template A、PDF/PNG 和关键 E2E。
10. Boss Collector adapter 与独立 Stretch Release Gate。
11. Browser Executor feasibility 仅在核心 Hard Gates 全部稳定后开始。

## 4. Scope-cut 顺序与停止规则

出现时间或复杂度压力时，按以下顺序缩减：

1. Browser Executor 不实现或保持 disabled。
2. Template B 延后，只保留 Template A。
3. OpenTelemetry instrumentation、额外 metrics 延后。
4. Boss live integration 保持 adapter/fixture 或 disabled，Manual Import 继续工作。
5. 相邻职位族只保留未校准的通用能力，不作效果声明。

不得削减：

- Evidence-grounded claim 与零 unsupported-claim gate；
- QuickScreen/DeepFit 分离；
- 两个人工 Gate；
- MaterialApproval/ExecutionApproval 分离；
- bounded repair/tool/retrieval/context；
- domain lineage、版本与 hash；
- privacy、fail-closed 和外部副作用边界；
- deterministic test Hard Gates。

Feasibility 结果无法证明安全、契约稳定或基本可用时，停止对应能力并记录结论，不通过增加反检测、通用权限或无界重试绕过问题。

## 5. TDD 策略

### 5.1 Domain、Policy 与 Contract

严格遵循 Red → Green → Refactor：

- 先用最小失败测试描述状态、不变量或 contract；
- 实现最少代码使测试通过；
- 在全套测试通过时重构；
- bug fix 必须先增加可复现 regression test。

适用范围包括状态转换、approval validity、version/hash、claim grounding、eligibility、deduplication、budget、adapter normalization 和 error mapping。

### 5.2 持久化与并发写入

不得根据 Repository/UoW 的形式，或单个测试事务中的原子行为，推断系统具备并发保证。持久化 adapter 或允许重叠写入的 runtime 获准进入默认路径前：

- 先冻结 expected-revision/active-version contract 及其 conflict mapping，再开始实现；
- 编写 deterministic test：两个 UoW 从同一版本开始，第一个提交后，stale commit 不得静默覆盖；
- 验证冲突发生后，成功提交的状态仍保留完整 immutable history 和权威 lineage；
- 一旦内存 fake 在 concurrency-sensitive test 中替代已获准的 adapter，必须对两者运行相同的 observable contract；
- 必须在真实 coordination boundary 上测试，例如数据库事务或约束；仅测试进程内锁不能证明多进程支持。
- 使用两条真实 connection 证明 read UnitOfWork 在另一 connection commit 后仍保留同一 snapshot；framework Session flag 本身不能证明 SQLite transaction state；

只要限制被明确记录且未启用不受支持的并发配置，当前内存 adapter 可以继续保持 single-writer，并比未来持久化 adapter 更简单。

每个 UnitOfWork 都是 one-shot；commit、rollback 或成功 read 后都必须在 `finally` path 显式 close。Persistence test 使用临时 database file 与真实独立 connection，不复用或删除开发者配置的 database。

同步 SQLAlchemy use case 必须由同步 FastAPI handler 或显式 worker-thread boundary 调用。不得在 async route 中直接执行 blocking database work。

Read-model test 必须覆盖 deterministic ordering、active pointer、immutable history、cross-entity lineage、empty collection、稳定 not-found behavior 与派生 actionability。浏览器刷新恢复声明必须有 contract evidence 证明 mutation result 可由 backend GET response 重建；该声明不代表 backend restart durability。

### 5.3 LangGraph

先测试 typed state、legal/illegal routes、conditional repair、interrupt/checkpoint/resume 和预算。使用 FakeModel、FakeTool、FixedClock 与 DeterministicIdGenerator。单元/集成测试不得依赖真实 provider。

### 5.4 RAG、Prompt 与 LLM

采用 evaluation-driven development：

```text
Dataset
→ Annotation / Rubric
→ Baseline
→ Candidate Implementation
→ Error Analysis
→ Frozen Holdout Evaluation
```

Development Set 可以迭代；Holdout 泄漏后必须迁移并补充新样本。禁止根据 Holdout 个案直接调 prompt/threshold 后继续把它称为未见数据。

Evaluation foundation 在实现前必须用测试冻结 dataset validation、reference integrity、active-version ownership、eligibility exclusion 与 judgment eligibility、deterministic ranking/tie-break、Full Context 完整性、无静默截断的 retrieval-budget accounting、包含 parser per-class metric 的精确 metric arithmetic，以及 production/report 共用的 version metadata。Seed synthetic fixture 必须保持小规模并明确标记为 runner smoke data，不能作为 Dataset Gate 证据。Replay/fake model adapter 只有在 evaluation runner 或 contract test 实际执行时才允许存在；它不能证明未使用的 production abstraction 有必要，也不能把 live dependency 带入 deterministic CI。

### 5.5 Rendering

使用 typed Resume IR fixtures、结构断言、PDF text extraction 和 visual golden regression。避免用 PDF binary hash 作为唯一 determinism 指标。

### 5.6 Frontend

对关键交互写 component/E2E tests：Job ingestion/triage、Evidence/DeepFit、Resume edit/preview/diff、validation/approval/export 与必要失败路径。不强迫每个 CSS 细节 unit-test-first。

### 5.7 Third-party Spike

Scraper、Chroma packaging 和 Browser Executor 可以先做 bounded spike。Spike 必须：

- 有明确问题、时间/范围上限和退出条件；
- 隔离在 production path 外；
- 不处理真实外部副作用，除非用户逐次批准；
- 记录观察事实和风险；
- 行为稳定后先冻结自有 contract/characterization tests，再转 production；
- 未满足 admission gate 时删除、隔离或保持 disabled。

## 6. 测试轨道

### Fast Deterministic CI

Fake model、domain、contract、workflow、repository、rendering invariants、frontend unit/component 和 mock-backed E2E。它是普通变更的 Hard Gate。

### Replay Evaluation

固定或录制的 structured model output、golden dataset、prompt contract、retriever comparison 和 workflow quality regression。可重复部分可以进入 CI/release gate。

### Live Evaluation

真实 provider/model、显式启动的 Boss smoke 和用户批准的 executor validation。手动、定期或 release 前运行，按环境单独报告；除非指标后来证明稳定，否则不作为每次提交的 CI gate。

## 7. Python 工程规范

- Runtime：Python 3.12；使用 uv，提交 `backend/uv.lock`。
- Layout：`backend/src/job_hunter`；pytest 使用 importlib import mode。
- Formatting/lint/import sorting：Ruff stable mode。不得同时加入 Black/isort/Flake8。
- Typing：Pyright strict 是唯一 Python static-type authority。
- External input 可以短暂为 `Any`，但必须在 adapter/IO boundary 立即通过 Pydantic 或显式 parser 转为 typed contract。
- `Any` 不得传播到 Domain、Application、LangGraph State、Retrieval、Context 或 persistence 核心。
- `# type: ignore` 必须局部、带具体错误码与理由；禁止 file/global ignore 掩盖业务错误。
- LangGraph State 使用 TypedDict/Pydantic 等明确 contract，不使用 `dict[str, Any]`。
- Migrations、generated 和受控 third-party code 可以单独排除。
- 使用 constructor injection；FastAPI `Depends` 只在 API composition boundary 使用。
- 共享 repository 或 transaction 的 application-scoped use case 必须作为一个完整 typed composition bundle 注入；不得提供可能静默拆分 dependency graph 的逐项 partial override。
- 时间、ID、model、repository、artifact、collector 和 executor 通过 seam 注入，测试不得依赖 wall clock 或随机 ID。
- UnitOfWorkFactory acquisition 必须包含在 Application error boundary 内。未知 acquisition failure 不得泄漏原始细节，且只有实际创建 UnitOfWork 后才调用 rollback。
- 从 dynamic framework state 读取 dependency 时，必须在 API boundary 进行 runtime validation；`cast()` 可以辅助 static typing，但不能证明运行时正确性。
- 在出现确实需要共享 Protocol 的非子类实现或测试替身之前，保持具体 Application Use Case 作为注入类型。触发条件出现后，应定义并用 contract test 验证窄 Protocol，一致地更新 composition typing，同时保留明确的 runtime guard。

## 8. Frontend 工程规范

- React + TypeScript + Vite；MVP 不引入 Next.js 或 Electron。
- TypeScript `strict`、`noUncheckedIndexedAccess`、`exactOptionalPropertyTypes`。
- 外部 JSON/API response 必须 runtime validate，禁止仅靠类型断言。
- ESLint 使用 flat config 与 typescript-eslint；Prettier 只负责格式，不重复 lint 规则。
- UI 不直接依赖 backend Python 实现，只依赖 versioned HTTP contract。
- API client、domain view model 与 component state 分离；不得在 component 内复制后端业务规则。
- 面向用户的文案默认使用简体中文，包括标签、控件、状态与错误反馈、可访问名称和解释文本。`Job Hunter`、`Candidate Profile`、`QuickScreen`、`DeepFit`、`Evidence`、`RAG` 等既定产品/领域/技术名称，以及序列化 API 枚举值、版本和 ID 保持原样；不得把机器 contract 值翻译成另一套前端事实。
- Playwright 测试用户可见行为，使用可访问 locator，mock 第三方服务。

## 9. 架构编码规则

- Route/Controller 不包含业务规则、SQL、LLM、Chroma 或浏览器代码。
- Application Use Case 管理一次业务操作和事务边界。
- Domain 不导入 FastAPI、SQLAlchemy、LangGraph、Chroma、LangChain 或 Playwright。
- SQLAlchemy model 不作为跨层领域 API。
- Pydantic DTO、Domain Model、Persistence Model 仅在边界真实需要时分离，不机械复制。
- LangGraph Node 负责编排 typed state 和调用 application capability，不直接操作基础设施。
- 第三方异常不得越过 adapter boundary。
- 禁止通用 Shell、JavaScript、selector、SQL 和 filesystem tool 暴露给模型。
- 未经运行时 validation 的模型/第三方输出不得写入 Domain State。

## 10. 错误与失败语义

错误 taxonomy 至少区分：validation、policy denial、budget exceeded、not found、conflict、stale version、invalid approval、dependency unavailable、login/auth anomaly、schema drift、timeout、rate/risk signal、partial external success 和 unknown external result。

未知外部结果必须 fail closed。不得用 broad `except` 把失败伪装为成功，不得在 application/domain 中传播第三方异常字符串作为业务状态。

## 11. Dependency 管理

- Python 与 frontend dependency 必须使用 lockfile；升级是显式变更。
- 不启用 Ruff preview 或不稳定工具行为，除非单独批准。
- 一个语言只保留一个 formatter 和一个主要 type authority。
- 第三方依赖进入 runtime 前检查许可证、维护状态、固定版本能力、接口、安全权限和可替换性。
- `third-party/` 保存 dependency identity、immutable SHA、license/admission notes、patch metadata 和 contract version；不得把凭据或复制的 browser profile 放入仓库。
- Vendor patch/fork 必须经过用户明确批准，并保留上游 SHA、patch、原因和重新验证证据。

## 12. Git 与变更流程

- 一个变更保持单一清晰目的；不得混入无关重构。
- Commit message 说明业务行为或架构边界变化，不描述“修改了一些文件”。
- 修改需求、架构、Hard Gate 或安全边界时先更新权威文档，再实现。
- 新 requirement 使用稳定 ID；相应 test/eval 应引用该 ID 或能够通过 acceptance matrix 追踪。
- 不提交 secrets、真实 Cookie、浏览器 Profile、未经脱敏的个人数据、临时 diagnostic artifact 或短期截图。

## 13. 统一开发命令

根目录必须提供统一脚本，底层具体命令可随 scaffold 调整，但语义保持稳定：

```text
./scripts/setup          install locked backend/frontend dependencies
./scripts/db-upgrade     upgrade the configured local SQLite schema
./scripts/db-check       verify Alembic head and metadata against a temporary database
./scripts/dev            start local FastAPI and Vite
./scripts/check          all deterministic checks
./scripts/eval-replay    reproducible replay evaluation
./scripts/eval-live      explicit live evaluation; never implicit
```

`./scripts/check` 至少执行：

```text
Backend format check
Backend lint
Pyright strict
Backend deterministic tests
Frontend format/lint/typecheck
Frontend deterministic tests/build
Selected mock-backed Playwright E2E
```

Pre-commit 只运行低延迟 formatter/linter。CI 运行与 `./scripts/check` 等价的 locked verification，不维护另一套命令。

## 14. Completion Checklist

实现者在声称 feature 完成前必须确认：

- 对应 Spec requirement 和 Acceptance criterion 已存在；
- 先有失败测试/eval contract，再有实现；
- 新外部数据有 runtime validation；
- 类型、lint、format 和 deterministic tests 通过；
- lineage、version、hash 和 privacy 行为已覆盖；
- 错误、预算与边界失败为显式状态；
- 文档与实际行为一致；
- 未通过 Quality Target 的 capability 已应用规定后果；
- Stretch capability 未通过 Release Gate 时保持关闭。
