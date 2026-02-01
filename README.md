# AutoResearchLab (Automated Research Assistant)

AutoResearchLab is an automated research system based on multi-agent collaboration, designed to assist researchers in the entire workflow from **Idea Conception**, **Experiment Design**, **Code Implementation**, **Data Analysis** to **Paper Drafting**. The system integrates Large Language Models (LLM), Sandbox Execution Environments (Docker), and Version Control Systems (Git) to ensure experiment safety, traceability, and result reliability.

---

## 1. Overall Design Philosophy

The core design philosophy of this system revolves around the following four points:

1.  **End-to-End Automation**:
    *   Connects all stages of research work. Users only need to provide a vague research direction, and the system can automatically refine it into specific topics and generate executable experiment plans.
2.  **Safety & Isolation**:
    *   All generated code runs in **Docker Containers**, completely isolated from the host environment, preventing auto-generated code from damaging the system or causing dependency conflicts.
3.  **Traceability & Exploration**:
    *   Introduces **Git** as the underlying recording mechanism for the experiment process. Every experiment step and code modification is submitted as a Commit.
    *   Supports **DFS (Depth-First Search)** style experiment path exploration. If a step fails or performs poorly, the system can backtrack and create new branches to try different schemes, forming a visualized Experiment Tree (Git Tree).
4.  **Human-in-the-Loop**:
    *   While pursuing automation, manual intervention interfaces are retained at critical nodes (such as risk assessment, plan confirmation, result review) to ensure the research direction meets user expectations.

---

## 2. Architecture Design

### 2.1 System Architecture Diagram
```mermaid
graph TD
    User[User] --> Frontend[Streamlit Frontend]
    Frontend --> Orchestrator[Experiment Orchestrator (ExperimentRunner)]
    
    subgraph "Agent Cluster"
        IdeaAgent[Idea Agent]
        DesignAgent[Design Agent]
        CodingAgent[Coding Agent]
        ReviewAgent[Review Agent]
        AnalysisAgent[Analysis Agent]
        WritingAgent[Writing Agent]
    end
    
    Orchestrator <--> Agent Cluster
    
    subgraph "Execution Environment"
        Docker[Docker Sandbox]
        Workspace[Experiment Workspace (Data/Experiments)]
        Git[Git Version Control]
    end
    
    CodingAgent --> Docker
    Docker <--> Workspace
    Workspace <--> Git
```

### 2.2 Core Modules Detail

#### **A. Frontend Interaction Layer (Frontend)**
*   Built on **Streamlit**, providing an intuitive operation interface.
*   **Idea Generator**: Supports refining vague concepts into specific topics.
*   **Experiment Dashboard**: Real-time display of experiment progress, logs, and generated charts (Artifacts).
*   **Git Tree Visualization**: Uses Graphviz to visualize experiment branches and attempt records, supporting node clicking and detail viewing.

#### **B. Agent Cluster (Backend Agents)**
All Agents are configured through a unified LLM interface (supporting OpenAI/DeepSeek/Gemini, etc.).
*   **IdeaAgent**: Responsible for divergent thinking, generating multiple research topics, and evaluating novelty.
*   **ExperimentDesignAgent**: Converts topics into detailed experiment steps (Plan), including environment dependency analysis and risk assessment.
*   **CodingAgent**: Responsible for specific code implementation. It not only generates code but also handles dependency installation, file reading/writing, etc.
*   **ReviewAgent**: **Quality Gatekeeper**. After each step execution, it reviews code execution results, logs, and generated files to judge whether the current step goal and global experiment goal are met.
*   **DataAnalysisAgent**: After the experiment ends, it automatically reads data files (CSV/JSON) and generates statistical charts and quantitative analysis reports.
*   **WritingAgent**: Automatically drafts papers conforming to academic standards based on experiment plans, process records, and analysis results.

#### **C. Infrastructure**
*   **Docker Sandbox**: 
    *   Automatically builds or reuses Docker images when each experiment starts.
    *   Uses Volume mounting to achieve data persistence, ensuring files generated inside the container can be synced back to the host.
*   **Git Versioning**:
    *   Each experiment directory is initialized as an independent Git repository.
    *   The system automatically submits Commits, with structured Messages recording (Step, Plan, Scheme, Result).
    *   Supports automatic branch switching to record every "retry" or "scheme change".

---

## 3. Feature Details

### 3.1 Idea Generation & Refinement
*   User inputs an area of interest (e.g., "Application of Reinforcement Learning in Gomoku").
*   The system analyzes the breadth of the field; if too broad, it generates multiple subdivisions; if specific, it refines it.
*   Generates proposal cards containing abstract, keywords, and feasibility analysis.

### 3.2 Interactive Experiment Planning
*   After selecting a topic, the system generates an experiment plan containing 5-8 steps.
*   **Environment Self-Check**: Automatically detects local Docker, Git environments, and whether required Python libraries might have conflicts.
*   **Risk Negotiation**: Identifies potential risks (e.g., requires GPU, requires private data), and the user can provide feedback or confirm to ignore risks at this stage.

### 3.3 Automated Execution & Correction
*   **Auto-Coding**: Generates Python scripts based on step descriptions.
*   **Sandbox Execution**: Runs scripts in Docker, capturing stdout/stderr.
*   **Self-Correction**: If execution fails, CodingAgent reads error logs and attempts to fix the code (default 3 retries).
*   **Result Review**: ReviewAgent intervenes to judge whether the execution result is logically correct (not just error-free, but also whether there is output).

### 3.4 Experiment Visualization & Management
*   **Real-time Logs**: Frontend displays current thinking processes and execution logs in real-time.
*   **Git Tree Diagram**: Graphically displays the exploration path of the experiment, clearly showing which attempts failed and which succeeded.
*   **Artifact Preview**: View generated CSV data, PNG charts, or code files directly on the web page.

---

## 4. Debugging & Startup

### 4.1 Environment Requirements
*   **OS**: macOS (Recommended), Linux, Windows (WSL2)
*   **Python**: 3.10+
*   **Docker**: Docker Daemon must be installed and running (for sandbox environment).
*   **Git**: Git must be installed on the system.

### 4.2 Installation Steps

1.  **Clone Project**
    ```bash
    git clone <repository_url>
    cd AutoResearchLab
    ```

2.  **Create Virtual Environment & Install Dependencies**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables**
    Copy `.env.example` (if exists) or create `.env` file directly:
    ```env
    # LLM Configuration (Backend/config.py will read these configs)
    # Option 1: Use SiliconFlow (DeepSeek)
    # SILICON_API_KEY=sk-xxxxxxxx
    
    # Option 2: Use Google Gemini
    GOOGLE_API_KEY=AIzaSyxxxxxxxxx
    ```
    *Note: Please confirm the currently enabled model configuration in `backend/config.py`.*

### 4.3 Start System

Run Streamlit Frontend Application:
```bash
streamlit run frontend/app.py
```
After startup, the browser will automatically open `http://localhost:8501`.

### 4.4 FAQ & Debugging

*   **Docker Connection Failed**:
    *   Symptom: "Docker Daemon not running" prompts when starting experiment.
    *   Solution: Ensure Docker Desktop is started and `docker ps` outputs correctly in the terminal.
*   **Git Tree Too Large**:
    *   Symptom: Git Tree takes up full screen after many experiment steps.
    *   Solution: Frontend is optimized to collapse by default with adaptive width. Click "Expand" to view details.
*   **Streamlit Warnings (use_container_width)**:
    *   Fixed in the latest version, replaced with `width="stretch"`.
*   **Experiment Stuck at Certain Step**:
    *   Check terminal background logs, or click "Stop" in frontend to stop experiment, then try "Retry".

---

## 5. Directory Structure

```
AutoResearchLab/
├── backend/                # Backend Core Logic
│   ├── agents/             # Agent Implementations (Coding, Design, Review...)
│   ├── execution/          # Experiment Execution Engine (Runner)
│   ├── sandbox/            # Docker Sandbox Management
│   ├── config.py           # Unified Config Center
│   └── ...
├── frontend/               # Frontend Interface
│   ├── app.py              # Entry File
│   ├── components/         # Functional Components (Dashboard, IdeaGenerator...)
│   └── ...
├── data/                   # Data Storage (configured in .gitignore)
│   ├── experiments/        # Specific Experiment Workspace (One folder per experiment)
│   ├── cache/              # Cache Data
│   └── ...
├── requirements.txt        # Project Dependencies
└── README.md               # Project Documentation
```
