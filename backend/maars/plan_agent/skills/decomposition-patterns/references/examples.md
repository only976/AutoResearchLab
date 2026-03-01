# Decomposition Examples

## Example 1: Technical Comparison (Python vs JS)

**Idea**: Compare Python vs JavaScript for backend development and summarize pros/cons.

```
0: Compare Python vs JS for backend
├── 1: 调研 Python 后端生态（框架、性能、适用场景）
├── 2: 调研 JavaScript 后端生态（框架、性能、适用场景）
└── 3: 对比两者优缺点并撰写总结报告 [deps: 1, 2]
```

Parallel research (1, 2) + synthesis (3). Task 3 has fan-in dependency.

## Example 2: Literature Review

**Idea**: Literature review on transformer architectures.

```
0: 文献综述：Transformer 架构
├── 1: 确定检索关键词与数据库范围
├── 2: 检索并筛选核心论文 [deps: 1]
├── 3: 提取各论文关键贡献与局限 [deps: 2]
└── 4: 综合撰写综述报告 [deps: 3]
```

Sequential pipeline. Each phase has one deliverable.

## Example 3: Experiment

**Idea**: Run experiments to compare model A vs B.

```
0: 实验对比模型 A 与 B
├── 1: 定义假设、评估指标与实验配置
├── 2: 运行模型 A 与 B 并记录结果 [deps: 1]
└── 3: 统计分析并撰写实验报告 [deps: 2]
```

## Example 4: Multi-Source Search (Parallel + Merge)

**Idea**: Search multiple databases and merge results.

```
0: 多库检索并合并
├── 1: 检索 ACM Digital Library [deps: []]
├── 2: 检索 IEEE Xplore [deps: []]
├── 3: 合并去重并筛选 [deps: 1, 2]
└── 4: 撰写检索报告 [deps: 3]
```

Tasks 1 and 2 are parallel (empty deps); 3 fans in from both.

## Example 5: Documentation

**Idea**: Write technical documentation for a module.

```
0: 撰写模块技术文档
├── 1: 梳理模块结构与 API 大纲
├── 2: 撰写各章节初稿 [deps: 1]
├── 3: 补充示例与图表 [deps: 2]
└── 4: 审阅并定稿 [deps: 3]
```

## Example 6: Survey Study

**Idea**: Conduct a survey and analyze results.

```
0: 用户调研：满意度与需求
├── 1: 设计问卷与抽样方案
├── 2: 发放并回收问卷 [deps: 1]
├── 3: 数据清洗与编码 [deps: 2]
└── 4: 统计分析并撰写报告 [deps: 3]
```
