# T-001 · CSS Token 收敛 + 状态组件化

> 执行日期：2026-10-09
> 决策：ACCEPT ✅
> 迭代轮次：2 轮（首轮交付 + 自引用 Bug 修复）

---

## 交付物

| 操作 | 文件 | 说明 |
|---|---|---|
| 新建 | `apps/web/modules/ui-components.js` | 4 个统一组件：StatusBadge / EmptyState / LoadingGuard / ExportButton |
| 新建 | `apps/web/modules/` | 模块目录 |
| 修改 | `apps/web/styles.css` | 3 套 :root → 1 套统一 token；295 处硬编码颜色替换为变量；新增 LoadingGuard 样式；status-danger 别名 |
| 修改 | `apps/web/app.js` | 新增 setStatus / setTaskProgress / renderEmpty 三个工具函数；3 处 empty-state 硬编码 → renderEmpty()；6 处状态更新 → setStatus() |
| 修改 | `apps/web/index.html` | 引入 modules/ui-components.js（defer，app.js 之前） |

## 验收数据

| 指标 | 变更前 | 变更后 |
|---|---|---|
| :root 数量 | 3 | 1 |
| 硬编码 #176b50（业务代码） | 48 处 | 0 处 |
| 硬编码 #a43c32（业务代码） | 5 处 | 0 处 |
| 替换色值种类 | — | 118 种 |
| 替换总次数 | — | 295 次 |
| CSS 变量 token | 7 个（:root #1）+ 5 个（banboos）+ 6 个（state） | 56 个（含别名） |
| setStatus 调用 | 0 | 6（示范）+ 1（定义）|
| renderEmpty 调用 | 0 | 3（示范）+ 1（定义）|

## 设计 token 体系

### 中性色 Neutral（9 级）
`--neutral-ink` / `--neutral-muted` / `--neutral-muted-soft` / `--neutral-line` / `--neutral-line-soft` / `--neutral-line-faint` / `--neutral-surface` / `--neutral-paper` / `--neutral-paper-soft` / `--neutral-page` / `--neutral-page-warm`

### 品牌色 Brand · 竹青体系（10 个）
`--brand-bamboo` / `--brand-bamboo-soft` / `--brand-bamboo-border` / `--brand-bamboo-deep` / `--brand-ink` / `--brand-ochre` / `--brand-gold` / `--brand-gold-light` / `--brand-mist`

### 状态色 State（5 组 × 3 属性）
ok / progress / warning / danger / muted，每组含 bg / fg / border

### 尺寸节奏
- 圆角：sm(6px) / md(8px) / lg(10px) / xl(12px) / 2xl(14px) / pill(999px)
- 阴影：sm / md / lg / xl / 2xl
- 间距：1(4px) / 2 / 3 / 4 / 5 / 6 / 8 / 10（4px 基准）
- 字体：--font-sans（微软雅黑）/ --font-mono

### RGB 分量变量（7 个）
支持 rgba 透明度叠加：`--brand-bamboo-rgb` / `--brand-ink-rgb` / `--brand-bamboo-deep-rgb` / `--neutral-ink-rgb` / `--neutral-surface-rgb` / `--neutral-paper-rgb` / `--brand-bamboo-border-rgb`

### 向后兼容别名
- `--banboos-*` → 对应 brand/neutral token（过渡期保留）
- `--ink` / `--muted` / `--line` / `--surface` / `--accent` / `--accent-soft` / `--gold` → 对应新 token

## 缺陷记录

### D-001 · CSS 变量自引用
- **严重度**：P0（阻断）
- **描述**：批量颜色替换脚本未排除 `:root` 变量定义行，导致 22 个基础 token 出现 `--neutral-ink: var(--neutral-ink)` 自引用，整个 token 系统失效
- **发现阶段**：Codex 代码评审
- **修复方式**：重写 `:root` 块，基础 token 使用真实 hex 值，仅语义别名引用其他变量
- **验证**：自引用数量 22 → 0

## 下一步建议（T-002 候选）

1. **O-P0-4 导出按钮强绑定**：ExportButton 接入业务，queryHash 绑定自动失效
2. **LoadingGuard 实战接入**：替换节点分析、电价曲线等页面加载态
3. **剩余状态更新批量迁移**：~54 处 `textContent + className` → `setStatus()`
4. **pulse-demo.css token 化**：该文件仍有硬编码色值
5. **浏览器视觉回归**：Playwright 截图对比 token 收敛前后差异
