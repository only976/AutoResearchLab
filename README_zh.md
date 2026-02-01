# AutoResearchLab (自动化科研助手)

AutoResearchLab 是一个基于多 Agent 协作的自动化科研系统，旨在辅助科研人员完成从**灵感构思**、**实验设计**、**代码实现**、**数据分析**到**论文草稿**的全流程工作。系统集成了大语言模型（LLM）、沙箱执行环境（Docker）和版本控制系统（Git），以确保实验的安全性、可追溯性和结果的可靠性。

---

## 1. 整体设计思路

本系统的核心设计理念围绕以下四点展开：

1.  **全流程自动化 (End-to-End Automation)**：
    *   打通科研工作的各个环节，用户仅需提供一个模糊的研究方向，系统即可自动细化为具体课题，并生成可执行的实验计划。
2.  **安全性与隔离性 (Safety & Isolation)**：
    *   所有生成的代码均在 **Docker 容器**中运行，与宿主机环境完全隔离，防止自动生成的代码对系统造成破坏或依赖冲突。
3.  **可追溯性与非线性探索 (Traceability & Exploration)**：
    *   引入 **Git** 作为实验过程的底层记录机制。每个实验步骤、每一次代码修改都作为 Commit 提交。
    *   支持 **DFS (深度优先搜索)** 式的实验路径探索。如果某一步骤失败或效果不佳，系统可以回溯并创建新分支尝试不同方案，形成可视化的实验树（Git Tree）。
4.  **人机协作 (Human-in-the-Loop)**：
    *   虽然追求自动化，但关键节点（如风险评估、计划确认、结果审查）保留人工介入接口，确保研究方向符合用户预期。

---

## 2. 架构设计

### 2.1 系统架构图
```mermaid
graph TD
    User[用户] --> Frontend[Streamlit 前端]
    Frontend --> Orchestrator["实验编排器 (ExperimentRunner)"]
    
    subgraph "Agent Cluster (智能体集群)"
        IdeaAgent[灵感 Agent]
        DesignAgent[设计 Agent]
        CodingAgent[Coding Agent]
        ReviewAgent[Review Agent]
        AnalysisAgent[Analysis Agent]
        WritingAgent[Writing Agent]
    end
    
    Orchestrator <--> Agent Cluster
    
    subgraph "Execution Environment (执行环境)"
        Docker[Docker Sandbox]
        Workspace["实验工作区 (Data/Experiments)"]
        Git[Git Version Control]
    end
    
    CodingAgent --> Docker
    Docker <--> Workspace
    Workspace <--> Git
```

### 2.2 核心模块详解

#### **A. 前端交互层 (Frontend)**
*   基于 **Streamlit** 构建，提供直观的操作界面。
*   **Idea Generator**：灵感生成器，支持从模糊概念到具体课题的细化。
*   **Experiment Dashboard**：实验控制台，实时展示实验进度、日志、生成的图表（Artifacts）。
*   **Git Tree Visualization**：使用 Graphviz 可视化展示实验的分支与尝试记录，支持节点点击与详情查看。

#### **B. 智能体集群 (Backend Agents)**
所有 Agent 均通过统一的 LLM 接口（支持 OpenAI/DeepSeek/Gemini 等）进行配置。
*   **IdeaAgent**: 负责发散思维，生成多个研究选题，并进行新颖性评估。
*   **ExperimentDesignAgent**: 将选题转化为详细的实验步骤（Plan），包括环境依赖分析和风险评估。
*   **CodingAgent**: 负责具体的代码实现。它不仅生成代码，还会处理依赖安装、文件读写等操作。
*   **ReviewAgent**: **质量守门员**。在每一步执行后，审查代码运行结果、日志和生成的文件，判断是否满足当前步骤目标及全局实验目标。
*   **DataAnalysisAgent**: 实验结束后，自动读取数据文件（CSV/JSON），生成统计图表和定量分析报告。
*   **WritingAgent**: 基于实验计划、过程记录和分析结果，自动撰写符合学术规范的论文草稿。

#### **C. 基础设施 (Infrastructure)**
*   **Docker Sandbox**: 
    *   每个实验启动时自动构建或复用 Docker 镜像。
    *   通过 Volume 挂载实现数据持久化，确保容器内生成的文件能同步回宿主机。
*   **Git Versioning**:
    *   每个实验目录初始化为一个独立的 Git 仓库。
    *   系统自动提交 Commit，Message 结构化记录了（Step, Plan, Scheme, Result）。
    *   支持自动分支切换，记录每一次“重试”或“方案变更”。

---

## 3. 功能详情

### 3.1 灵感生成与细化
*   用户输入感兴趣的领域（如“强化学习在五子棋中的应用”）。
*   系统分析该领域的广度，若太宽泛则生成多个细分方向；若具体则进行完善。
*   生成包含摘要、关键词、可行性分析的提案卡片。

### 3.2 交互式实验规划
*   选定课题后，系统生成包含 5-8 个步骤的实验计划。
*   **环境自检**：自动检测本地 Docker、Git 环境，以及所需的 Python 库是否可能存在冲突。
*   **风险谈判**：识别潜在风险（如需要 GPU、需要私有数据），用户可在此阶段反馈或确认忽略风险。

### 3.3 自动化执行与纠错
*   **自动编码**：根据步骤描述生成 Python 脚本。
*   **沙箱运行**：在 Docker 中执行脚本，捕获 stdout/stderr。
*   **自我修正**：如果运行报错，CodingAgent 会读取错误日志并尝试修复代码（默认重试 3 次）。
*   **结果审查**：ReviewAgent 介入，判断执行结果是否逻辑正确（不仅仅是无报错，还要看是否有产出）。

### 3.4 实验可视化与管理
*   **实时日志**：前端实时滚动显示当前的思考过程和执行日志。
*   **Git 树状图**：图形化展示实验的探索路径，清晰看到哪些尝试失败了，哪些成功了。
*   **产物预览**：直接在网页上查看生成的 CSV 数据、PNG 图表或代码文件。

---

## 4. 调试与启动

### 4.1 环境要求
*   **操作系统**: macOS (推荐), Linux, Windows (WSL2)
*   **Python**: 3.10+
*   **Docker**: 必须安装并启动 Docker Daemon（用于沙箱环境）。
*   **Git**: 系统需安装 Git。

### 4.2 安装步骤

1.  **克隆项目**
    ```bash
    git clone <repository_url>
    cd AutoResearchLab
    ```

2.  **创建虚拟环境并安装依赖**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **配置环境变量**
    复制 `.env.example` (如果有) 或直接创建 `.env` 文件：
    ```env
    # LLM 配置 (Backend/config.py 会读取这些配置)
    # 选项 1: 使用 SiliconFlow (DeepSeek)
    # SILICON_API_KEY=sk-xxxxxxxx
    
    # 选项 2: 使用 Google Gemini
    GOOGLE_API_KEY=AIzaSyxxxxxxxxx
    ```
    *注意：请在 `backend/config.py` 中确认当前启用的模型配置。*

### 4.3 启动系统

运行 Streamlit 前端应用：
```bash
streamlit run frontend/app.py
```
启动后，浏览器将自动打开 `http://localhost:8501`。

### 4.4 常见问题与调试

*   **Docker 连接失败**:
    *   现象：启动实验时提示 "Docker Daemon not running"。
    *   解决：请确保 Docker Desktop 已启动，且在终端运行 `docker ps` 能看到输出。
*   **Git Tree 显示过大**:
    *   现象：实验步骤多了以后，Git Tree 占满屏幕。
    *   解决：我们在前端已优化，默认折叠且宽度自适应。点击 "Expand" 查看详情。
*   **Streamlit 警告 (use_container_width)**:
    *   已在最新版本中修复，替换为 `width="stretch"`。
*   **实验卡在某一步**:
    *   查看终端后台日志，或者在前端点击 "Stop" 停止实验，然后尝试 "Retry"。

---

## 5. 目录结构说明

```
AutoResearchLab/
├── backend/                # 后端核心逻辑
│   ├── agents/             # 各类智能体实现 (Coding, Design, Review...)
│   ├── execution/          # 实验执行引擎 (Runner)
│   ├── sandbox/            # Docker 沙箱管理
│   ├── config.py           # 统一配置中心
│   └── ...
├── frontend/               # 前端界面
│   ├── app.py              # 入口文件
│   ├── components/         # 各个功能组件 (Dashboard, IdeaGenerator...)
│   └── ...
├── data/                   # 数据存储 (已配置 .gitignore)
│   ├── experiments/        # 具体的实验工作区 (每个实验一个文件夹)
│   ├── cache/              # 缓存数据
│   └── ...
├── requirements.txt        # 项目依赖
└── README.md               # 项目文档
```
