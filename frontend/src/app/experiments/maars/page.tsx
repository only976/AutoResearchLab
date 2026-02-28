"use client"

import { useEffect } from "react"

const MAARS_SCRIPTS = [
  "https://cdn.socket.io/4.5.4/socket.io.min.js",
  "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.9/purify.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js",
  "/maars/js/utils.js",
  "/maars/js/config.js",
  "/maars/js/task-tree.js",
  "/maars/js/theme.js",
  "/maars/js/api.js",
  "/maars/js/plan.js",
  "/maars/js/thinking.js",
  "/maars/js/views.js",
  "/maars-overrides/sse.js",
  "/maars/app.js"
]

const MAARS_STYLES = [
  "https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;1,400&display=swap",
  "/maars/styles.css",
  "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css"
]

export default function MaarsPage() {
  useEffect(() => {
    const root = document.documentElement
    const prevTheme = root.getAttribute("data-theme")
    root.setAttribute("data-theme", "black")

    const existingMarker = document.querySelector("[data-maars-assets]")
    if (!existingMarker) {
      const marker = document.createElement("meta")
      marker.setAttribute("data-maars-assets", "true")
      document.head.appendChild(marker)

      MAARS_STYLES.forEach((href) => {
        const link = document.createElement("link")
        link.rel = "stylesheet"
        link.href = href
        link.setAttribute("data-maars-asset", "style")
        document.head.appendChild(link)
      })

      const loadSequential = async () => {
        for (const src of MAARS_SCRIPTS) {
          await new Promise<void>((resolve, reject) => {
            const script = document.createElement("script")
            script.src = src
            script.async = false
            script.defer = false
            script.setAttribute("data-maars-asset", "script")
            script.onload = () => resolve()
            script.onerror = () => reject(new Error(`Failed to load ${src}`))
            document.body.appendChild(script)
          })
        }
      }

      loadSequential().catch((err) => {
        console.error(err)
      })
    }

    return () => {
      if (prevTheme) root.setAttribute("data-theme", prevTheme)
      else root.removeAttribute("data-theme")
    }
  }, [])

  return (
    <div className="w-full">
      <div className="container">
        <header className="page-header">
          <div className="header-title">
            <h1>MAARS</h1>
            <p className="subtitle">Multi-Agent Automated Research System</p>
          </div>
        </header>

        <div id="settingsModal" className="modal">
          <div className="modal-content modal-content--settings">
            <div id="settingsForm" className="settings-form">
              <div className="settings-body">
                <aside className="settings-sidebar">
                  <nav className="settings-nav" role="navigation">
                    <button type="button" className="settings-nav-item" data-item="theme">
                      <span className="settings-nav-item-name">Theme</span>
                    </button>
                    <button type="button" className="settings-nav-item" data-item="db">
                      <span className="settings-nav-item-name">DB Operation</span>
                    </button>
                    <button type="button" className="settings-nav-item" data-item="execution">
                      <span className="settings-nav-item-name">Execution</span>
                    </button>
                    <button type="button" className="settings-nav-item" data-item="mode">
                      <span className="settings-nav-item-name">AI Mode</span>
                    </button>
                    <button type="button" className="settings-nav-item" data-item="preset">
                      <span className="settings-nav-item-name">Preset</span>
                    </button>
                  </nav>
                  <button type="button" className="btn-ghost settings-save-btn" id="settingsSaveBtn">Save</button>
                </aside>
                <main className="settings-main" id="settingsMain">
                  <div className="settings-panel" id="settingsPanelTheme" data-panel="theme">
                    <div className="settings-card">
                      <h3 className="settings-card-title">Theme</h3>
                      <div className="settings-options">
                        <button type="button" className="settings-option" data-theme="light">Light</button>
                        <button type="button" className="settings-option" data-theme="dark">Dark</button>
                        <button type="button" className="settings-option" data-theme="black">Black</button>
                      </div>
                    </div>
                  </div>
                  <div className="settings-panel" id="settingsPanelDb" data-panel="db">
                    <div className="settings-card">
                      <h3 className="settings-card-title">DB Operation</h3>
                      <div className="settings-db-actions">
                        <button type="button" className="btn-default" id="settingsRestoreBtn">Restore</button>
                        <button type="button" className="btn-danger" id="settingsClearDbBtn">Clear DB</button>
                      </div>
                    </div>
                  </div>
                  <div className="settings-panel" id="settingsPanelExecution" data-panel="execution">
                    <div className="settings-card">
                      <h3 className="settings-card-title">Execution</h3>
                      <div className="settings-field">
                        <label htmlFor="maxExecutionConcurrency">Max concurrent tasks</label>
                        <input type="number" id="maxExecutionConcurrency" min="1" max="32" defaultValue={7} />
                        <span className="settings-param-tip">Maximum number of tasks running in parallel during execution</span>
                      </div>
                    </div>
                  </div>
                  <div className="settings-panel" id="settingsPanelMode" data-panel="mode">
                    <div className="settings-card">
                      <h3 className="settings-card-title">AI Mode</h3>
                      <div className="settings-options" id="settingsModeOptions">
                        <button type="button" className="settings-option" data-item="mock">Mock</button>
                        <button type="button" className="settings-option" data-item="llm">LLM</button>
                        <button type="button" className="settings-option" data-item="llmagent">LLM+Agent</button>
                        <button type="button" className="settings-option" data-item="agent">Agent</button>
                      </div>
                    </div>
                    <div className="settings-card">
                      <h3 className="settings-card-title" id="settingsModeConfigTitle">Config</h3>
                      <div className="settings-mode-content" id="settingsModeContent"></div>
                    </div>
                  </div>
                  <div className="settings-panel" id="settingsPanelPreset" data-panel="preset">
                    <div className="settings-card">
                      <h3 className="settings-card-title">Preset</h3>
                      <div className="settings-preset-row">
                        <div className="settings-preset-list" id="settingsPresetList"></div>
                        <button type="button" className="settings-preset-add" id="settingsPresetAddBtn">+ New</button>
                      </div>
                    </div>
                    <div className="settings-card">
                      <h3 className="settings-card-title" id="settingsPresetEditTitle">Select preset</h3>
                      <div className="settings-fields">
                        <div className="settings-field">
                          <label htmlFor="presetLabel">Name</label>
                          <input type="text" id="presetLabel" placeholder="My Config" />
                        </div>
                        <div className="settings-field">
                          <label htmlFor="presetBaseUrl">Base URL</label>
                          <input type="url" id="presetBaseUrl" placeholder="https://api.openai.com/v1" />
                        </div>
                        <div className="settings-field">
                          <label htmlFor="presetApiKey">API Key</label>
                          <input type="password" id="presetApiKey" placeholder="sk-..." autoComplete="off" />
                        </div>
                        <div className="settings-field">
                          <label htmlFor="presetModel">Model</label>
                          <input type="text" id="presetModel" placeholder="gpt-4o" />
                        </div>
                      </div>
                      <div className="settings-phase-section">
                        <h4 className="settings-phase-title">Config by phase</h4>
                        <div className="settings-phase-grid" id="settingsPhaseCards"></div>
                      </div>
                      <div className="settings-actions">
                        <button type="button" id="settingsPresetDeleteBtn" className="btn-ghost">Delete preset</button>
                      </div>
                    </div>
                  </div>
                </main>
              </div>
            </div>
          </div>
        </div>

        <main className="main-content">
          <div className="idea-input-row">
            <input type="text" id="ideaInput" className="idea-input" placeholder="Enter your research idea..." />
            <button id="loadExampleIdeaBtn">Load Idea</button>
            <button id="generatePlanBtn">Plan</button>
            <button id="stopPlanBtn" className="stop-btn" style={{ display: "none" }}>Stop</button>
            <button id="executionBtn">Execute</button>
            <button id="stopExecutionBtn" className="stop-btn" style={{ display: "none" }}>Stop</button>
          </div>
          <div className="plan-agent-thinking-tree-row">
            <div className="plan-agent-tree-area" data-tree-area="plan">
              <div className="tree-view-tabs">
                <button type="button" className="tree-view-tab active" data-view="decomposition" aria-pressed="true">Decomposition</button>
                <button type="button" className="tree-view-tab" data-view="execution" aria-pressed="false">Execution</button>
                <button type="button" className="tree-view-tab" data-view="output" aria-pressed="false">Output</button>
              </div>
              <div className="tree-view-panel view-decomposition active" data-view-panel="decomposition">
                <div className="plan-agent-quality-badge" id="planAgentQualityBadge" title="" style={{ display: "none" }}></div>
                <div className="tree-container">
                  <div className="tasks-tree plan-agent-tasks-tree"></div>
                </div>
              </div>
              <div className="tree-view-panel view-execution" data-view-panel="execution">
                <div className="plan-agent-execution-tree-area" data-tree-area="execution">
                  <div className="tree-container">
                    <div className="tasks-tree plan-agent-execution-tree"></div>
                  </div>
                </div>
              </div>
              <div className="tree-view-panel view-output" data-view-panel="output">
                <div className="task-agent-output-area plan-agent-output-area" id="taskAgentOutputArea">
                  <div className="task-agent-output-content markdown-body" id="taskAgentOutputContent"></div>
                </div>
              </div>
            </div>
            <div className="plan-agent-thinking-area" id="planAgentThinkingArea">
              <div className="plan-agent-thinking-content markdown-body" id="planAgentThinkingContent"></div>
              <div className="plan-agent-thinking-placeholder" id="planAgentThinkingPlaceholder">Thinking will appear here when generating plan or executing tasks...</div>
            </div>
          </div>
        </main>
      </div>

      <div id="taskAgentOutputModal" className="task-agent-output-modal" aria-hidden="true">
        <div className="task-agent-output-modal-backdrop"></div>
        <div className="task-agent-output-modal-dialog">
          <div className="task-agent-output-modal-header">
            <span className="task-agent-output-modal-title" id="taskAgentOutputModalTitle">Task Output</span>
            <span className="task-agent-output-modal-actions">
              <button
                type="button"
                className="task-agent-output-modal-download"
                id="taskAgentOutputModalDownload"
                aria-label="Download"
                title="Download"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 4v16" />
                  <path d="M7 15l5 5 5-5" />
                </svg>
              </button>
              <button type="button" className="task-agent-output-modal-close" id="taskAgentOutputModalClose" aria-label="Close">×</button>
            </span>
          </div>
          <div className="task-agent-output-modal-body markdown-body" id="taskAgentOutputModalBody"></div>
        </div>
      </div>
    </div>
  )
}
