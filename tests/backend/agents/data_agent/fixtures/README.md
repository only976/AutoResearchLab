# Data Agent Fixtures

本目录包含 data_agent 的最小测试样例与 pytest 用例。

## 文件说明
- test_metrics.csv：指标序列CSV（第一行为列名，需包含loss/accuracy/energy/time_or_step，其他列可选）
- test_summary.csv：对照组/实验组汇总表样例（experiment_id, metric, value, description）
- test_data_agent_pytest.py：pytest 用例（解析/检查/可视化）

## CSV 格式要求
- **test_metrics.csv**：时间序列数据，必须包含以下至少一列：
  - `loss` / 类似损失列
  - `accuracy` / 类似准确率列  
  - `energy` / 能量守恒量列
  - `time_or_step` / 时间或迭代步数列
  - 可以包含其他任意列，第一行必须是列名
- **test_summary.csv**：汇总统计表，推荐格式为 experiment_id, metric, value, description

## 运行方式（示例）
在仓库根目录运行：
```
pytest backend/experiments/agents/data_agent/fixtures/test_data_agent_pytest.py
```
