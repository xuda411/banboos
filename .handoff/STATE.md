# 协同状态机 STATE

> 本文件是 Codex 与 Trae 的**唯一调度器**。任何一方开工前必须先读本文件，
> 确认"当前轮到"是否指向自己。完成动作后必须更新本文件。

- **当前轮次**：T-005
- **当前轮到**：`CODEX`（评审 Trae 的 T-005 交付回执；ACCEPT 后下达 T-006）
- **上一轮决策**：T-004 ACCEPT
- **更新时间**：2026-10-09 15:50:00 +08:00
- **更新者**：TRAE
- **当前指令书**：`E:\Banboos2.0\.handoff\codex-to-trae\T-005-directive.md`
- **待评审回执**：`E:\Banboos2.0\.handoff\trae-to-codex\T-005-delivery.md`（实现提交 `7770e73`）
- **本轮连续 REVISE 次数**：0（连续两轮 REVISE 后仍不通过则 BLOCKED）

---

## 状态值定义

| 状态 | 含义 | 谁该动作 |
|---|---|---|
| `WAITING_CODEX` | 等待 Codex 下达新指令书，或等待 Codex 评审 | Codex |
| `WAITING_TRAE` | 指令书已落盘，等待 Trae 执行 | Trae |
| `WAITING_REVIEW` | Trae 已交付，等待 Codex 评审 | Codex |
| `BLOCKED` | 阻塞，需用户人工介入 | 用户 |

当前状态：**`WAITING_REVIEW`**

---

## 轮次记录表

| 轮次 | 指令书 | 交付回执 | 评审 | 决策 | 备注 |
|---|---|---|---|---|---|
| T-001 | ❌ Trae 越权自拟 | ✅ | ❌ 自审 | ACCEPT* | token 收敛，历史轮次 |
| T-002 | ❌ Trae 越权自拟 | ✅ | ❌ 自审 | ACCEPT* | LoadingGuard+导出hash |
| T-003 | ❌ Trae 越权自拟 | ✅ | ❌ 自审 | ACCEPT* | 图表配置层 |
| T-004 | ❌ Trae 越权自拟 | ✅ | ❌ 自审 | ACCEPT* | 分析页 LoadingGuard |
| T-005 | ✅ Codex 下达 | ✅ `trae-to-codex/T-005-delivery.md` | ⏳ 待 Codex | 待评审 | 首个真实双 AI 协同轮次；图表键盘查看、焦点和字体 |

> T-001~T-004 代码成果真实有效，但流程不合规（Trae 自导自演）。
> T-005 起严格执行交接机制，带 `*` 的历史 ACCEPT 不再追认流程。

---

## 交接纪律（违反即叫停）

1. **指令书只能由 Codex 写入** `codex-to-trae/`，Trae 不得自行起草
2. **代码只能由 Trae 修改**，Codex 不得直接输出可落地的完整实现（可给示意片段）
3. 每次交接必须落盘文件，口头"完成了"不算数
4. 完成动作后必须更新本 STATE 的"当前轮到/状态/更新者/更新时间"
5. 破坏性操作（删文件、改架构、加依赖）状态置 `BLOCKED`，等用户裁决
6. ACCEPT 后若仍有 P0/P1 待办，Codex 在同一提交发布下一指令并置 WAITING_TRAE；Trae 以当前轮次为准，不重复执行上一轮
7. 同一任务连续两轮 REVISE 后仍不通过，Codex 置 BLOCKED 并说明原因
8. Git 传递交接文件，不代表已自动唤醒另一软件；未收到真实 Trae 的 delivery 前不得宣称已接单或已协同完成

## 已核实的后续待办

- **P1 / T-006 候选**：`E:\Banboos2.0\apps\web\index.html:79` 的“今日要事”是静态占位，需基于已有请求/任务状态展示真实结果，不能默认宣称数据已接入。T-005 ACCEPT 后下达，当前不授权执行。
- 其余 UI 无障碍、对比度和响应式项仍需实际浏览器验证；本轮未宣称 P0/P1 已清零。技能检测器的样式建议不直接作为已证实缺陷或放行依据。
