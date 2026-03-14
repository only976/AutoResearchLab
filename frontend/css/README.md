# MAARS CSS 结构

按样式类型与区域分类，精简冗余。

## 目录结构

```
css/
├── core/           # 基础
│   ├── theme.css       # 色板（light/dark/black）
│   ├── variables.css   # 布局/组件变量（引用 theme）
│   └── reset.css       # 重置、滚动条、body、container
├── layout/         # 布局
│   └── page.css        # 页面头部、主内容、排版
├── components/     # 通用组件
│   ├── markdown.css    # markdown 内容（thinking/output/modal 共用）
│   ├── buttons.css     # 按钮系统
│   ├── modal.css       # 弹窗、Popover
│   └── toast.css       # 轻量通知
├── regions/        # 区域
│   ├── idea-input.css  # 输入行
│   ├── research.css    # Research 首页、详情页、阶段面板
│   ├── thinking.css    # 推理区（thinking-block + output-block 共用基础）
│   ├── tree.css        # 任务树、视图切换
│   └── output.css      # 执行统计、芯片、产出弹窗
└── ui/             # UI 特定
    ├── settings.css   # 设置弹窗
    └── sidebar.css    # 侧边栏（Research 列表、开关）
```

## 加载顺序（styles.css）

1. core/variables → core/reset
2. layout/page
3. components（markdown → buttons → modal → toast）
4. regions（idea-input → research → thinking → tree → output）
5. ui（settings → sidebar）

## 冗余精简

- **content-block**：`.plan-agent-thinking-block` 与 `.task-agent-output-block` 共用基础样式
- **markdown**：thinking、output、modal 共用 `.markdown-body` 规则
- **base + theme**：合并为 variables.css（theme 独立保留便于主题切换）

## 按钮系统

按钮规范统一收敛在 `components/buttons.css` 和 `core/variables.css`，不再单独维护另一份设计文档。

### 设计原则

- 默认保持可见边框，避免按钮边界在深浅主题里丢失
- hover / active 只通过背景和边框层级变化反馈，不使用 `transform`
- 选中态应明显强于 hover 态，但仍保持和主题变量一致
- focus 不额外绘制外圈，交互反馈主要靠颜色与边框

### 关键变量

| 变量 | 说明 |
|------|------|
| `--btn-radius` | 按钮统一圆角 |
| `--btn-transition` | 按钮统一过渡 |
| `--btn-hover-bg` | hover 背景 |
| `--btn-active-bg` | active 背景 |
| `--btn-hover-border` | hover 边框 |

### 常用变体

| 变体 | 典型类名 | 用途 |
|------|----------|------|
| default | `.btn-default` | 普通主按钮 |
| ghost | `.btn-ghost` | 描边透明按钮 |
| danger | `.btn-danger` | 危险操作 |
| menu | `.settings-nav-item` | 设置导航项 |
| tab | `.btn-tab`, `.research-stage-btn` | 标签/阶段切换 |
| icon | `.btn-icon`, `.app-sidebar-toggle` | 图标按钮 |
