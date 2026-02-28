# MAARS Release Note 撰写标准

本文档定义 MAARS 项目 Release Note 的撰写规范，供每次版本发布时参考。

---

## 1. 输出方式

- **不维护** `docs/releases/` 目录下的 Release 文件
- **输出**：撰写完成后，以 Markdown 代码块（` ```markdown ... ``` `）形式输出，供用户复制到 GitHub Release、CHANGELOG 等
- **版本号**：采用语义化版本 `v{major}.{minor}.{patch}`，如 `v1.2.0`

---

## 2. 版本号规则

遵循 [Semantic Versioning 2.0.0](https://semver.org/lang/zh-CN/)：

| 类型 | 何时递增 | 示例 |
|------|----------|------|
| **major** | 不兼容的 API 或架构变更 | 1.0.0 → 2.0.0 |
| **minor** | 向后兼容的功能新增 | 1.0.0 → 1.1.0 |
| **patch** | 向后兼容的问题修复 | 1.0.0 → 1.0.1 |

预发布版本使用后缀，如 `v1.2.0-alpha.1`、`v1.2.0-beta.2`。

---

## 3. Release Note 结构模板

> **注意**：正文中不要包含版本标题（如 `# MAARS v2.4.1`）。GitHub 版本发布页面会自动显示版本号作为标题，重复书写会造成冗余。

```markdown
**发布日期**：YYYY-MM-DD

## 概述

（1–3 句话概括本版本的主要变化与价值）

## 新增功能 (Added)

- （功能描述，可附 PR/Issue 编号）

## 变更 (Changed)

- （行为变更、API 变更、配置变更等）

## 修复 (Fixed)

- （Bug 修复、稳定性改进）

## 弃用/移除 (Deprecated / Removed)

- （如有）

## 安全 (Security)

- （如有安全相关更新）

## 技术细节 / 迁移指南

（可选：重要变更的迁移步骤、配置说明、破坏性变更说明）

```

---

## 4. 分类说明

### 4.1 新增功能 (Added)

- 新模块、新 API、新 UI 组件
- 新配置项、新工作流
- 新文档或示例

**撰写要点**：说明「做了什么」以及「用户/开发者能获得什么」。

### 4.2 变更 (Changed)

- 现有行为或 API 的调整
- 性能优化、重构
- 默认配置变更

**撰写要点**：明确变更前后差异，必要时说明迁移方式。

### 4.3 修复 (Fixed)

- Bug 修复
- 崩溃、异常、错误处理改进
- 兼容性修复

**撰写要点**：简要描述问题现象及修复结果。

### 4.4 弃用/移除 (Deprecated / Removed)

- 已弃用但暂未移除的 API/配置
- 已移除的功能或文件

**撰写要点**：说明替代方案及迁移路径。

### 4.5 安全 (Security)

- 安全漏洞修复
- 依赖升级中的安全修复

**撰写要点**：说明影响范围及建议操作。

---

## 5. 撰写原则

### 5.1 语言与风格

- **语言**：以中文为主，技术术语可保留英文（如 API、WebSocket、LLM）
- **对象**：面向用户与开发者，兼顾使用场景与实现细节
- **风格**：简洁、客观，避免营销式表述

### 5.2 条目格式

- 每条变更单独一行，以 `-` 开头
- 格式：`- **模块/区域**：具体描述`（模块可选）
- 可附 PR/Issue 编号，如：`(#123)`、`(PR #45)`

### 5.3 示例

```markdown
## 新增功能 (Added)

- **Plan Agent**：支持按阶段独立配置 LLM（atomicity/decompose/format）
- **Monitor**：执行图新增 stage-based 网格布局，支持等价任务合并 (#78)

## 变更 (Changed)

- **API**：`/api/plan/{id}` 响应中 `layout` 字段结构变更，详见 [EXECUTION_LAYOUT_RULES](backend/visualization/EXECUTION_LAYOUT_RULES.md)

## 修复 (Fixed)

- 修复 Task Agent 池在任务失败时可能卡死的问题
- 修复前端任务树在深层嵌套时的布局错位
```

---

## 6. 发布流程

1. **收集变更**：从 Git 提交、PR、Issue 中整理本版本变更
2. **分类归类**：按 Added / Changed / Fixed / Deprecated / Security 分类
3. **撰写初稿**：按模板撰写，遵循上述原则
4. **评审**：由维护者或团队 Review
5. **输出**：以 Markdown 代码块形式输出 Release Note，供用户复制到 GitHub Release 等

---

## 7. 可选：CHANGELOG.md 集成

若需维护单一 CHANGELOG，可在项目根目录维护 `CHANGELOG.md`，格式与 Release Note 一致，按版本倒序排列，每个版本下直接内联 Release Note 摘要。

---

*本规范自制定之日起生效，后续可根据项目实践迭代更新。*
