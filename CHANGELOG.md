# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project follows [Semantic Versioning](https://semver.org/).

---

## [1.3.0] — 2026-05-27

### Added
- **`phase1-prototyping.md`**：Phase 1 原型化子流程独立文件。检测低保真信号（用户连续 ≥2 次"我不确定/你做一个我看看"）后，主对话派发原型 sub-agent 把决策点具象化，再基于 readout 重提决策点。包含信号检测规则、类型/Mode 决策树、默认升级路径（Viz → Shape → Spike）、派发参数模板、回流契约、`prototypes/YYYY-MM-DD-NNN-<slug>/` 命名规范
- **`worker-prototype-frontend.md`**：前端原型 sub-agent prompt。镜像 QA Agent 风格（Phase 级、只读、不产 PR），产出单 HTML + Tailwind CDN 可交互原型 + ≤200 字 readout
- **`worker-prototype-backend.md`**：后端原型 sub-agent prompt，单文件三模式由派发方注入。**Viz**（Mermaid sequence/state/ER/flow）/ **Shape**（Pydantic / SQL / OpenAPI 草图 + 示例数据）/ **Spike**（≤50 行可运行 Python 脚本，Phase 1 慎用）。严禁跨 Mode 越权
- **`docs/glossary.md`** 子文档加入 `PROJECT_CONTEXT_TEMPLATE.md`：领域术语规范表（规范词 + `_Avoid_` 近义词 + 关系 + 已标记歧义），Phase 1 词语精度 pass 时 inline 写入

### Changed
- **`phase1.md`** 重写为模块化渐进对齐流程：
  - 顶部锚定原则：一次只问一个问题、每个问题附 AI 推荐答案 + 一句理由、不设提问上限（由用户在闸门主动按"满意"才推进）、每轮显示进度面包屑（`[模块 N/M: 名] · 当前层级: X · 已锁定: K · 待决策: J`，K/J 为非负整数）
  - **Step A** — 产品全貌 + 模块切分草案（不预设模板，AI 现场判断）+ 锁定握手必经
  - **Step B** — 模块内三层渐进提问（Big Picture → 行为 → 细节）+ 词语精度 inline 写入 `docs/glossary.md` + 场景压测（编 2-3 个边界场景）+ 低保真触发原型化
  - **Step C** — 模块切换闸门，每锁定一个模块前先写入 `PRD-draft.md`
  - **Step D** — 全模块完成后输出冻结 PRD（`PRD.md`），人类可读不强制 schema
  - 跨会话状态恢复协议（PRD-draft 顶部嵌入进度元信息）+ 术语重审规则 + Phase 2 回流增量更新
  - 用户主动 opt-out B.3 场景压测时，必须 surface 该 opt-out 为已锁定决策，不静默跳过
- **`PROJECT_CONTEXT_TEMPLATE.md`**：子文档目录新增 `docs/glossary.md`，新增 `prototypes/` 与 `PRD-draft.md` 的 `.gitignore` 指引
- **`dev.md`** Phase 1 一行描述：模块化渐进对齐 + 词语精度沉淀 + 必要时原型驱动，无上限提问由用户掌控闸门，冻结 PRD 作为 Phase 2 输入

### Tested
- 4 个场景模拟对话（冷启动 AI Agent / 原型触发 / 已有 PRD 情况 A / 后端 Viz→Shape 升级）+ 1 个真实文件系统 case（CLI markdown summarizer）。经过 5 轮迭代修复后所有场景 PASS

---

## [1.2.0] — 2026-03-30

### Added
- **`phase5.md`**：Phase 5 独立文件，包含完整的 Retro + 技术债清扫流程。技术债清扫分三步：2a 死文档清查（git log 辅助 + 引用对象验证）、2b 废弃代码清查（注释代码块、零调用方函数、固化 feature flag、过期 TODO/FIXME）、2c 失效功能登记；清扫后输出结构化报告
- **渐进式文档结构**：`PROJECT_CONTEXT_TEMPLATE.md` 重构为 index + 子文档模式，主索引 ≤ 35 行仅做路由，技术内容分散至 `docs/tech-stack.md`、`docs/architecture.md`、`docs/api-contracts.md`、`docs/style-guide.md`、`docs/feature-log.md`，每个子文档保持 100–200 行

### Changed
- **`dev.md`**：Phase 5 入口改为引用 `phase5.md`（与其他 phase 保持一致）；全局规则中 `PROJECT_CONTEXT.md` 更新说明改为「架构决策变化时立即更新对应子文档，每轮结束后更新主索引 + feature-log」
- **`phase3.md`（zh/en）**：进度报告格式升级为任务看板（Task Board），包含分支名、Issue 号、状态字段，每次 PR 创建后重新输出完整看板；状态枚举：进行中 / PR 已创建 / 阻塞
- **`install.sh`**：修复漏复制 `phase3.5.md` 和 `phase5.md` 的 bug

---

## [1.1.0] — 2026-03-24

### Added
- **轻量模式 (Lightweight Mode)**：Phase 0 新增轻量模式路由。满足「文件 ≤ 2 个、无新对外接口、无 schema 变更、无认证逻辑」时，Tech Lead 可在主对话中直接执行，无需 Issue / worktree / PR 流程，并附内联质量检查
- `phase3.5.md`：Phase 3.5 QA 触发条件独立文件，量化判断规则（diff 行数 ≥ 50 / 文件数 ≥ 3 / 新增对外接口 / schema 变更 / 认证逻辑），满足任一条件才触发 QA，否则直接进入 Phase 4

### Changed
- **phase4.md**：Review 新增 Step 0 Scope Drift 检测（`gh pr diff --name-only` 对比 Issue 预期范围，超出则 REQUEST CHANGES）
- **phase2.md**：新项目初始化流程更详细，拆分为①创建仓库（`gh repo create --clone`）+ ②创建 init commit 推送 main 分支两步，避免 main 分支不存在导致 worktree 创建失败
- **worker-new.md / worker-fix.md**：并行冲突检查移至 Step 2（代码阅读之前），强调必须先通过冲突检查才能继续，而非作为编码前的可选步骤
- **qa-agent.md**：QA 报告措辞优化，强调「实际运行测试」与「静态分析推断」的区分

---

## [1.0.0] — 2026-03-22

### Initial Release

**Core workflow (Phase 0–5)**
- Phase 0: 6-type request router — New Project / New Feature / Bug Fix / Emergency Hotfix / Architectural Change / Refactoring
- Phase 1: Product alignment — uses existing PRD directly, or generates one in ≤2 rounds of questions
- Phase 2: Architecture decision checkpoint + task decomposition + GitHub Issue creation with explicit dependency DAG
- Phase 3: Multi-agent parallel development with `isolation: "worktree"`
- Phase 3.5: QA Agent with honest tool boundary declaration (static analysis only)
- Phase 4: Code Review with 8-item checklist and mandatory veto conditions per item
- Phase 5: Retro + next iteration loop

**Worker Agents**
- `worker-new.md`: new feature agent — design-first, 6-category counterexample self-check, structured test output format
- `worker-fix.md`: fix/hotfix agent — minimal scope principle, hotfix branch naming, regression testing requirement

**Safety gates (Phase 4)**
- Static analysis: `flake8` / `pylint` / `mypy` / `eslint` + `bandit` security scan
- Dependency vulnerability scan: `pip-audit` / `npm audit` (mandatory, High/Critical = send back)
- Hardcoded secrets detection (mandatory veto)
- Database migration guard: direct DDL without migration framework = mandatory veto

**Multi-language support**
- `zh/`: Chinese skill files
- `en/`: English skill files
- Install scripts support `--lang en|zh`

**Project templates**
- `PROJECT_CONTEXT_TEMPLATE.md`: structured template for project context file

**Key design decisions**
- Progressive disclosure: slim entry file (`dev.md`) + on-demand phase files
- Tech Lead role anchoring via session state anchor block
- Post-merge PR coordination: scans open PRs for rebase needs after every merge
- `PROJECT_CONTEXT.md` updated at decision time, not just at end of iteration
