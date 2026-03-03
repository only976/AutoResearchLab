# Agent 目录结构规范

Idea、Plan、Task 三个 Agent 保持统一目录结构，便于维护与扩展。

## 统一结构

```
{agent}/
├── agent.py           # Agent 入口，*AgentMode=True 时调用
├── adk_runner.py      # Google ADK 驱动实现（仅 Agent 模式）
├── agent_tools.py     # 工具定义 + execute 逻辑
├── llm/               # 单轮 LLM 实现（Mock/LLM 模式）
│   ├── __init__.py
│   └── executor.py    # 各阶段 LLM 调用
├── prompts/           # Prompt 文件
│   ├── {agent}-agent-prompt.txt   # Agent 模式 system prompt
│   └── reflect-prompt.txt         # Self-Reflection 评估 prompt
├── skills/            # Agent Skills（SKILL.md + references/scripts 等）
│   └── {skill-name}/
│       └── SKILL.md   # YAML frontmatter + Markdown 内容
└── __init__.py
```

## 各 Agent 差异

| 组件 | Idea | Plan | Task |
|------|------|------|------|
| 编排 | 无（API 直接调用） | `index.py` | `runner.py` |
| 领域模块 | `arxiv.py` | `execution_builder.py` | `artifact_resolver.py`, `pools.py`, `web_tools.py` |
| LLM 子模块 | `llm/executor.py` | `llm/executor.py` | `llm/executor.py`, `llm/validation.py` |

## Skills 规范

- **位置**：`{agent}/skills/{skill-name}/`
- **入口**：`SKILL.md`，含 YAML frontmatter（`name`, `description`）
- **发现**：`shared/skill_utils.list_skills(skills_root)` 扫描目录
- **加载**：`shared/skill_utils.load_skill(skills_root, name)` 读取 SKILL.md

Task Agent 的 Skills 可含 `scripts/`、`references/`；Idea/Plan 以 SKILL.md 为主。

## 解耦要点

1. **Skill I/O**：统一由 `shared/skill_utils` 提供，各 agent_tools 仅传入 `*_SKILLS_ROOT`
2. **ADK 桥接**：工具格式转换、ExecutorTool 封装由 `shared/adk_bridge` 统一处理
3. **LLM 调用**：单轮调用由 `shared/llm_client.chat_completion` 统一；Mock 由 `test/mock_stream.mock_chat_completion` 统一
