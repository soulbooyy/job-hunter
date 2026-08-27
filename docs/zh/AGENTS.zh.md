# AGENTS.md

本文件是方便开发者阅读的中文副本。编码代理必须读取仓库根目录英文版 `AGENTS.md`，详细规范以英文版 `docs/` 文档为准。

## 权威文档

- 产品范围与需求：`spec.zh.md`
- 架构、不变量与技术边界：`architecture.zh.md`
- TDD、代码规范与开发流程：`development.zh.md`
- Hard Gates、Quality Targets 与 Release Gates：`acceptance.zh.md`

发生冲突时，先停止实现并修正文档，不得自行选择更宽的权限或产品范围。

## 必须遵守

- 真实业务价值优先；技术不能仅为展示而进入主链路。
- AI 不得创造或修改未经 Candidate Knowledge 支持的职业事实。
- `QuickScreen` 与 evidence-grounded `DeepFitAnalysis` 必须分离。
- `MaterialApproval` 与 `ExecutionApproval` 必须分离；`Ready` 不代表允许外部执行。
- LangGraph 不得执行或自动重放浏览器外部副作用。
- Collector 和 Executor 默认关闭；不得实现验证码破解、风险码绕过或主动反检测。
- 外部数据必须在 adapter boundary 完成运行时校验，未经验证的数据不得写入领域状态。
- 核心 Python 与 TypeScript 业务代码保持严格类型；禁止让 `Any`、`unknown` 或第三方异常跨越边界传播。
- 先写失败测试或评测契约，再实现确定性业务能力；feasibility spike 不得未经 contract tests 进入 production path。
- 不读取、记录或上传 Cookie、Token、密码、浏览器 Session 或与任务无关的个人数据。

## 完成检查

提交实现前必须运行仓库统一检查入口 `./scripts/check`。在该脚本尚未创建前，使用 `docs/development.md` 中列出的等价命令。不得声称完成仍然失败的 Hard Gate。
