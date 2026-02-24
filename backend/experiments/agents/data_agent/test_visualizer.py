"""
测试可视化模块的各种图表类型
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from backend.agents.data_agent.visualizer import (
    DataVisualizer,
    create_line_chart,
    create_bar_chart,
    create_confusion_matrix
)

def test_visualizations():
    """测试各种可视化类型"""
    
    print("=" * 60)
    print("测试 Data Agent 可视化模块")
    print("=" * 60)
    
    viz = DataVisualizer(use_matplotlib=False)
    
    # 1. 折线图 - 模拟训练损失
    print("\n1. 生成折线图 (训练损失曲线)...")
    x = list(range(0, 100, 5))
    y = [10 / (i + 1) + 0.1 for i in x]  # 递减曲线
    line_svg = viz.create_chart(
        chart_type="line",
        data={"x": x, "y": y},
        output_format="svg",
        title="Training Loss Curve"
    )
    
    output_path = os.path.join(os.path.dirname(__file__), "outputs", "test_line.svg")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(line_svg)
    print(f"   ✓ 折线图已保存: {output_path}")
    print(f"   ✓ SVG 大小: {len(line_svg)} bytes")
    
    # 2. 柱状图 - 不同类型检查结果
    print("\n2. 生成柱状图 (检查结果统计)...")
    bar_svg = viz.create_chart(
        chart_type="bar",
        data={
            "labels": ["Pass", "Warning", "Fail"],
            "values": [45, 12, 3]
        },
        output_format="svg",
        title="Data Quality Checks"
    )
    
    output_path = os.path.join(os.path.dirname(__file__), "outputs", "test_bar.svg")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(bar_svg)
    print(f"   ✓ 柱状图已保存: {output_path}")
    
    # 3. 散点图
    print("\n3. 生成散点图 (参数关系)...")
    scatter_svg = viz.create_chart(
        chart_type="scatter",
        data={
            "x": [i + (i % 3) * 0.5 for i in range(20)],
            "y": [i**1.2 + (i % 5) for i in range(20)]
        },
        output_format="svg",
        title="Parameter Correlation"
    )
    
    output_path = os.path.join(os.path.dirname(__file__), "outputs", "test_scatter.svg")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(scatter_svg)
    print(f"   ✓ 散点图已保存: {output_path}")
    
    # 4. 热力图
    print("\n4. 生成热力图 (参数敏感性分析)...")
    heatmap_svg = viz.create_chart(
        chart_type="heatmap",
        data={
            "matrix": [
                [0.9, 0.1, 0.05],
                [0.2, 0.7, 0.15],
                [0.05, 0.1, 0.8]
            ],
            "row_labels": ["Param A", "Param B", "Param C"],
            "col_labels": ["Low", "Medium", "High"]
        },
        output_format="svg",
        title="Parameter Sensitivity Analysis"
    )
    
    output_path = os.path.join(os.path.dirname(__file__), "outputs", "test_heatmap.svg")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(heatmap_svg)
    print(f"   ✓ 热力图已保存: {output_path}")
    
    # 5. 混淆矩阵
    print("\n5. 生成混淆矩阵 (分类结果)...")
    confusion_svg = viz.create_chart(
        chart_type="confusion_matrix",
        data={
            "matrix": [
                [85, 5],   # TN, FP
                [10, 90]   # FN, TP
            ],
            "labels": ["Negative", "Positive"]
        },
        output_format="svg",
        title="Binary Classification Results"
    )
    
    output_path = os.path.join(os.path.dirname(__file__), "outputs", "test_confusion.svg")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(confusion_svg)
    print(f"   ✓ 混淆矩阵已保存: {output_path}")
    
    # 6. 使用便捷函数
    print("\n6. 测试便捷函数...")
    quick_line = create_line_chart(
        x=list(range(10)),
        y=[i**2 for i in range(10)],
        title="Quick Line Chart",
        format="svg"
    )
    output_path = os.path.join(os.path.dirname(__file__), "outputs", "test_quick_line.svg")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(quick_line)
    print(f"   ✓ 快速折线图已保存: {output_path}")
    
    quick_bar = create_bar_chart(
        labels=["A", "B", "C", "D"],
        values=[10, 25, 15, 30],
        title="Quick Bar Chart",
        format="svg"
    )
    output_path = os.path.join(os.path.dirname(__file__), "outputs", "test_quick_bar.svg")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(quick_bar)
    print(f"   ✓ 快速柱状图已保存: {output_path}")
    
    # 7. Base64 编码输出测试
    print("\n7. 测试 Base64 编码输出...")
    base64_line = create_line_chart(
        x=list(range(5)),
        y=[1, 4, 2, 8, 5],
        format="base64_svg"
    )
    print(f"   ✓ Base64 输出长度: {len(base64_line)} chars")
    print(f"   ✓ 前缀: {base64_line[:50]}...")
    
    print("\n" + "=" * 60)
    print("✅ 所有可视化测试完成！")
    print(f"📁 输出目录: {os.path.join(os.path.dirname(__file__), 'outputs')}")
    print("=" * 60)

if __name__ == "__main__":
    test_visualizations()
