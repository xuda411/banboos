# Codex × Trae 协同交接区 · 操作手册

## 目录结构

```
E:\Banboos2.0\.handoff\
├── STATE.md                  ← 状态机（唯一调度器，开工前必读）
├── README.md                 ← 本操作手册
├── codex-prompt.md           ← 贴给 ChatGPT 内 Codex 的系统提示词
├── trae-rules.md             ← Trae 侧执行规则
├── scripts\
│   └── handoff-sync.ps1      ← Git 通道同步脚本（pull / push / status）
├── codex-to-trae\            ← Codex 写指令书 → Trae 只读
├── trae-to-codex\            ← Trae 写交付回执 → Codex 只读
└── review\                   ← Codex 写评审意见 → Trae 只读
```

## 数据流（每一轮）

```
Codex 在 GitHub 提交指令书 ──→ codex-to-trae/T-XXX-directive.md
      ▲                    STATE: WAITING_TRAE
      │                         │
      │                         ▼
评审意见 review/          Trae pull → 读指令 → 改代码
      ▲                         │
      │                         ▼
      └────────────── trae-to-codex/T-XXX-delivery.md
                       STATE: WAITING_REVIEW → push
```

## 通道选择

| 通道 | 状态 | 适用 |
|---|---|---|
| ③ **Git 同步（主通道）** | 本次配置 | Codex 已连接同一 GitHub 仓库，双方通过 commit 交换文件 |
| ① 手动粘贴（兜底） | 随时可用 | Git 不可用时，直接复制 Markdown 内容 |

## Git 通道标准操作

### 一次性准备（仅首次）

1. 已安装 Git for Windows（本机已完成）
2. 在 GitHub 创建一个**私有仓库**（建议名 `banboos2-internal`），不要勾选初始化 README
3. 关联远程并首次推送（Trae 会引导你完成，首次推送时凭据管理器会弹浏览器登录 GitHub）
4. 在 ChatGPT 中让 Codex **连接该 GitHub 仓库**（对话里的仓库/连接器入口），并粘贴 `codex-prompt.md`

### 每轮操作（你只做"触发"）

**Codex 下达/评审后（它会把指令书或评审意见 commit 到仓库）：**

在 Trae 里说：

> 同步并执行

Trae 会自动：`pull` → 读 STATE 确认轮到自己 → 执行 → 写交付回执 → 更新 STATE → `push`。

**Trae 交付后：**

在 ChatGPT 里对 Codex 说：

> Trae 已交付并推送，请 pull 后读取 `.handoff/trae-to-codex/T-XXX-delivery.md` 评审，评审意见写入 `review/` 并 commit/push。

### 同步脚本（Trae 内部使用，也可手动运行）

```powershell
cd E:\Banboos2.0\.handoff\scripts
.\handoff-sync.ps1 status                    # 查看通道状态
.\handoff-sync.ps1 pull                      # 拉取 Codex 最新指令/评审
.\handoff-sync.ps1 push -Task T-005 -Role trae   # 提交并推送交付
```

## 冲突防呆

- 每一方写文件前必须先 `pull`
- STATE 是串行状态机，同一时刻只有一方在写，正常不会冲突
- push 脚本内置 fetch + merge；若真冲突，脚本中止并提示人工处理
- `pull` 要求工作区干净；Trae 每轮交付前必须先完成 push

## 给 Codex 的仓库内行为约束（已写入 codex-prompt.md）

- Codex 只允许 commit `.handoff/` 内的文件（指令书、评审、STATE）
- Codex 不得直接修改业务代码；它可以浏览全仓库代码用于评审
