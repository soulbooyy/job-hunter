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

项目处于规格与架构冻结后的初始实现阶段。代码、依赖版本、第三方依赖 SHA 和模型预算将在对应 feasibility spike 与 TDD 实现中逐步落地。
