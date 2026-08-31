# Job Hunter 验收标准

## 1. 文档职责

本文件是方便开发者阅读的中文副本。上一级目录中的英文版 `../acceptance.md` 是 MVP 验收、质量目标和 Release Gate 的权威来源。具体数据集、rubric、runner 与报告存放在 `evals/`。

## 2. 验收模型

### 2.1 Acceptance Severity

| 类型 | 含义 | 未满足的后果 |
|---|---|---|
| Hard Gate | 核心业务、安全、正确性与可重复 verification | MVP 不完成 |
| Quality Target | AI 能力实际质量 | 必须报告，并限制默认启用、标记 experimental、缩小声明范围或记录 deviation |
| Stretch Release Gate | Collector/Executor 等可选外部能力 | 能力保持 disabled/不可用，不阻断核心 MVP |

### 2.2 Evaluation Environment

- Synthetic：边界、错误与不变量。
- Development/Replay：可重复迭代与 regression。
- Frozen Holdout：未参与调参的独立评估。
- Live/Real-world：真实 provider、BOSS 或实际使用。

不同环境单独报告，不计算混合总分。Hard Gate 不依赖 BOSS 网站即时状态或实时模型随机性。

## 3. Dataset Gate

### AC-DATA-001 — Minimum Dataset

Hard Gate：

```text
Development Set
- ≥20 realistic/replay Jobs
- ≥100 atomic Requirements

Frozen Holdout
- ≥10 Jobs
- ≥50 atomic Requirements
- 20%–30% atomic Requirements 为人工确认 No-Evidence

Synthetic Edge Cases
- ≥20 independent cases
```

### AC-DATA-002 — Governance

- 每个样本记录 source、generation method、human edits、split、annotation version 和 dataset version。
- Requirement Ground Truth 使用 stable EvidenceItem IDs，支持多标签与 `DIRECT/PARTIAL/BACKGROUND` graded relevance。
- `no_relevant_evidence=true` 必须人工确认，不能从空 judgments 推断。
- Holdout 个案一旦用于具体调参即视为泄漏，迁入 Development 并补充新 Holdout。
- Synthetic、Replay、Holdout、Live 单独报告。
- 报告必须声明样本规模有限，不能声称代表全部 AI 岗位。

### AC-EVAL-001 — Evaluation Foundation

- Invalid dataset structure、重复 ID、悬空 judgment、指向 eligible Evidence universe 之外的 judgment 和未人工确认的 No-Evidence 标签必须在 evaluation 开始前 fail closed。
- Full Context 与 Lexical/Metadata baseline 使用同一 eligibility input，保留准确 EvidenceItemVersion lineage，并在重复执行时保持确定性。
- Full Context 必须返回全部 eligible Evidence 或 `NOT_EXECUTABLE`，禁止静默截断。
- Completed retrieval run 的 selected-Evidence token estimate 必须满足 `max_tokens`，并分别报告 eligible-Evidence 与 selected-Evidence estimate。
- Retrieval 与 parser metric 必须匹配人工计算 fixture，包含 raw counts、priority per-class precision/recall/F1/support，以及 production/evaluation 共用的版本 metadata，且不得把 Candidate Evidence 内容复制进 report。
- `./scripts/eval-replay` 不依赖网络、数据库、model 或 browser，并明确说明 seed smoke fixture 不满足 AC-DATA-001。

## 4. Functional Hard Gates

### AC-JOB-001 — Source Independence

- ManualJDSource 与 ManualURLSource 可独立完成主链路。
- BossSource failure 不阻断已保存岗位和 downstream workflow。
- Source provenance、captured time 与 freshness 完整。

### AC-PERSIST-001 — 并发写入准入

持久化 Repository/UoW adapter 或任何允许 mutation 重叠的运行配置进入默认路径前，本 Hard Gate 开始适用。

- 在 deterministic scenario 中，两个 UoW 必须在任一方提交前读取同一个 entity version。
- 第一个有效 commit 成功；stale commit 不得静默覆盖，并返回稳定的 conflict/stale-version error contract。
- rejected commit 发生后，成功状态、immutable version history、active-version pointer 与权威 lineage 必须保持相互一致。
- Concurrent re-screen 与 Triage race 必须覆盖两种 commit order。基于同一 Job revision 时只能一个 operation 成功；loser 返回 `stale_write`、不留下 child row，也不能使 latest QuickScreen pointer 与 Triage decision 分离。
- 必须在获准持久化 adapter 的真实 coordination boundary 上运行该 gate。仅有进程内锁不足以证明多进程能力。
- 未通过该 gate 的 adapter 只能用于明确标注为 single-writer 的开发或测试配置。

### AC-PERSIST-002 — Restart Durability and Migration

- 空的临时 SQLite database 必须在不使用 `create_all()` 的情况下升级到当前 Alembic head，重复升级保持稳定。
- 一个 application lifespan 写入当前完整 Workspace path 并 dispose engine 后，使用同一 database 的新 lifespan 必须重建相同 active pointer、immutable history、derived read model 与 authoritative lineage。
- 两条真实 connection 必须证明：同一 UnitOfWork 在第一次 SELECT 后的重复 read 不会观察到另一 connection 的中途 commit。
- 失败 transaction 不得留下部分 Snapshot、Version、Requirement、Triage、Evidence 或 RetrievalRun row。
- Database/driver exception 与非法 persisted state 只能通过稳定 Job Hunter error taxonomy 跨越 adapter boundary，不得暴露 SQL text、parameter 或本地路径。
- 即使 serialized payload ID 与 association row 被同时篡改，composite relational constraint 与 hydration test 也必须拒绝错误的 Job/JobVersion/Requirement、Triage/QuickScreen/Job、RetrievalRun/Requirement/JobVersion，以及 EvidenceItem/EvidenceVersion ownership。
- Repository check 必须创建临时 database、升级到由 Alembic 推导的唯一 head，并在不读取或修改开发者 database 的前提下报告 metadata drift。

### AC-SCREEN-001 — Screening and Triage

- QuickScreen 只输出 `SCREEN_IN/SCREEN_OUT/UNCERTAIN`。
- QuickScreen recommendation 与 human decision 同时保留。
- Candidate Profile 更新不得改写或删除已有 QuickScreen result；每个历史结果都保留到实际使用 Profile snapshot 的可遍历 lineage。
- 面向用户的 screening read model 必须把基于非当前 Profile 的结果标记为 stale 并建议重新筛选，同时仍允许用户基于该结果继续 Human Triage。
- 重新筛选必须创建新的 QuickScreen result，不覆盖历史。
- 用户可以恢复/覆盖被过滤岗位。
- 只有 Shortlisted Job 进入 DeepFit 和材料工作流。

### AC-WORKSPACE-001 — Workspace Readback

- 空 Job、Profile 与 Evidence collection 返回 typed `200` response，不构造虚假 entity。
- 完成 deterministic mutation fixture 后，GET read model 必须无丢失、无乱序地重建 active pointer、immutable version、source/freshness lineage、ParsedRequirements、QuickScreen result 与 Triage decision。
- QuickScreen result 只因存在更新的 active Candidate Profile 而成为 `stale`；Profile staleness 本身不使 Triage 失去资格。
- 属于 historical JobVersion 或已不再 latest 的 result 仍可读取，但不得标记为 Triage-eligible。
- 未知 Job detail 返回稳定 `404` ErrorResponse，dependency failure 返回稳定 `503` contract，且敏感 read response 包含 `Cache-Control: no-store`。
- Readback test 可以证明 in-memory backend 仍存活时的浏览器刷新恢复，但不得声明 backend restart durability。

### AC-FIT-001 — Deep Fit Structure

- 成功解析的 atomic Requirement 全部拥有 stable requirement ID。
- 每项 DeepFit Requirement 归类为 `MATCHED/PARTIAL/MISSING/UNKNOWN`。
- `MATCHED/PARTIAL` 全部引用 supporting EvidenceItemVersion。
- `MISSING/UNKNOWN` 不伪造 Evidence；retrieval miss 不自动等于 MISSING。
- Structured Output 在 bounded repair 后仍无效时明确失败，不写入 Domain State。

### AC-HITL-001 — Human Gates

- Job Triage interrupt/resume 场景 100% 通过。
- Material Review interrupt/resume 场景 100% 通过。
- 事实冲突、敏感/unknown information 和低置信判断可触发 conditional interrupt。

Job Triage 验证 Application/Domain checkpoint；Material Review 验证 LangGraph interrupt/checkpoint。两者不要求共享同一状态机。

## 5. Retrieval Quality

### AC-RAG-001 — Hybrid Promotion Target

Frozen Holdout initial Quality Targets：

| Metric | Target |
|---|---:|
| EvidenceItem Recall@5 | ≥ 0.85 |
| Direct-Evidence MRR | ≥ 0.70 |
| No-Evidence Accuracy | ≥ 0.90 |

No-Evidence 同时报告 raw correct/total。Hybrid 未达到 threshold 时保留 implemented/experimental，但 RetrievalPolicy 不得默认选择它。

### AC-RAG-002 — Context Efficiency

对 eligible context 较大的样本：

| Metric | Target |
|---|---:|
| Context token reduction | ≥ 30% |
| Recall@5 degradation | ≤ 5 percentage points |
| No-Evidence degradation | ≤ 2 percentage points |

Full Context runtime feasible 时直接比较；不可执行时使用离线 eligible full-evidence reference。Eligibility scope 必须相同。

### AC-RAG-003 — Retrieval Correctness Hard Gates

- Claim provenance coverage = 100%。
- Metric runner、dataset、retriever/policy version 和参数可复现。
- Hybrid 未达标时 fallback 可验证。
- Bounded Agentic RAG 最多一次 reformulation；不足时输出明确 no/insufficient evidence。

## 6. Parser 与 Fit Quality Targets

| Metric | Initial Target |
|---|---:|
| Atomic Requirement Recall | ≥ 0.90 |
| Atomic Requirement Precision | ≥ 0.85 |
| Requirement Priority Macro-F1 | ≥ 0.85 |

Priority classes 为 `REQUIRED/PREFERRED/UNSPECIFIED`。报告必须包含各类别 raw counts/per-class metrics。Human Acceptance Rate 与 Override Rate 只观察和报告，暂不作为 Hard Gate。

QuickScreen 使用独立轻量 evaluation，不与 DeepFit 指标混用。

## 7. Resume Grounding Hard Gates

### AC-RESUME-001 — Provenance and Support

| Invariant | Gate |
|---|---:|
| factual claim provenance coverage | 100% |
| validator-known unsupported claims | 0 |
| unapproved high-risk inference | 0 |
| failed/unresolved validation entering Ready | 0 |
| Approval ↔ ResumeVersion/artifact hash match | 100% |

### AC-RESUME-002 — Manual Holdout Review

Frozen Holdout 对所有 factual claims 进行人工 claim-level review：unsupported factual claim rate = 0%。发现一个 unsupported claim 即失败；修复时将该 case 迁入 Development 并补充新 Holdout。

报告只能声称“在 dataset/version X 的 Holdout 中未发现 unsupported factual claims”，不得声称系统永不 hallucinate。

## 8. Context Management

### AC-CTX-001 — Hard Gates

| Invariant | Gate |
|---|---:|
| protected-entry loss | 0 |
| ContextReference rehydration correctness | 100% |
| provenance continuity | 100% |
| unsupported factual claims introduced by compaction | 0 |
| silent truncation | 0 |

Protected context 仍超预算时必须返回 `CONTEXT_BUDGET_EXCEEDED`。

### AC-CTX-002 — Stress Benchmark Quality Targets

| Metric | Target |
|---|---:|
| active-context token reduction | ≥ 25% |
| effective Evidence Recall degradation | ≤ 5 percentage points |
| workflow completion degradation | ≤ 5 percentage points |

报告应展示不同 workload 的 token-saving/quality-loss trade-off。

## 9. Workflow 与 Capability Policy Hard Gates

以下 deterministic scenarios 必须 100% 通过：

- 所有已定义 legal conditional routes；
- 所有已定义 illegal state transitions 被拒绝；
- Job Triage 和 Material Review interrupt/checkpoint/resume；
- repair attempts ≤ 2；
- checkpoint recovery 不重复生成或持久化已固化版本；
- 未授权 NodeToolPolicy call 被拒绝；
- tool-call、iteration、timeout、token/cost 与 result-size budget 被执行；
- Graph-triggered browser external side effects = 0；
- valid run_id/correlation_id coverage = 100%。

Timeout 与 budget tests 使用 deterministic/fake timing，避免 CI flaky。

## 10. Traceability Hard Gates

### AC-TRACE-001 — Traversable Lineage

每条最终 factual ResumeClaim：

- 到 EvidenceItemVersion 的语义合法路径 = 100%；
- 到 ParsedRequirement/JobVersion = 100%；
- 到 ValidationResult/ResumeVersion = 100%。

AI-generated/rewritten factual claims 还必须 100% 遍历到 ContextPackage/ModelInvocation。Human-authored/edited claim 记录 human provenance，不伪造 ModelInvocation。

进入 Ready 的 ResumeVersion 必须 100% 遍历到有效 MaterialApproval。

### AC-TRACE-002 — Corruption Rejection

以下负向场景必须 fail closed：

- missing parent/reference；
- wrong artifact hash；
- cross-job Evidence binding；
- broken version reference；
- stale/invalid MaterialApproval；
- 使用 MaterialApproval 冒充 ExecutionApproval；
- ExecutionApproval 引用失效 MaterialApproval。

测试必须验证 reference existence、target/version/hash match、semantic validity 和完整 traversal，而非仅检查非空 ID。

## 11. Approval Hard Gates

- MaterialApproval 与 ExecutionApproval 使用不同类型和验证逻辑。
- Ready 不表示 execution permission。
- MaterialApproval 不能被 Executor 消费。
- ExecutionApproval 必须引用有效、hash/version 一致的 MaterialApproval。
- Material mutation 使 MaterialApproval 和未消费 ExecutionApproval 失效。
- ExecutionApproval 必须 single-use、scope-bound、time-bound。
- 已消费 Approval 不篡改历史；后续操作需要新 Approval。

## 12. Rendering Hard Gates

相同 Resume IR、template version 和 renderer version 必须产生一致语义内容与布局。Template A 至少包含 5 个不同内容密度的 golden fixtures，并满足：

- required fields 无丢失；
- 无重叠、裁切和不可见 required text；
- 指定 fixtures 保持一页；
- PDF text extraction 与 ResumeClaim 内容一致；
- visual regression 在预定义容差内通过；
- PDF 与 PNG 均可导出。

不要求 PDF byte-level reproducibility。MaterialApproval 必须绑定实际展示 artifact 的 hash。

## 13. Web Workspace Hard Gates

Playwright deterministic CI 使用 fake/replay 后端覆盖：

1. ManualJDSource fixture → normalize → inspect → triage；
2. BossSource normalized fixture → 相同 downstream workflow；
3. Shortlist → Evidence Retrieval/DeepFit → material generation；
4. Resume IR edit → preview/diff → validation → MaterialApproval；
5. PDF/PNG export → Ready。

失败路径至少覆盖 no Evidence、structured-output failure、stale/invalid Approval 和 backend unavailable。CI 不访问真实 BOSS 或真实 LLM。

## 14. Runtime Budget

### AC-BUDGET-001 — Mechanism Hard Gate

Fit 与 Material Workflow 必须拥有可配置、版本化、可观察且由 runtime 强制的 latency、model-call、token/cost budget。超限时停止或暂停并给出明确状态；不得无限 retry、静默突破预算或自动切换未经验证模型。

每次运行记录实际 latency、calls、tokens 和 cost。

### AC-BUDGET-002 — Policy v1

具体阈值在 primary model feasibility benchmark 后冻结。90 秒/5 calls、3 分钟/10 calls、US$0.50 仅作为 starting hypotheses，不是当前 Hard Gate。BudgetPolicy v1 必须在对应 capability 默认启用前写入 versioned config 和 evaluation report。

## 15. Privacy and Security Hard Gates

- API key、Cookie、Token、密码、Session secret 和无关页面内容不得进入 logs/traces/metrics。
- 外部 LangSmith trace 默认不上传完整 Candidate Profile、Resume、Evidence 或 PII。
- 敏感 invocation 可关闭 input/output tracing。
- 原始 prompt/response 和 diagnostic artifact 遵循本地 retention/redaction。
- 用户隐私删除可真正移除敏感原文，只保留最小 tombstone。
- Collector/Executor 默认关闭，不实现 CAPTCHA/risk bypass 或主动反检测。
- 普通 Agent tool loop 无 external side effect、Shell 或通用代码执行权限。

使用 canary secret/PII fixtures 验证 redaction 与禁止日志行为。

## 16. BossSource Stretch Release Gate

启用前必须全部满足：

- immutable SHA、lock、license/admission record 完整；
- adapter contract fixtures 100% 通过；
- malformed/schema-drift output 在 domain write 前拒绝；
- CAPTCHA、风险码、登录异常和未知结果 fail closed；
- 默认关闭且 live smoke 只能由用户显式运行；
- source、captured_at、freshness 与 adapter version 可追踪；
- live failure 明确并提供 Manual Import fallback。

不承诺覆盖率、长期成功率、anti-bot resilience 或 always-on availability。

## 17. Browser Executor Stretch Release Gate

标记 `experimental enabled` 前必须全部满足：

- 默认关闭、单任务、visible browser、用户显式开始；
- Approval scope/hash/expiry checks 100%；
- idempotency tests 100%；
- partial-success failure-injection tests 100%；
- automatic retry disabled；
- CAPTCHA/rate limit/unknown page state 立即熔断；
- dry-run/simulation 100%；
- 至少一次用户明确批准的真实单岗位执行，由 read-back 证明预期外部效果。

未满足时可以保留代码或 feasibility report，但 UI 不提供执行入口。

## 18. MVP Completion

核心 MVP 完成需要：

1. 所有 Hard Gates 通过；
2. 所有 Quality Targets 已测量、版本化并报告；
3. 未达 Quality Target 的 capability 应用明确 consequence；
4. `./scripts/check` 和可重复 replay evaluation 通过；
5. README、Spec、Architecture、Development、Acceptance 与实现一致；
6. Stretch capability 未通过 gate 时保持关闭；
7. 不把 synthetic/replay 指标表述为真实 Time-to-Application 提升。

进入真实使用后才采集人工 Time-to-Application baseline，并分别记录 screening、analysis、tailoring、preparation 和 form-filling 时间。业务提效声明必须基于真实使用对照，而不是 synthetic benchmark。

## 19. Requirement Traceability Matrix

| Spec Requirement | Primary Acceptance Evidence |
|---|---|
| REQ-JOB-001 / REQ-JOB-002 / REQ-JOB-005 / REQ-JOB-006 | AC-JOB-001、Web Workspace path 1、source/freshness contract tests |
| REQ-JOB-003 / REQ-JOB-004 | BossSource Stretch Release Gate、adapter/three-way screening tests |
| REQ-WORKSPACE-001 | AC-WORKSPACE-001、backend read-model contracts、browser-reload tests |
| REQ-PERSIST-001 | AC-PERSIST-001/002、migration/restart/repository contract tests |
| REQ-EVAL-001 | AC-DATA-001/002、AC-EVAL-001、reproducible replay reports |
| REQ-KNOW-001 / REQ-KNOW-002 | Dataset Gate、AC-RAG-003、AC-TRACE-001/002 |
| REQ-RAG-001 / REQ-RAG-002 | AC-RAG-001/002、fallback and policy-version tests |
| REQ-RAG-003 / REQ-RAG-004 | AC-RAG-003、budget/eligibility/no-evidence tests |
| REQ-CTX-001 | AC-TRACE-001、ContextPackage schema/redaction/token tests |
| REQ-CTX-002 | AC-CTX-001/002 |
| REQ-AGENT-001 | AC-HITL-001、Workflow/Capability Policy Hard Gates |
| REQ-AGENT-002 / REQ-AGENT-003 / REQ-AGENT-004 | Workflow/Capability Policy Hard Gates、Privacy/Security Hard Gates |
| REQ-RESUME-001 / REQ-RESUME-002 | AC-RESUME-001/002、AC-TRACE-001/002 |
| REQ-RESUME-003 | Rendering Hard Gates、Web Workspace paths 3–5 |
| REQ-HITL-001 / REQ-HITL-002 | AC-SCREEN-001、AC-HITL-001、Web Workspace paths 1–4 |
| REQ-APPROVAL-001 / REQ-APPROVAL-002 / REQ-APPROVAL-003 | Approval Hard Gates、AC-TRACE-002、Browser Executor Release Gate |

新增或变更稳定 Requirement ID 时，必须同步更新本表或提供等价的机器可追踪映射。
