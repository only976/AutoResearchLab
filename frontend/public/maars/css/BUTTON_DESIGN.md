# 按钮设计规范

## 设计原则

1. **默认有边框**：所有按钮默认具备可见边框（`1px solid`），保证视觉边界清晰
2. **三种背景色与容器背景色的色差递增**：默认（色差最小）→ hover（色差中等）→ active（色差最大，点击反馈）
3. **选中状态**：选中态使用专用变量（如 `--settings-select-selected`），通常比 hover 更深
4. **统一 hover 逻辑**：hover 时背景与边框使用统一变量，无缩放/位移效果
5. **无 focus 外圈**：移除 `outline`，避免点击时出现外圈边框

## 设计变量（base.css）

| 变量 | 值 | 说明 |
|------|-----|------|
| `--btn-radius` | 8px | 统一圆角 |
| `--btn-transition` | all 0.2s ease | 统一过渡 |
| `--btn-hover-bg` | var(--interactive-hover) | hover 背景色（与容器色差中等） |
| `--btn-active-bg` | var(--interactive-active) | active 背景色（与容器色差最大） |
| `--btn-hover-border` | var(--interactive-border-hover) | hover 边框色 |

## 基础规则（所有 button / .btn）

- `border-radius`: var(--btn-radius)
- `transition`: var(--btn-transition)
- `cursor`: pointer
- `outline`: none
- `box-sizing`: border-box

### 状态

| 状态 | 规则 |
|------|------|
| **默认** | 各变体自定义背景色（与容器色差最小） |
| **hover** | `background: var(--btn-hover-bg)`, `border-color: var(--btn-hover-border)`（色差中等） |
| **active** | `background: var(--btn-active-bg)`（色差最大，点击反馈） |
| **选中** | 维持 hover 背景色（如 `.settings-nav-item.active`） |
| **disabled** | `opacity: 0.5`, `cursor: not-allowed` |
| **focus** | `outline: none`（无外圈） |

## 变体

### default（默认实心）
- 适用：无 class 的 button、`.btn-default`
- 边框：`1px solid var(--border-color)`
- 背景：`var(--bg-white)`
- hover：`box-shadow: var(--shadow-lg)`

### icon（图标按钮）
- 适用：`.icon-btn`, `.btn-icon`
- 尺寸：40×40px
- 边框：`1px solid var(--border-color)`
- 背景：`var(--bg-area-secondary)`

### close（关闭按钮）
- 适用：`.close`, `.task-agent-output-modal-close`, `.task-detail-popover-close`
- 尺寸：32×32px
- 边框：`1px solid var(--border-color)`
- 背景：`transparent`，hover 时 `var(--btn-hover-bg)`

### expand（块内展开）
- 适用：`.task-agent-output-block-expand`, `.btn-expand`
- 边框：`1px solid var(--border-color)`
- 背景：`transparent`，hover 时 `var(--btn-hover-bg)`

### ghost（描边透明）
- 适用：`.btn-ghost`
- 边框：`1px solid var(--border-color)`
- 背景：`transparent`

### menu（侧栏菜单项）
- 适用：`.settings-nav-item`
- 边框：`1px solid transparent`
- 背景：`none`，hover `var(--settings-select-hover)`，active `var(--settings-select-active)`，选中 `var(--settings-select-selected)`
- 选中（`.active`）：`var(--settings-select-selected)`（比 hover 更深，避免过亮）

### preset-add（预设添加）
- 适用：`.settings-preset-add`
- 边框：`1px dashed var(--border-color)`
- 背景：`var(--bg-white)`，hover `var(--btn-hover-bg)`

### tab（标签）
- 适用：`.task-detail-tab`, `.btn-tab`
- 边框：`1px solid var(--border-color)`
- 默认：`var(--status-undone)`，hover `var(--btn-hover-bg)`，active `var(--btn-active-bg)`
- 带状态的 tab：使用 `--status-*-hover`、`--status-*-active`

### danger（危险操作）
- 适用：`.stop-btn`, `.btn-danger`
- 边框：`1px solid var(--failure-border)`
- 背景：`var(--failure-bg)`
- hover：`var(--failure-bg-hover)`
- active：`var(--failure-bg-active)`（与容器色差最大）

## 禁止项

- 禁止 hover 时使用 `transform`（如 `translateY`、`scale`）
- 禁止 focus 时使用 `outline` 外圈

## 实现位置

- 变量：`frontend/css/base.css`
- 样式：`frontend/css/components.css`（按钮系统区块）
