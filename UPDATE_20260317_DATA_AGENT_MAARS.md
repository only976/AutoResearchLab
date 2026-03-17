# Data Agent 接入 MAARS 更新说明（2026-03-17）

## 1. 目标

将现有 Data Agent 能力接入主分支 MAARS API 流程，支持通过实验接口直接触发数据分析并回读报告。

## 2. 主要改动

### 2.1 新增 Data Agent 适配层

新增目录与文件：
- backend/integration/__init__.py
- backend/integration/data_agent_adapter.py

适配层能力：
- 扫描实验目录中的 CSV/LOG 文件
- 调用 backend/agents/data_agent/docker_data_agent.py 执行解析、检查、可视化
- 将 base64 图像落盘为文件引用
- 生成 summary（metrics/observations/generated_charts）

### 2.2 MAARS 实验 API 接线

修改文件：
- backend/api/experiments.py

新增内容：
- 在 _load_maars 中增加 DB_DIR 与 save_task_artifact 的接入
- 新增接口：
  - POST /api/experiments/{exp_id}/analyze
  - GET /api/experiments/{exp_id}/data-report

行为说明：
- analyze 会在 db/maars/{exp_id}/ 下扫描数据文件并生成 data_agent_report
- 报告保存为 MAARS artifact（task_id=data_analysis）
- data-report 读取上述 artifact 返回

### 2.3 Data Agent 相关模块迁移进融合分支

新增（迁移）文件：
- backend/agents/data_agent.py
- backend/agents/data_analysis_agent.py
- backend/agents/data_agent/*
- backend/tools/git_ops.py

## 3. 验证结果

### 3.1 服务可用性

- /health 返回 {"status":"ok"}

### 3.2 接口联调

已验证：
1. POST /api/experiments 创建实验成功
2. POST /api/experiments/{exp_id}/plan 在 Gemini 链路恢复后可返回任务（样例 TASKS=19）
3. POST /api/experiments/{exp_id}/analyze 返回 completed
4. GET /api/experiments/{exp_id}/data-report 可读回检查和可视化结果

### 3.3 Data Agent 报告样例指标

- checks_count: 5
- visuals_count: 1
- data_agent_pass_checks > 0
- data_agent_fail_checks = 0（样例数据）

## 4. 过程中修复的问题

1. 缺失依赖导致后端无法启动（socketio、pypdf、qdrant-client、sentence-transformers 等）
2. integration 文件编码为 UTF-16 导致导入报错：source code string cannot contain null bytes
   - 已重写为 UTF-8
3. /plan 超时问题
   - 在超时窗口较小时可能超时，延长到 300s 可完成

## 5. 已知注意项

1. 如果 Gemini API key 过期，/plan 会报 500（外部依赖问题）
2. /analyze 依赖实验目录下存在 CSV/LOG 输入；无数据时会返回 skipped
3. 首次安装 sentence-transformers 及其依赖可能较慢

## 6. 建议合并策略

1. 先合并本分支到 main（保留 API 接线 + integration 目录）
2. 后续再做前端调用对接（新增 Analyze 按钮与 data-report 展示）
3. 增加一条自动化回归：create -> plan -> analyze -> data-report
