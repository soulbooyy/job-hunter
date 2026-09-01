# Job Hunter

Job Hunter 是一个面向个人求职场景的本地优先 AI Job Application Workspace。它把职位采集、低成本筛选、人工决策、Career Evidence Retrieval、岗位匹配分析、定制材料生成、事实校验和申请跟踪组织成一条可追溯的半自动工作流。

项目的核心约束是：AI 可以发现、分析、检索、起草和校验；用户保留求职决策、事实确认、材料批准和所有外部动作的最终控制权。

## MVP 主链路

```text
Collect / Import
→ Normalize / Deduplicate
→ Parse Requirements
→ QuickScreen
→ Human Job Triage
→ Shortlisted
→ Evidence Retrieval
→ DeepFitAnalysis
→ Material Preparation
→ Validation / Bounded Repair
→ Human Material Review
→ Ready
```

BOSS 单岗位投递与结果回读属于 Stretch Goal。即使实现完成，也必须通过独立安全、幂等和回读验证门槛后才能启用。

## 项目定位

- 第一阶段为深圳地区 AI Agent / LLM Application Engineer 岗位服务。
- AI Backend Engineer 与 AI Full-stack Engineer 可以使用通用能力维度和初步权重，但不属于 MVP 正式效果声明范围。
- Career RAG、LangGraph、Context Engineering 和 Human-in-the-loop 都必须解决明确问题并接受评测。
- 不实现无人值守批量投递、验证码绕过、主动反检测、通用代码执行或多租户 SaaS。

## 文档

- [产品规格](spec.zh.md)
- [系统架构](architecture.zh.md)
- [开发规范](development.zh.md)
- [验收标准](acceptance.zh.md)

英文文档是 Codex 与自动化的权威来源；`docs/zh/` 下的中文版仅供开发者阅读。中文文档职责为：`spec.zh.md` 定义要构建什么，`architecture.zh.md` 定义如何设计，`development.zh.md` 定义如何开发，`acceptance.zh.md` 定义如何证明完成。

## 当前状态

本地 Manual Job → QuickScreen → Human Triage workspace 与 backend readback 路径已经建立。默认 backend 使用显式 migration 管理的 SQLAlchemy/SQLite store，提供跨重启 Workspace state 与 stale-writer rejection。后端同时包含 deterministic Full Context 与 Lexical/Metadata baseline、可选且可重建的本地 Chroma semantic derivative、记录 policy lineage 的 Hybrid retrieval、immutable RetrievalRun，以及具备预算和脱敏语义的 ContextPackage persistence。由于尚无合格的人工审阅 Frozen Holdout 通过 promotion gate，Hybrid 仍为 experimental，默认策略不会选择它；滚动状态以英文 `../progress.md` 为准，该文档按项目规则不提供中文副本。

`./scripts/setup` 安装默认 locked dependency 并升级本地 database；`./scripts/db-upgrade` 只执行 database migration。Application startup 校验当前 Alembic head，并有意不自动迁移。仓库完整验证使用 `./scripts/check`，其中包括隔离 locked Chroma adapter 检查。`./scripts/semantic-setup` 是显式且校验 checksum 的本地模型获取步骤；普通 setup 和 request handling 均不会下载模型。Deterministic seed evaluation 使用 `./scripts/eval-replay`，显式本地模型 synthetic Hybrid evaluation 使用 `./scripts/hybrid-eval`。两份 synthetic report 都不满足 curated Development/Frozen Holdout Dataset Gate，也不能支持产品质量声明。
