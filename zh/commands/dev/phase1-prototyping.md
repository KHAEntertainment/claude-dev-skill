# Phase 1 — 原型化子流程

Phase 1 中遇到**低保真问题**（用文字讨论拍不了板的问题）时，由本子流程派发原型 sub-agent 把决策点具象化，再回到主对话继续。

主对话（Tech Lead）负责：检测信号 → 决定派不派 → 选类型/Mode → 派发 → 拿回 readout → 重提原问题。
Sub-agent 负责：只产 artifact 和 readout，不替主对话做决策。

---

## Step 1 — 检测低保真信号

出现以下任一情况时考虑触发原型化（不必每条都满足，能命中一条就值得评估）：

- 用户在同一个问题上连续 ≥2 次说"我不确定 / 看情况 / 你先做一个我看看 / 感觉得看到东西"
- AI 给出推荐答案后，用户既不同意也不反对，表达"嗯……我也说不清"
- 决策涉及视觉/交互/数据形态/调用流程，单纯文字描述明显容易跑偏
- 同一个决策点反复回到原点超过 2 轮，没收敛

**反信号（不要轻易派）：**
- 用户只是在思考，请耐心等
- 决策本质是"做不做"而不是"怎么做"
- 决策已经基本清晰，用户只是想要更详细的解释（这是回答问题，不是原型化）

---

## Step 2 — 选类型 + Mode

| 决策点性质 | 类型 | Mode |
|------------|------|------|
| 用户看不到前端长什么样 / 用户流走得对不对 | Frontend | — |
| 多模块怎么互相调 / Agent 节点怎么连 / 业务流分支 | Backend | **Viz** |
| 数据模型/接口/State 字段长什么样 | Backend | **Shape** |
| LLM 在某个 prompt 下到底能不能做出某种行为 | Backend | **Spike** |

**默认升级路径**（同一个决策点连续派发时）：
**Viz → Shape → Spike**

第一次派 Viz（最便宜，能讨论清楚 90% 的后端低保真问题）；如果讨论后用户仍模糊于"具体字段"，升级到 Shape；如果仍模糊于"LLM 实际反应"，再升级到 Spike。

**严禁跳级**（比如直接派 Spike）除非用户明确要求或决策点本质就是 LLM 行为问题。

---

## Step 3 — 准备派发参数

派发前主对话必须先准备好：

- **slug**：决策点的简短标识符（小写连字符，例如 `chat-list-layout`、`agent-state-shape`）
- **目录名**：`prototypes/[今天日期 YYYY-MM-DD]-[序号 NNN]-[slug]/`
  - 序号 NNN 是当天本项目内的第几个原型，从 001 开始
  - 用 `ls prototypes/ 2>/dev/null` 看一下当天已有几个原型
- **决策点一句话**：把 Phase 1 当前在讨论的问题压成一句
- **已锁定上下文**：把以下三块拼成派发参数
  - PRD 草稿的当前状态（只取相关模块部分，不全文）
  - glossary 里跟当前决策相关的关键术语
  - 当前模块已锁定的决策列表

---

## Step 4 — 派发

用 Agent 工具派发，参数：

```
subagent_type: general-purpose
description: 一句话描述要做的原型
prompt: <把 worker-prototype-frontend.md 或 worker-prototype-backend.md 的完整内容贴入>

派发参数：
- 原型 slug：[slug]
- Mode（仅后端需要）：[Viz | Shape | Spike]
- 输出目录：prototypes/[YYYY-MM-DD]-[NNN]-[slug]/
- 要回答的决策点：[一句话]
- 已锁定上下文：[拼好的上下文段落]
```

**告知用户**：派发的同时在主对话告诉用户：
```
我注意到 [决策点] 用文字讨论拍不了板，我派一个原型 sub-agent 做 [类型/Mode]，
产出后我会基于原型重新提问。
```

---

## Step 5 — 接收 + 回流

Sub-agent 返回汇报后，主对话执行：

1. **读 readout**（不读 artifact 全文，只读 readout.md），把"原型已呈现 / 未呈现 / 建议主对话下一步"消化掉
2. **告知用户 artifact 路径**，让用户用浏览器/编辑器打开看：
   ```
   原型已生成在 [路径]。
   - 前端：请在浏览器打开 index.html，点击 [关键交互] 试试
   - 后端 Viz/Shape：请打开 diagram.md / shape.md
   - 后端 Spike：请看 run-output.txt 里的 LLM 真实输出
   ```
3. **基于 readout 重提决策点**，把原问题改写得更具体：
   - 原问题（低保真）：`聊天列表应该长什么样？`
   - 重提（高保真）：`你看完原型，发现列表项里我把"未读计数"放在了右上角。这个位置合适吗？如果不合适，你倾向于哪里？`
4. **glossary 增补**：如果 readout 里有"glossary 增补建议"，立即把术语补充进 `docs/glossary.md`
5. **进度面包屑更新**：当前模块的"已锁定决策"数量保持不变，因为原型本身不锁定决策；用户基于原型回答后才锁定

---

## 命名与归档

- 目录：`prototypes/YYYY-MM-DD-NNN-<slug>/`
- 文件：
  - 前端：`index.html` + `readout.md`
  - 后端 Viz：`diagram.md` + `readout.md`
  - 后端 Shape：`shape.md` + `readout.md`
  - 后端 Spike：`spike.py` + `run-output.txt` + `readout.md`
- 默认 `prototypes/` 在 `.gitignore` 中（见 `PROJECT_CONTEXT_TEMPLATE.md` 的 gitignore 指引）。用户可选择性 `git add` 关键原型。
- 同一决策点连续升级（Viz → Shape → Spike）时，使用不同 slug 或在 slug 上加版本号（如 `agent-state-shape-v2`），不要覆盖之前的原型。

---

## 禁止行为

- 不在没有低保真信号时主动派原型（不要为了"显得 thorough"而派）
- 不在派发前向用户征求许可（用户已经表达过模糊，征求许可只会拖慢节奏，但**派发的同时必须告知**）
- 不让 sub-agent 直接修改 PRD 或 glossary（这是主对话的职责，sub-agent 只能"建议增补"）
- 不复述 sub-agent 的 readout 全文给用户看（让用户和主对话各自从 readout 取信息）
- 不在同一轮派多个 sub-agent（一次一个原型，等回来再决定要不要升级或切类型）
