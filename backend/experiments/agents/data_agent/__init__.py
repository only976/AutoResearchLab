from backend.experiments.agents.base_agent import BaseAgent
from .visualizer import (
    DataVisualizer,
    create_line_chart,
    create_bar_chart,
    create_confusion_matrix
)


class DataAgent(BaseAgent):
    def __init__(self):
        super().__init__()


__all__ = [
    "DataAgent",
    "DataVisualizer",
    "create_line_chart",
    "create_bar_chart",
    "create_confusion_matrix",
]
