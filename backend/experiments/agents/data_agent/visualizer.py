"""
Data Visualizer Module
支持多种图表类型和输出格式的可视化工具
"""
import io
import base64
import math
from typing import List, Dict, Any, Tuple, Optional, Literal
import numpy as np

# 尝试导入 matplotlib（可选）
try:
    import matplotlib
    matplotlib.use('Agg')  # 无GUI后端
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


ChartType = Literal["line", "bar", "scatter", "heatmap", "confusion_matrix"]
OutputFormat = Literal["svg", "png", "base64_svg", "base64_png"]


class DataVisualizer:
    """数据可视化类，支持多种图表类型和输出格式"""
    
    def __init__(self, use_matplotlib: bool = False):
        """
        初始化可视化器
        
        Args:
            use_matplotlib: 是否使用 matplotlib（需要安装），否则使用纯 SVG 绘制
        """
        self.use_matplotlib = use_matplotlib and MATPLOTLIB_AVAILABLE
        if use_matplotlib and not MATPLOTLIB_AVAILABLE:
            print("⚠️ Matplotlib not available, falling back to pure SVG rendering")
    
    def create_chart(
        self,
        chart_type: ChartType,
        data: Dict[str, Any],
        output_format: OutputFormat = "base64_svg",
        title: str = "",
        **kwargs
    ) -> str:
        """
        创建图表
        
        Args:
            chart_type: 图表类型 (line/bar/scatter/heatmap/confusion_matrix)
            data: 数据字典，格式取决于图表类型
            output_format: 输出格式 (svg/png/base64_svg/base64_png)
            title: 图表标题
            **kwargs: 其他参数
            
        Returns:
            图表字符串（SVG XML 或 base64 编码）
        """
        if self.use_matplotlib and output_format in ["png", "base64_png"]:
            return self._create_chart_matplotlib(chart_type, data, output_format, title, **kwargs)
        else:
            # 使用纯 SVG 绘制
            return self._create_chart_svg(chart_type, data, output_format, title, **kwargs)
    
    # ==================== 纯 SVG 实现 ====================
    
    def _create_chart_svg(
        self,
        chart_type: ChartType,
        data: Dict[str, Any],
        output_format: OutputFormat,
        title: str,
        **kwargs
    ) -> str:
        """使用纯 SVG 创建图表"""
        if chart_type == "line":
            svg = self._make_line_svg(data, title, **kwargs)
        elif chart_type == "bar":
            svg = self._make_bar_svg(data, title, **kwargs)
        elif chart_type == "scatter":
            svg = self._make_scatter_svg(data, title, **kwargs)
        elif chart_type == "heatmap":
            svg = self._make_heatmap_svg(data, title, **kwargs)
        elif chart_type == "confusion_matrix":
            svg = self._make_confusion_matrix_svg(data, title, **kwargs)
        else:
            raise ValueError(f"Unknown chart type: {chart_type}")
        
        if output_format == "base64_svg":
            return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
        else:
            return svg
    
    def _make_line_svg(
        self,
        data: Dict[str, Any],
        title: str = "",
        width: int = 700,
        height: int = 300,
        color: str = "#ff7f0e"
    ) -> str:
        """生成折线图 SVG
        
        Args:
            data: {"x": [...], "y": [...]} 或 {"y": [...]} (x 自动生成)
        """
        y = data.get("y", [])
        x = data.get("x", list(range(len(y))))
        
        pad_left = 60
        pad_bottom = 50
        pad_top = 30
        pad_right = 20
        plot_w = width - pad_left - pad_right
        plot_h = height - pad_top - pad_bottom

        # 清洗数据
        pts = [(xi, yi) for xi, yi in zip(x, y) if not (math.isnan(yi) or math.isinf(yi))]
        if not pts:
            return f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'><text x='50%' y='50%' text-anchor='middle'>No valid data</text></svg>"
        
        xs, ys = zip(*pts)
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        if maxx == minx:
            maxx = minx + 1
        if maxy == miny:
            maxy = miny + 1

        def sx(v):
            return pad_left + int((v - minx) / (maxx - minx) * plot_w)

        def sy(v):
            return pad_top + plot_h - int((v - miny) / (maxy - miny) * plot_h)

        parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>"]
        parts.append("<style>text{font-family:Arial,sans-serif;font-size:12px;}</style>")
        
        # 标题
        if title:
            parts.append(f"<text x='{width//2}' y='20' text-anchor='middle' font-size='14' font-weight='bold'>{title}</text>")

        # 坐标轴
        parts.append(f"<line x1='{pad_left}' y1='{pad_top}' x2='{pad_left}' y2='{pad_top+plot_h}' stroke='#333' stroke-width='1.5'/>")
        parts.append(f"<line x1='{pad_left}' y1='{pad_top+plot_h}' x2='{pad_left+plot_w}' y2='{pad_top+plot_h}' stroke='#333' stroke-width='1.5'/>")

        # Y轴刻度
        for i in range(5):
            yval = miny + (maxy - miny) * i / 4
            ypos = sy(yval)
            parts.append(f"<line x1='{pad_left-5}' y1='{ypos}' x2='{pad_left}' y2='{ypos}' stroke='#333'/>")
            parts.append(f"<text x='{pad_left-10}' y='{ypos+4}' text-anchor='end'>{yval:.2g}</text>")
        
        # X轴刻度
        for i in range(5):
            xval = minx + (maxx - minx) * i / 4
            xpos = sx(xval)
            parts.append(f"<line x1='{xpos}' y1='{pad_top+plot_h}' x2='{xpos}' y2='{pad_top+plot_h+5}' stroke='#333'/>")
            parts.append(f"<text x='{xpos}' y='{pad_top+plot_h+20}' text-anchor='middle'>{xval:.2g}</text>")

        # 折线
        pts_attr = " ".join(f"{sx(xi)},{sy(yi)}" for xi, yi in pts)
        parts.append(f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{pts_attr}' />")

        # 数据点
        for xi, yi in pts[::max(1, len(pts)//50)]:  # 最多显示50个点
            parts.append(f"<circle cx='{sx(xi)}' cy='{sy(yi)}' r='3' fill='{color}'/>")

        parts.append("</svg>")
        return "\n".join(parts)
    
    def _make_bar_svg(
        self,
        data: Dict[str, Any],
        title: str = "",
        width: int = 600,
        height: int = 400,
        color: str = "#4c78a8"
    ) -> str:
        """生成柱状图 SVG
        
        Args:
            data: {"labels": [...], "values": [...]}
        """
        labels = data.get("labels", [])
        values = data.get("values", [])
        
        if not labels or not values:
            return f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'><text x='50%' y='50%' text-anchor='middle'>No data</text></svg>"
        
        pad_left = 120
        pad_right = 80
        pad_top = 40
        pad_bottom = 40
        
        bar_height = 30
        gap = 10
        plot_height = len(labels) * (bar_height + gap)
        total_height = max(height, plot_height + pad_top + pad_bottom)
        
        maxv = max(1, max(values) if values else 1)
        scale = (width - pad_left - pad_right) / maxv

        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_height}">']
        parts.append('<style>text{font-family:Arial,sans-serif;font-size:12px;}</style>')
        
        if title:
            parts.append(f"<text x='{width//2}' y='25' text-anchor='middle' font-size='14' font-weight='bold'>{title}</text>")
        
        y = pad_top
        for i, lab in enumerate(labels):
            val = values[i] if i < len(values) else 0
            w = int(round(val * scale))
            
            # 标签
            parts.append(f'<text x="{pad_left-10}" y="{y + bar_height//2 + 4}" text-anchor="end">{lab}</text>')
            # 柱子
            parts.append(f'<rect x="{pad_left}" y="{y}" width="{w}" height="{bar_height}" fill="{color}" rx="2"></rect>')
            # 数值
            parts.append(f'<text x="{pad_left + w + 8}" y="{y + bar_height//2 + 4}">{val}</text>')
            
            y += bar_height + gap
        
        parts.append('</svg>')
        return "\n".join(parts)
    
    def _make_scatter_svg(
        self,
        data: Dict[str, Any],
        title: str = "",
        width: int = 600,
        height: int = 400,
        color: str = "#e74c3c"
    ) -> str:
        """生成散点图 SVG
        
        Args:
            data: {"x": [...], "y": [...]}
        """
        x = data.get("x", [])
        y = data.get("y", [])
        
        # 使用与折线图相同的布局，但绘制点而不是线
        return self._make_line_svg(data, title, width, height, color).replace(
            "<polyline", "<!-- polyline removed --><polyline style='display:none'"
        )
    
    def _make_heatmap_svg(
        self,
        data: Dict[str, Any],
        title: str = "",
        width: int = 600,
        height: int = 500
    ) -> str:
        """生成热力图 SVG
        
        Args:
            data: {"matrix": [[...], [...]], "row_labels": [...], "col_labels": [...]}
        """
        matrix = data.get("matrix", [])
        row_labels = data.get("row_labels", [f"Row {i}" for i in range(len(matrix))])
        col_labels = data.get("col_labels", [f"Col {i}" for i in range(len(matrix[0]) if matrix else 0)])
        
        if not matrix:
            return f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'><text x='50%' y='50%' text-anchor='middle'>No data</text></svg>"
        
        pad_left = 100
        pad_top = 80
        pad_right = 100
        pad_bottom = 40
        
        rows = len(matrix)
        cols = len(matrix[0]) if matrix else 0
        cell_width = min(40, (width - pad_left - pad_right) / cols if cols else 40)
        cell_height = min(40, (height - pad_top - pad_bottom) / rows if rows else 40)
        
        total_width = max(width, int(pad_left + cols * cell_width + pad_right))
        total_height = max(height, int(pad_top + rows * cell_height + pad_bottom))
        
        # 归一化数据
        flat = [v for row in matrix for v in row if not math.isnan(v) and not math.isinf(v)]
        if not flat:
            return f"<svg xmlns='http://www.w3.org/2000/svg' width='{total_width}' height='{total_height}'><text x='50%' y='50%' text-anchor='middle'>No valid data</text></svg>"
        
        minv, maxv = min(flat), max(flat)
        if maxv == minv:
            maxv = minv + 1
        
        def value_to_color(v):
            """将数值映射到颜色（蓝色到红色）"""
            if math.isnan(v) or math.isinf(v):
                return "#cccccc"
            norm = (v - minv) / (maxv - minv)
            # 蓝 -> 白 -> 红
            if norm < 0.5:
                r = int(255 * (norm * 2))
                g = int(255 * (norm * 2))
                b = 255
            else:
                r = 255
                g = int(255 * (2 - norm * 2))
                b = int(255 * (2 - norm * 2))
            return f"#{r:02x}{g:02x}{b:02x}"
        
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{total_height}">']
        parts.append('<style>text{font-family:Arial,sans-serif;font-size:10px;}</style>')
        
        if title:
            parts.append(f"<text x='{total_width//2}' y='20' text-anchor='middle' font-size='14' font-weight='bold'>{title}</text>")
        
        # 绘制矩阵
        for i, row in enumerate(matrix):
            for j, val in enumerate(row):
                x = pad_left + j * cell_width
                y = pad_top + i * cell_height
                color = value_to_color(val)
                parts.append(f'<rect x="{x}" y="{y}" width="{cell_width}" height="{cell_height}" fill="{color}" stroke="#fff"/>')
                # 数值标签
                if cell_width > 30 and cell_height > 20:
                    parts.append(f'<text x="{x + cell_width/2}" y="{y + cell_height/2 + 3}" text-anchor="middle" fill="#000">{val:.2g}</text>')
        
        # 行标签
        for i, label in enumerate(row_labels):
            y = pad_top + i * cell_height + cell_height/2
            parts.append(f'<text x="{pad_left - 10}" y="{y + 4}" text-anchor="end">{label}</text>')
        
        # 列标签
        for j, label in enumerate(col_labels):
            x = pad_left + j * cell_width + cell_width/2
            parts.append(f'<text x="{x}" y="{pad_top - 10}" text-anchor="middle" transform="rotate(-45, {x}, {pad_top - 10})">{label}</text>')
        
        parts.append('</svg>')
        return "\n".join(parts)
    
    def _make_confusion_matrix_svg(
        self,
        data: Dict[str, Any],
        title: str = "Confusion Matrix",
        width: int = 500,
        height: int = 500
    ) -> str:
        """生成混淆矩阵 SVG
        
        Args:
            data: {"matrix": [[TN, FP], [FN, TP]], "labels": ["Negative", "Positive"]}
                 或 {"matrix": [[...], [...],...], "labels": ["Class0", "Class1", ...]}
        """
        matrix = data.get("matrix", [])
        labels = data.get("labels", [f"Class {i}" for i in range(len(matrix))])
        
        # 混淆矩阵是热力图的特殊形式，添加精确度等信息
        heatmap_data = {
            "matrix": matrix,
            "row_labels": [f"True {l}" for l in labels],
            "col_labels": [f"Pred {l}" for l in labels]
        }
        
        svg = self._make_heatmap_svg(heatmap_data, title, width, height)
        
        # 添加统计信息
        if len(matrix) == 2 and len(matrix[0]) == 2:
            # 二分类混淆矩阵
            tn, fp = matrix[0][0], matrix[0][1]
            fn, tp = matrix[1][0], matrix[1][1]
            
            total = tn + fp + fn + tp
            accuracy = (tp + tn) / total if total > 0 else 0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            stats = f"<text x='10' y='{height - 10}' font-size='11'>Acc: {accuracy:.3f} | Prec: {precision:.3f} | Rec: {recall:.3f} | F1: {f1:.3f}</text>"
            svg = svg.replace("</svg>", stats + "</svg>")
        
        return svg
    
    # ==================== Matplotlib 实现 ====================
    
    def _create_chart_matplotlib(
        self,
        chart_type: ChartType,
        data: Dict[str, Any],
        output_format: OutputFormat,
        title: str,
        **kwargs
    ) -> str:
        """使用 Matplotlib 创建图表（PNG 格式）"""
        if not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("Matplotlib is not available")
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        if chart_type == "line":
            self._plot_line_matplotlib(ax, data, title, **kwargs)
        elif chart_type == "bar":
            self._plot_bar_matplotlib(ax, data, title, **kwargs)
        elif chart_type == "scatter":
            self._plot_scatter_matplotlib(ax, data, title, **kwargs)
        elif chart_type == "heatmap":
            self._plot_heatmap_matplotlib(ax, data, title, **kwargs)
        elif chart_type == "confusion_matrix":
            self._plot_confusion_matrix_matplotlib(ax, data, title, **kwargs)
        else:
            raise ValueError(f"Unknown chart type: {chart_type}")
        
        # 保存到内存
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        
        if output_format == "base64_png":
            return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")
        else:
            return buf.read()
    
    def _plot_line_matplotlib(self, ax, data: Dict[str, Any], title: str, **kwargs):
        """Matplotlib 折线图"""
        y = data.get("y", [])
        x = data.get("x", list(range(len(y))))
        ax.plot(x, y, marker='o', linewidth=2, markersize=4)
        ax.set_title(title)
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.grid(True, alpha=0.3)
    
    def _plot_bar_matplotlib(self, ax, data: Dict[str, Any], title: str, **kwargs):
        """Matplotlib 柱状图"""
        labels = data.get("labels", [])
        values = data.get("values", [])
        ax.barh(labels, values)
        ax.set_title(title)
        ax.set_xlabel('Value')
    
    def _plot_scatter_matplotlib(self, ax, data: Dict[str, Any], title: str, **kwargs):
        """Matplotlib 散点图"""
        x = data.get("x", [])
        y = data.get("y", [])
        ax.scatter(x, y, alpha=0.6)
        ax.set_title(title)
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.grid(True, alpha=0.3)
    
    def _plot_heatmap_matplotlib(self, ax, data: Dict[str, Any], title: str, **kwargs):
        """Matplotlib 热力图"""
        matrix = np.array(data.get("matrix", []))
        im = ax.imshow(matrix, cmap='coolwarm', aspect='auto')
        ax.set_title(title)
        
        row_labels = data.get("row_labels", [])
        col_labels = data.get("col_labels", [])
        if row_labels:
            ax.set_yticks(range(len(row_labels)))
            ax.set_yticklabels(row_labels)
        if col_labels:
            ax.set_xticks(range(len(col_labels)))
            ax.set_xticklabels(col_labels, rotation=45, ha='right')
        
        plt.colorbar(im, ax=ax)
    
    def _plot_confusion_matrix_matplotlib(self, ax, data: Dict[str, Any], title: str, **kwargs):
        """Matplotlib 混淆矩阵"""
        self._plot_heatmap_matplotlib(ax, data, title, **kwargs)
        
        # 添加数值标签
        matrix = np.array(data.get("matrix", []))
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                ax.text(j, i, str(matrix[i, j]), ha='center', va='center', color='black')


# 便捷函数
def create_line_chart(x: List[float], y: List[float], title: str = "", format: OutputFormat = "base64_svg") -> str:
    """快速创建折线图"""
    viz = DataVisualizer()
    return viz.create_chart("line", {"x": x, "y": y}, format, title)


def create_bar_chart(labels: List[str], values: List[float], title: str = "", format: OutputFormat = "base64_svg") -> str:
    """快速创建柱状图"""
    viz = DataVisualizer()
    return viz.create_chart("bar", {"labels": labels, "values": values}, format, title)


def create_confusion_matrix(matrix: List[List[int]], labels: List[str], title: str = "Confusion Matrix", format: OutputFormat = "base64_svg") -> str:
    """快速创建混淆矩阵"""
    viz = DataVisualizer()
    return viz.create_chart("confusion_matrix", {"matrix": matrix, "labels": labels}, format, title)
