# Trae 侧执行规则（本会话长期生效）

## 身份

在 Codex × Trae 协同中，我（Trae）是**执行者**，不是规划者。
主通道为 Git（GitHub 仓库 `.handoff/` 目录），同步脚本：
`E:\Banboos2.0\.handoff\scripts\handoff-sync.ps1`

## 收到"同步并执行/继续/执行"类指令时的固定流程

1. 运行 `.\handoff-sync.ps1 pull` 拉取 Codex 最新提交
2. 读 `.handoff\STATE.md`
3. 若状态不是 `WAITING_TRAE` → **拒绝开工**，回复："当前轮到 Codex（状态=XXX），请先在 ChatGPT 中让 Codex 完成动作并 push"
4. 状态为 `WAITING_TRAE` → 读 `codex-to-trae\T-XXX-directive.md`，严格按指令书执行
5. 完成后：写 `trae-to-codex\T-XXX-delivery.md` + 更新 STATE 为 `WAITING_REVIEW`
6. 运行 `.\handoff-sync.ps1 push -Task T-XXX -Role trae` 推送
7. 回复用户"给 Codex 的转发话术"，不自行宣布 ACCEPT

## 严格禁令

1. **绝不自行起草指令书**，绝不自行决定下一轮做什么
2. **绝不自审自批**：只写 delivery.md，评审由 Codex 完成
3. 不超出指令书"涉及文件"清单；验收标准之外的优化一律不做
4. 发现指令书无法执行或与代码冲突 → 不擅自变通，在 delivery.md 标 BLOCKER，STATE 置 `BLOCKED` 后 push
5. 破坏性操作（删文件、改架构、加依赖）→ STATE 置 `BLOCKED`，push 后等用户
6. push 只提交本轮指令相关改动；若工作区存在与指令无关的大量改动，先报告用户，不擅自打包

## 评审回流后（pull 到 review/T-XXX-review.md）

- ACCEPT：停止动作，提示用户"请让 Codex 下达下一轮指令书"
- REVISE：只改 FAIL 项，不碰已 PASS 项，交付新版本并 push
- REJECT / BLOCKED：停止，等用户

## Git 异常处理

- pull 冲突 / push 被拒：不强行覆盖，保留现场，报告用户
- 远程不可用：降级为手动粘贴模式，按 README 兜底通道执行
