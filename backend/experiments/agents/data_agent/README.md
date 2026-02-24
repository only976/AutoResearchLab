# Data Agent 模块

数据可靠性验证、可视化和分析工具，支持 LLM 智能识别和多种图表类型。

## 📁 目录结构

```
backend/experiments/agents/data_agent/
├── __init__.py                  # 模块入口
├── docker_data_agent.py         # 主程序：数据验证与报告生成
├── visualizer.py                # 可视化模块：支持多种图表类型
├── test_visualizer.py           # 可视化测试脚本
└── outputs/                     # 输出目录
    ├── run_YYYYMMDD_HHMMSS_xxxx/  # 每次运行的输出
    │   ├── report.json            # JSON 报告
    │   └── visuals/               # 可视化文件
    │       ├── 00_plot_0_loss.svg
    │       └── ...
    └── test_*.svg                 # 测试输出
```

## 🚀 快速开始

### 1. 数据验证与分析

```bash
# 基础用法
python -m backend.experiments.agents.data_agent.docker_data_agent -i data/simulation.csv -o report.json

# 使用 LLM 智能识别列类型
python -m backend.experiments.agents.data_agent.docker_data_agent -i data/simulation.csv -o report.json

# 禁用 LLM（仅使用规则识别）
python -m backend.experiments.agents.data_agent.docker_data_agent -i data/simulation.csv -o report.json --no-llm

# 自定义输出目录
python -m backend.experiments.agents.data_agent.docker_data_agent \
    -i data/simulation.csv \
    -o report.json \
    --out-dir backend/experiments/agents/data_agent/outputs
```

### 2. Docker 集成

```bash
# 从 Dockerfile 构建并运行
python -m backend.experiments.agents.data_agent.docker_data_agent \
    --dockerfile path/to/Dockerfile \
    --container-output-path /output \
    -o report.json

# 使用现有 Docker 镜像
python -m backend.experiments.agents.data_agent.docker_data_agent \
    --docker-image my_simulation:latest \
    --container-output-path /output \
    -o report.json
```

### 3. 使用可视化模块

```python
from backend.experiments.agents.data_agent import DataVisualizer, create_line_chart, create_bar_chart

# 方式 1：使用便捷函数
svg_base64 = create_line_chart(
    x=[0, 1, 2, 3, 4],
    y=[0, 1, 4, 9, 16],
    title="y = x²",
    format="base64_svg"
)

# 方式 2：使用 DataVisualizer 类
viz = DataVisualizer()
svg = viz.create_chart(
    chart_type="confusion_matrix",
    data={
        "matrix": [[85, 5], [10, 90]],
        "labels": ["Negative", "Positive"]
    },
    output_format="svg",
    title="Classification Results"
)
```

## 📊 支持的图表类型

| 图表类型 | 说明 | 数据格式 |
|---------|------|---------|
| `line` | 折线图 | `{"x": [...], "y": [...]}` |
| `bar` | 柱状图 | `{"labels": [...], "values": [...]}` |
| `scatter` | 散点图 | `{"x": [...], "y": [...]}` |
| `heatmap` | 热力图 | `{"matrix": [[...]], "row_labels": [...], "col_labels": [...]}` |
| `confusion_matrix` | 混淆矩阵 | `{"matrix": [[...]], "labels": [...]}` |

### 输出格式

- `svg`: 纯 SVG XML 字符串
- `png`: PNG 二进制数据（需要 matplotlib）
- `base64_svg`: Base64 编码的 SVG（可直接嵌入 HTML）
- `base64_png`: Base64 编码的 PNG（需要 matplotlib）

## 🤖 LLM 智能识别

Data Agent 使用 LLM（通过硅基流动 API）智能识别 CSV 列的语义类型：

### 识别类型

- `loss`: 损失/误差（应递减）
- `accuracy`: 准确率/性能（应递增，范围 0-1）
- `conserved`: 守恒量（应保持稳定）
- `time`: 时间/迭代计数
- `physical`: 一般物理量
- `unknown`: 无法确定

### 配置

在 `.env` 文件中设置：

```env
SF_API_KEY=your_siliconflow_api_key
```

### 示例

```python
# CSV 文件：
# step,residual_error,Total_Joule,val_acc
# 1,0.5,100.0,0.6
# 2,0.3,99.8,0.7
# ...

# LLM 智能识别：
# residual_error → loss
# Total_Joule → conserved
# val_acc → accuracy
```

## 🔍 数据校验

自动执行以下检查：

1. **NaN/Inf 检测**：检查无效数值比例
2. **收敛性检查**：验证损失类指标是否递减
3. **性能提升检查**：验证准确率类指标是否递增
4. **守恒性检查**：验证守恒量是否稳定（相对波动 < 5%）

## 📈 可视化功能

### 自动生成

Data Agent 自动为以下类型生成可视化：

- 损失曲线（优先级最高）
- 准确率曲线
- 守恒量变化
- 物理量趋势

### 自定义可视化

```python
from backend.experiments.agents.data_agent.visualizer import DataVisualizer

viz = DataVisualizer()

# 训练曲线
train_curve = viz.create_chart(
    chart_type="line",
    data={"x": epochs, "y": loss_values},
    output_format="svg",
    title="Training Loss",
    color="#ff7f0e"
)

# 参数敏感性热力图
sensitivity = viz.create_chart(
    chart_type="heatmap",
    data={
        "matrix": sensitivity_matrix,
        "row_labels": param_names,
        "col_labels": metric_names
    },
    output_format="svg",
    title="Parameter Sensitivity"
)

# 分类混淆矩阵
confusion = viz.create_chart(
    chart_type="confusion_matrix",
    data={
        "matrix": [[TN, FP], [FN, TP]],
        "labels": ["Class 0", "Class 1"]
    },
    output_format="svg"
)
```

## 🧪 测试

```bash
# 测试可视化模块
python backend/experiments/agents/data_agent/test_visualizer.py

# 查看测试输出
ls backend/experiments/agents/data_agent/outputs/test_*.svg
```

## 📋 输出报告格式

```json
{
  "input": "data/simulation.csv",
  "metadata": {
    "parsed_series_count": 4,
    "llm_identification_used": true,
    "detected_column_types": {
      "simulation.csv::loss": "loss",
      "simulation.csv::accuracy": "accuracy"
    }
  },
  "checks": [
    {
      "id": "convergence_loss",
      "name": "收敛性检查 - loss",
      "status": "pass",
      "details": "从 0.5 降到 0.1，改善 80.0%"
    }
  ],
  "visuals": [
    {
      "id": "plot_0_loss",
      "type": "line",
      "description": "loss 损失曲线",
      "image_base64": "data:image/svg+xml;base64,..."
    }
  ],
  "summary": {
    "total_checks": 5,
    "passed": 3,
    "warnings": 1,
    "failed": 1
  },
  "timestamp": "2026-02-11 14:34:45 SGT",
  "llm_enabled": true
}
```

## ⚙️ 配置

### 环境变量

| 变量 | 说明 | 默认值 |
|-----|------|--------|
| `SF_API_KEY` | 硅基流动 API 密钥 | - |
| `SILICON_API_KEY` | 备用 API 密钥 | - |

### 命令行参数

```
-i, --input              输入文件（CSV/LOG），可多次指定
-o, --output             输出 JSON 文件名
--out-dir                输出基目录（默认：outputs）
--dockerfile             Dockerfile 路径
--docker-image           Docker 镜像名
--container-output-path  容器内输出路径（默认：/output）
--repo-root              Git 仓库根路径（用于回滚）
--no-llm                 禁用 LLM 智能识别
```

## 🔧 依赖

### 必需
- Python 3.10+
- 标准库（无额外依赖）

### 可选
- `matplotlib`: PNG 格式图表输出
- `numpy`: 高级数值计算
- `google.adk`: LLM 智能识别（已安装）

## 📝 更新日志

### v2.0 (2026-02-11)
- ✅ 模块化重构，创建独立 data_agent 文件夹
- ✅ 新增 visualizer.py 可视化模块
- ✅ 支持 5 种图表类型（折线、柱状、散点、热力图、混淆矩阵）
- ✅ 支持多种输出格式（SVG、PNG、Base64）
- ✅ 集成硅基流动 API 进行 LLM 智能识别
- ✅ 输出目录迁移至模块内部

### v1.0
- 基础数据验证功能
- CSV/LOG 文件解析
- 规则基础的列类型识别
- Docker 集成
