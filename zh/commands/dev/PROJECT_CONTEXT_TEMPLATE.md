# PROJECT_CONTEXT.md — 索引文件

> 这是主索引，只做路由，不堆内容。
> 详细内容分散在 `docs/` 子文档中，每个文件保持 100–200 行。
> `/dev` skill 在每个 Phase 都会读取此文件恢复上下文。

---

## 仓库信息

- **仓库地址**：https://github.com/[owner]/[repo]
- **主分支**：main
- **创建时间**：YYYY-MM-DD

---

## 子文档目录

| 文件 | 内容 | 更新时机 |
|------|------|----------|
| `docs/glossary.md` | 领域术语规范表（与避免词） | Phase 1 词语精度 pass 时逐项追加；后续 Phase 发现术语漂移时修正 |
| `docs/tech-stack.md` | 语言、框架、数据库、测试框架、依赖版本 | 技术选型变化时 |
| `docs/architecture.md` | 架构决策记录（ADR），认证方案、API 规范、迁移方案 | 架构决策时立即更新 |
| `docs/api-contracts.md` | 接口清单、请求/响应格式、错误码（前后端分离项目） | 新增/修改接口时 |
| `docs/style-guide.md` | 命名规范、目录结构、错误处理约定、注释规范 | 约定变化时 |
| `docs/feature-log.md` | 已完成功能列表（PR号、合并日期） | 每轮 Phase 5 更新 |

---

## 当前状态（本文件唯一需要频繁更新的部分）

- **最后更新**：YYYY-MM-DD
- **当前迭代目标**：[本轮要完成的功能描述]
- **开放 PR**：#N [描述]，#M [描述]
- **已知技术债**：见 `docs/feature-log.md` 底部

---

## 初始化时的 .gitignore 指引

Phase 1 期间产出的原型 artifact 默认不进 git。在 `.gitignore` 添加：
```
prototypes/
PRD-draft.md
```

`PRD-draft.md` 是 Phase 1 进行中的草稿，Step D 冻结后改名为 `PRD.md` 才进 git。`prototypes/` 用户可以选择性 `git add` 个别保留价值高的原型。

---

## 子文档模板

新项目初始化时，在 `docs/` 目录下创建以下文件：

**`docs/glossary.md`**
```markdown
# Glossary

> Phase 1 词语精度环节锁定的领域术语规范。
> 主对话和所有 Phase 都应使用规范术语，不使用 _Avoid_ 列出的近义词。

## 术语

**<术语>**：<一句定义，描述"是什么"，不描述"做什么">
_Avoid_：<被替代的近义词，逗号分隔>

**<术语>**：<定义>
_Avoid_：<近义词>

## 关系

- 一个 <术语 A> 关联多个 <术语 B>
- <术语 C> 属于 <术语 A>

## 已标记歧义

- "<原始用词>" 曾被同时用于指代 <术语 X> 和 <术语 Y> — 解决：这两者是不同概念。
```



**`docs/tech-stack.md`**
```markdown
# Tech Stack

## 语言 & 运行时
- Python 3.11 / Node.js 20 / ...

## 框架
- FastAPI / Express / ...

## 数据库
- PostgreSQL / SQLite / ...

## 测试框架
- pytest / Jest / 无

## 关键依赖版本
- [package]: [version]
```

**`docs/architecture.md`**
```markdown
# Architecture Decisions

## 认证方案
- 方案：JWT，存储于 HttpOnly Cookie
- 决策时间：YYYY-MM-DD，PR #N

## API 设计规范
- 错误格式：`{"error_code": "...", "message": "..."}`
- 分页：`?page=&size=`

## 数据库迁移
- 框架：Alembic（有存量数据）/ 无（全新项目）

## [新决策按此格式追加]
- 方案：...
- 决策时间：...，PR #N
- 背景：...
```

**`docs/style-guide.md`**
```markdown
# Style Guide

## 命名规范
- Python: snake_case 变量/函数，PascalCase 类名

## 目录结构
src/
  routers/    # API 路由层
  services/   # 业务逻辑层
  models/     # 数据模型
  utils/      # 工具函数
tests/

## 错误处理约定
- 统一抛出 HTTPException，不在路由层写业务逻辑
```

**`docs/feature-log.md`**
```markdown
# Feature Log

## 已完成
- [功能名]（PR #N，YYYY-MM-DD 合并）

## 已知技术债
- [描述]（来源：PR #N，登记时间：YYYY-MM-DD）
```
