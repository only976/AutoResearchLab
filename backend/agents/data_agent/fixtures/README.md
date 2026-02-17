# Data Agent Fixtures

本目录包含 data_agent 的最小测试样例与 pytest 用例。

## 文件说明
- test_metrics.csv：基础指标序列（loss/accuracy/energy/time）
- test_summary.csv：对照组/实验组汇总表样例
- test_data_agent_pytest.py：pytest 用例（解析/检查/可视化）

## 运行方式（示例）
在仓库根目录运行：
```
pytest backend/agents/data_agent/fixtures/test_data_agent_pytest.py
```
