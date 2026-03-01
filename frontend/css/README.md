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
│   └── modal.css       # 弹窗、Popover
├── regions/        # 区域
│   ├── idea-input.css  # 输入行
│   ├── thinking.css   # 推理区（thinking-block + output-block 共用基础）
│   ├── tree.css       # 任务树、视图切换
│   └── output.css      # 执行统计、芯片、产出弹窗
└── ui/             # UI 特定
    └── settings.css   # 设置弹窗
```

## 加载顺序（styles.css）

1. core/variables → core/reset
2. layout/page
3. components（markdown → buttons → modal）
4. regions（idea-input → thinking → tree → output）
5. ui/settings

## 冗余精简

- **content-block**：`.plan-agent-thinking-block` 与 `.task-agent-output-block` 共用基础样式
- **markdown**：thinking、output、modal 共用 `.markdown-body` 规则
- **base + theme**：合并为 variables.css（theme 独立保留便于主题切换）
