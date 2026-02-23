# Data Agent 规范（输入/命名/表头/对照组）

本规范基于当前 data_agent（docker_data_agent.py）的解析与识别逻辑，统一输入格式、命名、对照组/实验组写法与表头指标约定。

## 1) 输入与汇总表命名

### 1.1 输入文件
- 支持：`.csv`、`.log`
- 若使用 `--dockerfile` / `--docker-image`：容器输出路径默认 `/output`，自动收集 `.csv/.log` 并解析。

### 1.2 汇总表（总报表）文件名
统一命名：
```
summary_{领域}_{方法}_{指标集}_{日期}.csv
```
示例：
```
summary_turbulence_PINN_coremetrics_20260217.csv
```

### 1.3 输出目录
统一产出目录：
```
outputs/run_YYYYMMDD_HHMMSS_xxxxxxxx/
  ├─ report.json
  └─ visuals/
```

## 2) Sheet/表命名规范（论证型数据）

### 2.1 结构（领域-方法-维度-组别）
```
{领域}_{方法}_{维度}_{组别}
```
- 领域：任务/学科（如 turbulence / fluid / protein）
- 方法：模型/算法（如 PINN / GNN / Baseline）
- 维度：指标维度（如 accuracy / stability / energy）
- 组别：`control` 或 `experiment`

示例：
- `turbulence_PINN_accuracy_experiment`
- `turbulence_baseline_accuracy_control`

### 2.2 论证表达（基于XX达到XX水平）
```
basis_{X}_reach_{Y}_{领域}_{方法}_{维度}_{组别}
```
示例：
- `basis_sparse_data_reach_sota_turbulence_PINN_accuracy_experiment`

## 3) 对照组 / 实验组写法

### 3.1 统一组别字段
- 对照组：`control`
- 实验组：`experiment`

### 3.2 表内字段（推荐最小集）
```
group, domain, method, dimension, metric, value, unit, time_or_step
```
说明：
- `group`: control / experiment
- `domain`: 领域
- `method`: 方法
- `dimension`: 指标维度
- `metric`: 指标名（如 loss / accuracy / energy）
- `value`: 数值
- `unit`: 单位（可空）
- `time_or_step`: 时间或迭代步

## 4) 表头规范（论文指标）

### 4.1 标准指标表头（优先）
```
time_or_step, loss, accuracy, energy, error, rmse, mae
```

### 4.2 常见扩展指标
```
precision, recall, f1, auc, r2, mape
```

### 4.3 对照/实验对比输出表头
```
group, metric, value, unit, time_or_step, note
```

## 5) 数值内容规范

- 数值只允许数值或科学计数法（如 `1.2e-3`）
- 缺失值使用空值或 `NaN`
- 允许负值，但需在 `note` 说明原因

## 6) 汇总表输出规范（对照 vs 实验）

建议统一汇总表字段：
```
group, domain, method, dimension, metric, value, unit, time_or_step, evidence
```
- `evidence`: 简要结论，用于表达“基于XX达到XX水平”
  - 示例：`基于稀疏采样达到SOTA水平`

## 7) 自动识别（与 data_agent 兼容）

data_agent 当前识别逻辑支持如下关键词：
- `loss/error/rmse/mse` → loss
- `accuracy/acc/auc` → accuracy
- `energy/momentum` → conserved
- `time/step/epoch/iteration` → time

若表头与以上关键词对齐，将提升识别准确率与可视化效果。
