/**
 * MAARS Research flow - Create page + Research detail page (auto pipeline).
 */
(function () {
    'use strict';

    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
    if (!cfg || !api) return;

    const homeView = document.getElementById('homeView');
    const researchView = document.getElementById('researchView');
    const promptInput = document.getElementById('researchPromptInput');
    const createBtn = document.getElementById('createResearchBtn');

    const breadcrumbEl = document.getElementById('researchBreadcrumb');
    const titleEl = document.getElementById('researchTitle');

    const stageButtons = {
        refine: document.getElementById('stageBtnRefine'),
        plan: document.getElementById('stageBtnPlan'),
        execute: document.getElementById('stageBtnExecute'),
        paper: document.getElementById('stageBtnPaper'),
    };
    const stageMetaEls = {
        refine: document.getElementById('stageMetaRefine'),
        plan: document.getElementById('stageMetaPlan'),
        execute: document.getElementById('stageMetaExecute'),
        paper: document.getElementById('stageMetaPaper'),
    };
    const stageActionBtns = {
        refine: {
            run: document.getElementById('stageRunRefine'),
            resume: document.getElementById('stageResumeRefine'),
            retry: document.getElementById('stageRetryRefine'),
            stop: document.getElementById('stageStopRefine'),
        },
        plan: {
            run: document.getElementById('stageRunPlan'),
            resume: document.getElementById('stageResumePlan'),
            retry: document.getElementById('stageRetryPlan'),
            stop: document.getElementById('stageStopPlan'),
        },
        execute: {
            run: document.getElementById('stageRunExecute'),
            resume: document.getElementById('stageResumeExecute'),
            retry: document.getElementById('stageRetryExecute'),
            stop: document.getElementById('stageStopExecute'),
        },
        paper: {
            run: document.getElementById('stageRunPaper'),
            resume: document.getElementById('stageResumePaper'),
            retry: document.getElementById('stageRetryPaper'),
            stop: document.getElementById('stageStopPaper'),
        },
    };

    const panelRefine = document.getElementById('researchPanelRefine');
    const panelWorkbench = document.getElementById('researchDetailHost');
    const panelPaper = document.getElementById('researchPanelPaper');
    const executeSplitterEl = document.getElementById('researchExecuteSplitter');

    const refineRefsEl = document.getElementById('researchRefineReferences');
    const refineLogicEl = document.getElementById('researchRefineLogic');
    const paperBodyEl = document.getElementById('researchPaperBody');

    const executeStreamEl = document.getElementById('researchExecuteStream');
    const executeStreamBodyEl = document.getElementById('researchExecuteStreamBody');
    const executeRuntimeBadgeEl = document.getElementById('researchExecutionRuntimeBadge');
    const executeRuntimeMetaEl = document.getElementById('researchExecutionRuntimeMeta');

    const treeTabsHost = panelWorkbench?.querySelector?.('.tree-view-tabs');
    const treeTabButtons = treeTabsHost ? Array.from(treeTabsHost.querySelectorAll('.tree-view-tab')) : [];
    const treePanels = panelWorkbench ? Array.from(panelWorkbench.querySelectorAll('.tree-view-panel')) : [];

    let currentResearchId = null;
    let activeStage = 'refine';
    let stageData = {
        papers: [],
        refined: '',
        refineThinking: '',
        paper: '',
    };
    let executionGraphPayload = {
        treeData: [],
        layout: null,
    };

    let executeState = {
        order: [],
        statuses: new Map(),
        recentOutputsByTask: new Map(),
        taskMetaById: new Map(),
        messages: [],
    };
    let executionRuntimeStatus = null;
    let runtimeStatusRequestId = 0;
    let executeSplitRatio = 80;
    let currentStageState = {
        refine: { started: false },
        plan: { started: false },
        execute: { started: false },
        paper: { started: false },
    };
    let stageStatusDetails = {
        refine: { status: 'idle', message: 'idle' },
        plan: { status: 'idle', message: 'idle' },
        execute: { status: 'idle', message: 'idle' },
        paper: { status: 'idle', message: 'idle' },
    };

    function setStageStarted(stage, started) {
        if (!currentStageState[stage]) return;
        currentStageState[stage].started = !!started;
        renderStageButtons();
    }

    function renderStageButtons(activeStage) {
        const order = ['refine', 'plan', 'execute', 'paper'];
        const current = String(activeStage || '').trim() || String(window.MAARS?.researchCurrentStage || '') || 'refine';
        const currentRank = order.indexOf(current);

        Object.entries(stageButtons).forEach(([stage, btn]) => {
            if (!btn) return;
            const started = !!currentStageState?.[stage]?.started;
            const stageRank = order.indexOf(stage);
            btn.disabled = !started;
            btn.setAttribute('aria-disabled', started ? 'false' : 'true');
            btn.classList.toggle('is-started', started);
            btn.classList.toggle('is-active', stage === current);
            btn.classList.toggle('is-completed', started && currentRank >= 0 && stageRank >= 0 && stageRank < currentRank);
        });
        renderStageStatusDetails();
    }

    function renderStageStatusDetails() {
        const runningStage = Object.entries(stageStatusDetails).find(([, info]) => String(info?.status || '') === 'running')?.[0] || '';
        Object.entries(stageMetaEls).forEach(([stage, metaEl]) => {
            if (!metaEl) return;
            const info = stageStatusDetails[stage] || { status: 'idle', message: 'idle' };
            const status = String(info.status || 'idle').trim() || 'idle';
            const message = String(info.message || status).trim() || status;
            metaEl.textContent = `${status} · ${message}`;
        });

        Object.entries(stageActionBtns).forEach(([stage, actions]) => {
            const info = stageStatusDetails[stage] || { status: 'idle' };
            const status = String(info.status || 'idle').trim() || 'idle';
            const stageStarted = !!currentStageState?.[stage]?.started;
            const isRunningSelf = status === 'running';
            const hasOtherRunning = !!runningStage && runningStage !== stage;
            const blocked = hasOtherRunning;
            if (actions?.run) actions.run.disabled = blocked;
            if (actions?.resume) actions.resume.disabled = blocked || !(status === 'stopped' || status === 'failed');
            if (actions?.retry) actions.retry.disabled = blocked || !(stageStarted || status === 'failed' || status === 'stopped');
            if (actions?.stop) actions.stop.disabled = blocked || !isRunningSelf;
        });
    }

    function _mdToHtml(md) {
        const src = (md == null ? '' : String(md));
        let html = '';
        try {
            html = (typeof marked !== 'undefined') ? marked.parse(src) : src;
        } catch (_) {
            html = src;
        }
        try {
            if (typeof DOMPurify !== 'undefined') html = DOMPurify.sanitize(html);
        } catch (_) {}
        return html;
    }

    function _renderRefinePanel() {
        if (refineLogicEl) {
            const refined = (stageData.refined || '').trim();
            const thinking = (stageData.refineThinking || '').trim();
            refineLogicEl.innerHTML = refined
                ? _mdToHtml(refined)
                : (thinking ? _mdToHtml(thinking) : '—');
        }
        if (refineRefsEl) {
            const papers = Array.isArray(stageData.papers) ? stageData.papers : [];
            if (!papers.length) {
                refineRefsEl.textContent = '—';
            } else {
                const md = papers.map((p, i) => {
                    const title = (p?.title || '').replace(/\s+/g, ' ').trim();
                    const url = p?.url || '';
                    const head = url ? `${i + 1}. [${title || 'Untitled'}](${url})` : `${i + 1}. ${title || 'Untitled'}`;
                    return `${head}`;
                }).join('\n');
                refineRefsEl.innerHTML = _mdToHtml(md);
            }
        }
    }

    function _renderPaperPanel() {
        if (!paperBodyEl) return;
        const content = (stageData.paper || '').trim();
        paperBodyEl.innerHTML = content ? _mdToHtml(content) : '—';
    }

    function _setPanelActive(panelEl, on) {
        if (!panelEl) return;
        panelEl.classList.toggle('is-active', !!on);
    }

    function _loadExecuteSplitRatio() {
        try {
            const raw = localStorage.getItem('maars-execute-split-ratio');
            const val = Number(raw);
            if (Number.isFinite(val)) executeSplitRatio = Math.max(35, Math.min(90, val));
        } catch (_) {}
    }

    function _saveExecuteSplitRatio() {
        try {
            localStorage.setItem('maars-execute-split-ratio', String(executeSplitRatio));
        } catch (_) {}
    }

    function _applyExecuteSplitRatio() {
        if (!panelWorkbench) return;
        panelWorkbench.style.setProperty('--execute-left-ratio', String(executeSplitRatio));
    }

    function setTreeView(view) {
        const v = String(view || '').trim();
        treeTabButtons.forEach((btn) => {
            const isActive = (btn.getAttribute('data-view') || '') === v;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
        treePanels.forEach((p) => {
            const isActive = (p.getAttribute('data-view-panel') || '') === v;
            p.classList.toggle('active', isActive);
        });
    }

    function setActiveStage(stage) {
        const s = String(stage || '').trim();
        activeStage = s;
        window.MAARS = window.MAARS || {};
        window.MAARS.researchCurrentStage = s;
        renderStageButtons(s);

        // Panels
        _setPanelActive(panelRefine, s === 'refine');
        _setPanelActive(panelWorkbench, s === 'plan' || s === 'execute');
        _setPanelActive(panelPaper, s === 'paper');

        // Workbench modes
        if (panelWorkbench) {
            panelWorkbench.classList.toggle('research-workbench--plan', s === 'plan');
            panelWorkbench.classList.toggle('research-workbench--execute', s === 'execute');
        }

        if (executeStreamEl) {
            executeStreamEl.hidden = !(s === 'execute');
        }

        if (s === 'plan') {
            setTreeView('decomposition');
        } else if (s === 'execute') {
            _applyExecuteSplitRatio();
            setTreeView('execution');
            if (executionGraphPayload?.layout && Array.isArray(executionGraphPayload?.treeData)) {
                window.MAARS?.taskTree?.renderExecutionTree?.(executionGraphPayload.treeData, executionGraphPayload.layout);
            }
            renderExecuteStream();
            refreshExecutionRuntimeStatus();
        }

        if (s === 'refine') _renderRefinePanel();
        if (s === 'paper') _renderPaperPanel();
    }

    function _getTaskDataFromNode(node) {
        if (!node) return null;
        const raw = node.getAttribute('data-task-data');
        if (!raw) return null;
        try {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) return parsed[0] || null;
            return parsed;
        } catch (_) {
            return null;
        }
    }

    function _stringifyOutput(val) {
        if (val == null) return '';
        if (typeof val === 'string') return val;
        try {
            if (typeof val === 'object' && val !== null && 'content' in val && typeof val.content === 'string') return val.content;
        } catch (_) {}
        try {
            return JSON.stringify(val, null, 2);
        } catch (_) {
            return String(val);
        }
    }

    function _ensureTaskInOrder(taskId) {
        const id = String(taskId || '').trim();
        if (!id) return '';
        if (!executeState.order.includes(id)) executeState.order.push(id);
        return id;
    }

    function _upsertTaskMeta(task) {
        const id = String(task?.task_id || '').trim();
        if (!id) return;
        const current = executeState.taskMetaById.get(id) || {};
        executeState.taskMetaById.set(id, {
            ...current,
            task_id: id,
            title: String(task?.title || current.title || '').trim(),
            description: String(task?.description || task?.objective || current.description || '').trim(),
            status: String(task?.status || current.status || '').trim(),
        });
        _ensureTaskInOrder(id);
    }

    function _getTaskMetaById(taskId) {
        const id = String(taskId || '').trim();
        if (!id) return null;
        return executeState.taskMetaById.get(id) || null;
    }

    function _pushRecentOutput(taskId, outputText) {
        const id = String(taskId || '').trim();
        if (!id) return;
        const text = String(outputText || '').trim();
        if (!text) return;
        const list = executeState.recentOutputsByTask.get(id) || [];
        list.push(text);
        while (list.length > 8) list.shift();
        executeState.recentOutputsByTask.set(id, list);
    }

    function _statusLabel(status) {
        const s = String(status || '').trim() || 'undone';
        const map = {
            undone: 'Pending',
            doing: 'Running',
            done: 'Done',
            'execution-failed': 'Execution Failed',
            'validation-failed': 'Validation Failed',
        };
        return map[s] || s;
    }

    function _statusTone(status) {
        const s = String(status || '').trim();
        if (s === 'doing') return 'doing';
        if (s === 'done') return 'done';
        if (s === 'execution-failed' || s === 'validation-failed') return 'failed';
        return 'pending';
    }

    function renderExecutionRuntimeStatus(status) {
        executionRuntimeStatus = status && typeof status === 'object' ? status : null;
        if (!executeRuntimeBadgeEl || !executeRuntimeMetaEl) return;

        const next = executionRuntimeStatus || {};
        const enabled = !!next.enabled;
        const connected = !!next.connected;
        const containerRunning = !!next.containerRunning;
        const running = !!next.running;

        let badgeText = 'Docker: checking…';
        let tone = 'is-warn';
        if (!enabled) {
            badgeText = 'Docker: disabled';
            tone = 'is-warn';
        } else if (!next.available) {
            badgeText = 'Docker: not found';
            tone = 'is-error';
        } else if (!connected) {
            badgeText = 'Docker: disconnected';
            tone = 'is-error';
        } else if (containerRunning && running) {
            badgeText = 'Docker: running';
            tone = 'is-ok';
        } else if (containerRunning) {
            badgeText = 'Docker: connected';
            tone = 'is-ok';
        } else {
            badgeText = 'Docker: ready';
            tone = 'is-warn';
        }

        executeRuntimeBadgeEl.textContent = badgeText;
        executeRuntimeBadgeEl.classList.remove('is-ok', 'is-warn', 'is-error');
        executeRuntimeBadgeEl.classList.add(tone);

        const metaParts = [];
        if (next.serverVersion) metaParts.push(`Engine ${next.serverVersion}`);
        if (next.image) metaParts.push(`Image ${next.image}`);
        if (next.executionRunId) metaParts.push(`Run ${next.executionRunId}`);
        if (next.error) metaParts.push(String(next.error).trim());
        if (!metaParts.length && !enabled) metaParts.push('Enable Task Agent mode to use Docker-backed execution.');
        executeRuntimeMetaEl.textContent = metaParts.join(' · ');
    }

    async function refreshExecutionRuntimeStatus(explicitIds) {
        if (!executeRuntimeBadgeEl) return null;
        const requestId = ++runtimeStatusRequestId;
        if (!executionRuntimeStatus) {
            renderExecutionRuntimeStatus({ enabled: true, available: true, connected: false });
        }
        try {
            const ids = explicitIds && (explicitIds.ideaId || explicitIds.planId)
                ? explicitIds
                : await cfg.resolvePlanIds();
            const status = await api.getExecutionRuntimeStatus?.(ids?.ideaId || '', ids?.planId || '');
            if (requestId !== runtimeStatusRequestId) return null;
            renderExecutionRuntimeStatus(status || {});
            return status || null;
        } catch (error) {
            if (requestId !== runtimeStatusRequestId) return null;
            renderExecutionRuntimeStatus({
                enabled: true,
                available: true,
                connected: false,
                error: error?.message || 'Failed to load Docker runtime status',
            });
            return null;
        }
    }

    function _appendExecuteMessage(message) {
        if (!message || !message.taskId && message.kind !== 'system') return;
        const dedupeKey = String(message.dedupeKey || '').trim();
        if (dedupeKey) {
            const exists = executeState.messages.some((m) => m.dedupeKey === dedupeKey);
            if (exists) return;
        }
        executeState.messages.push({
            id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            at: Date.now(),
            ...message,
        });
        if (executeState.messages.length > 240) executeState.messages = executeState.messages.slice(-240);
    }

    function _upsertExecuteThinkingMessage(taskId, operation, body, scheduleInfo) {
        const id = String(taskId || '').trim();
        if (!id) return;
        const op = String(operation || 'Execute').trim() || 'Execute';
        const text = String(body || '').trim();
        if (!text) return;

        const turn = Number(scheduleInfo?.turn);
        const maxTurns = Number(scheduleInfo?.max_turns);
        const toolName = String(scheduleInfo?.tool_name || '').trim();

        let title = `${id} · ${op}`;
        if (toolName) title += ` · ${toolName}`;

        const dedupeKey = `thinking:${id}:${op}`;
        const idx = executeState.messages.findIndex((m) => m?.dedupeKey === dedupeKey);
        const bodyText = Number.isFinite(turn) && Number.isFinite(maxTurns)
            ? `[${turn}/${maxTurns}] ${text}`
            : text;

        if (idx >= 0) {
            const prev = executeState.messages[idx] || {};
            executeState.messages[idx] = {
                ...prev,
                at: Date.now(),
                title,
                body: bodyText,
                status: executeState.statuses.get(id) || prev.status || 'doing',
            };
            return;
        }

        _appendExecuteMessage({
            taskId: id,
            kind: 'assistant',
            title,
            body: bodyText,
            status: executeState.statuses.get(id) || 'doing',
            dedupeKey,
        });
    }

    function _seedExecutionState(treeData, execution, outputs) {
        executeState.order = [];
        executeState.statuses = new Map();
        executeState.recentOutputsByTask = new Map();
        executeState.taskMetaById = new Map();
        executeState.messages = [];

        const treeTasks = Array.isArray(treeData) ? treeData : [];
        const execTasks = Array.isArray(execution?.tasks) ? execution.tasks : [];
        treeTasks.forEach(_upsertTaskMeta);
        execTasks.forEach((task) => {
            _upsertTaskMeta(task);
            if (task?.status) executeState.statuses.set(task.task_id, String(task.status));
        });

        const outputMap = outputs && typeof outputs === 'object' ? outputs : {};
        Object.entries(outputMap).forEach(([taskId, output]) => {
            const text = _stringifyOutput(output).trim();
            if (!text) return;
            _ensureTaskInOrder(taskId);
            _pushRecentOutput(taskId, text);
        });

        _appendExecuteMessage({
            kind: 'system',
            title: 'Execution timeline ready',
            body: execTasks.length ? `Loaded ${execTasks.length} execution steps.` : 'Waiting for execution to start.',
            dedupeKey: `seed:${currentResearchId || ''}`,
        });

        executeState.order.forEach((taskId) => {
            const meta = _getTaskMetaById(taskId) || {};
            const status = executeState.statuses.get(taskId) || meta.status || 'undone';
            _appendExecuteMessage({
                taskId,
                kind: 'assistant',
                title: meta.title || taskId,
                body: meta.description || 'Task prepared.',
                status,
                dedupeKey: `seed-task:${taskId}:${status}`,
            });

            const outputsForTask = executeState.recentOutputsByTask.get(taskId) || [];
            if (outputsForTask.length) {
                _appendExecuteMessage({
                    taskId,
                    kind: status === 'execution-failed' || status === 'validation-failed' ? 'error' : 'output',
                    title: meta.title || taskId,
                    body: outputsForTask[outputsForTask.length - 1],
                    status,
                    dedupeKey: `seed-output:${taskId}`,
                });
            }
        });
    }

    function renderExecuteStream() {
        if (!executeStreamBodyEl) return;
        const wasNearBottom = (executeStreamBodyEl.scrollHeight - executeStreamBodyEl.scrollTop - executeStreamBodyEl.clientHeight) < 48;
        const messages = Array.isArray(executeState.messages) ? executeState.messages : [];

        executeStreamBodyEl.textContent = '';

        if (!messages.length) {
            const empty = document.createElement('div');
            empty.className = 'research-execute-empty';
            empty.textContent = '执行开始后，这里会像对话流一样持续展示每一步的状态与产出。';
            executeStreamBodyEl.appendChild(empty);
            return;
        }

        messages.forEach((message) => {
            const taskId = String(message.taskId || '').trim();
            const wrap = document.createElement('div');
            wrap.className = `research-execute-message research-execute-message--${message.kind || 'assistant'}`;

            const meta = document.createElement('div');
            meta.className = 'research-execute-message-meta';

            if (taskId) {
                const taskEl = document.createElement('span');
                taskEl.className = 'research-execute-message-task';
                taskEl.textContent = taskId;
                meta.appendChild(taskEl);
            }

            const kindEl = document.createElement('span');
            kindEl.className = 'research-execute-message-kind';
            kindEl.textContent = message.kind === 'output'
                ? 'Output'
                : message.kind === 'error'
                    ? 'Error'
                    : message.kind === 'system'
                        ? 'System'
                        : 'Step';
            meta.appendChild(kindEl);

            wrap.appendChild(meta);

            const bubble = document.createElement('div');
            bubble.className = 'research-execute-message-bubble';

            if (message.title) {
                const titleEl = document.createElement('div');
                titleEl.className = 'research-execute-message-title';
                titleEl.textContent = message.title;
                bubble.appendChild(titleEl);
            }

            const bodyEl = document.createElement('div');
            bodyEl.className = 'research-execute-message-body';
            const bodyText = String(message.body || '').trim() || '—';
            bodyEl.textContent = bodyText.length > 6000 ? bodyText.slice(-6000) : bodyText;
            bubble.appendChild(bodyEl);

            if (message.status) {
                const statusEl = document.createElement('div');
                statusEl.className = 'research-execute-message-status';
                const dot = document.createElement('span');
                dot.className = `research-execute-status-dot is-${_statusTone(message.status)}`;
                const label = document.createElement('span');
                label.textContent = _statusLabel(message.status);
                statusEl.appendChild(dot);
                statusEl.appendChild(label);
                bubble.appendChild(statusEl);
            }

            wrap.appendChild(bubble);
            executeStreamBodyEl.appendChild(wrap);
        });

        if (wasNearBottom || executeStreamBodyEl.childElementCount <= 2) {
            executeStreamBodyEl.scrollTop = executeStreamBodyEl.scrollHeight;
        }
    }

    function _getQueryParam(name) {
        try {
            const params = new URLSearchParams(window.location.search || '');
            return (params.get(name) || '').trim();
        } catch (_) {
            return '';
        }
    }

    function _getResearchIdFromUrl() {
        // New routing: research_detail.html?researchId=...
        const byQuery = _getQueryParam('researchId') || _getQueryParam('rid');
        if (byQuery) return byQuery;
        // Back-compat: old hash route #/r/<id>
        const hash = (window.location.hash || '').replace(/^#/, '');
        const m = hash.match(/^\/r\/(.+)$/);
        if (m) return decodeURIComponent(m[1]);
        return '';
    }

    function navigateToCreateResearch() {
        // Dedicated create page
        window.location.href = 'research.html';
    }

    function navigateToResearch(researchId) {
        if (!researchId) return;
        window.location.href = `research_detail.html?researchId=${encodeURIComponent(researchId)}`;
    }

    function _scrollToDetails() {
        const host = document.getElementById('researchDetailHost');
        if (!host) return;
        host.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function initStageNav() {
        Object.entries(stageButtons).forEach(([stage, btn]) => {
            if (!btn) return;
            btn.addEventListener('click', () => {
                if (btn.disabled) return;
                setActiveStage(stage);
            });
        });
    }

    function initTreeTabs() {
        if (!treeTabButtons.length) return;
        treeTabButtons.forEach((btn) => {
            btn.addEventListener('click', () => {
                const view = btn.getAttribute('data-view') || 'decomposition';
                setTreeView(view);
            });
        });
        document.addEventListener('maars:switch-to-output-tab', () => {
            // Only switch when execute stage is active; avoid overriding plan/refine/paper.
            if (activeStage === 'execute') setTreeView('output');
        });
    }

    function initExecuteSplitter() {
        if (!executeSplitterEl || !panelWorkbench) return;

        _loadExecuteSplitRatio();
        _applyExecuteSplitRatio();

        let dragging = false;

        const onPointerMove = (e) => {
            if (!dragging) return;
            const rect = panelWorkbench.getBoundingClientRect();
            if (!rect || rect.width <= 0) return;
            const x = Number(e.clientX || 0);
            const pct = ((x - rect.left) / rect.width) * 100;
            executeSplitRatio = Math.max(35, Math.min(90, pct));
            _applyExecuteSplitRatio();
        };

        const stopDrag = () => {
            if (!dragging) return;
            dragging = false;
            document.body.style.userSelect = '';
            document.body.style.cursor = '';
            _saveExecuteSplitRatio();
            window.removeEventListener('pointermove', onPointerMove);
            window.removeEventListener('pointerup', stopDrag);
            window.removeEventListener('pointercancel', stopDrag);
        };

        executeSplitterEl.addEventListener('pointerdown', (e) => {
            if (activeStage !== 'execute') return;
            dragging = true;
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
            try { executeSplitterEl.setPointerCapture(e.pointerId); } catch (_) {}
            window.addEventListener('pointermove', onPointerMove);
            window.addEventListener('pointerup', stopDrag);
            window.addEventListener('pointercancel', stopDrag);
        });
    }

    async function createResearchFromHome() {
        const prompt = (promptInput?.value || '').trim();
        if (!prompt) return;
        createBtn && (createBtn.disabled = true);
        try {
            const { researchId } = await api.createResearch(prompt);
            if (!researchId) throw new Error('Create failed');
            document.dispatchEvent(new CustomEvent('maars:research-list-refresh'));
            navigateToResearch(researchId);
        } catch (e) {
            console.error(e);
            alert(e?.message || 'Failed to create research');
        } finally {
            createBtn && (createBtn.disabled = false);
        }
    }

    async function loadResearch(researchId) {
        currentResearchId = researchId;
        cfg.setCurrentResearchId?.(researchId);

        // clear UI, then restore from DB snapshot
        document.dispatchEvent(new CustomEvent('maars:restore-start'));

        const data = await api.getResearch(researchId);
        const research = data?.research || {};
        const idea = data?.idea || null;
        const plan = data?.plan || null;
        const execution = data?.execution || null;
        const outputs = data?.outputs || {};
        const paper = data?.paper || null;

        if (breadcrumbEl) breadcrumbEl.textContent = 'Research';
        if (titleEl) titleEl.textContent = research.title || research.researchId || 'Research';

        stageData.originalIdea = (idea?.idea || research.prompt || '').trim();
        stageData.papers = Array.isArray(idea?.papers) ? idea.papers : [];
        stageData.refined = (idea?.refined_idea || '').trim();
        stageData.refineThinking = '';
        stageData.paper = (paper?.content || '').trim();
        _renderRefinePanel();
        _renderPaperPanel();

        // Stage enablement: stage becomes clickable once started.
        // Use DB snapshot heuristics + runtime events.
        currentStageState = {
            refine: { started: !!(research.currentIdeaId || stageData.refined || stageData.papers.length) },
            plan: { started: !!(plan && Array.isArray(plan.tasks) && plan.tasks.length) },
            execute: { started: !!(execution && Array.isArray(execution.tasks) && execution.tasks.length) },
            paper: { started: !!(paper && String(paper.content || '').trim()) },
        };
        stageStatusDetails = {
            refine: { status: 'idle', message: 'idle' },
            plan: { status: 'idle', message: 'idle' },
            execute: { status: 'idle', message: 'idle' },
            paper: { status: 'idle', message: 'idle' },
        };
        const rs = String(research.stage || 'refine').trim() || 'refine';
        const rss = String(research.stageStatus || 'idle').trim() || 'idle';
        if (stageStatusDetails[rs]) {
            stageStatusDetails[rs] = { status: rss, message: rss };
        }
        renderStageButtons();

        const ideaId = research.currentIdeaId || '';
        const planId = research.currentPlanId || '';
        cfg.setCurrentIdeaId?.(ideaId);
        cfg.setCurrentPlanId?.(planId);

        let treePayload = { treeData: [], layout: null };
        let executionLayout = null;
        if (ideaId && planId) {
            try {
                const res = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/plan/tree?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`);
                const json = await res.json();
                if (res.ok) treePayload = { treeData: json.treeData || [], layout: json.layout || null };
            } catch (_) {}

            // Restore execute tree layout as well; otherwise Execute panel appears empty on revisit.
            try {
                const execTasks = Array.isArray(execution?.tasks) ? execution.tasks : [];
                if (execTasks.length) {
                    const layoutRes = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/plan/layout`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ execution, ideaId, planId }),
                    });
                    const layoutJson = await layoutRes.json().catch(() => ({}));
                    if (layoutRes.ok && layoutJson?.layout) {
                        executionLayout = layoutJson.layout;
                        executionGraphPayload = {
                            treeData: Array.isArray(layoutJson.layout?.treeData) ? layoutJson.layout.treeData : [],
                            layout: layoutJson.layout?.layout || null,
                        };
                    }
                }
            } catch (_) {}
        }

        document.dispatchEvent(new CustomEvent('maars:restore-complete', {
            detail: {
                ideaId,
                planId,
                treePayload,
                plan,
                layout: executionLayout,
                execution,
                outputs: outputs || {},
                ideaText: idea?.idea || research.prompt || '',
            },
        }));

        _seedExecutionState(treePayload.treeData, execution, outputs);
        if (executionGraphPayload?.layout && activeStage === 'execute') {
            window.MAARS?.taskTree?.renderExecutionTree?.(executionGraphPayload.treeData, executionGraphPayload.layout);
        }
        if (activeStage === 'execute') renderExecuteStream();
        refreshExecutionRuntimeStatus({ ideaId, planId });

        // Restore refine + paper output using their normal event paths.
        if (idea && (idea.keywords || idea.papers || idea.refined_idea)) {
            document.dispatchEvent(new CustomEvent('maars:idea-complete', {
                detail: {
                    ideaId,
                    keywords: idea.keywords || [],
                    papers: idea.papers || [],
                    refined_idea: idea.refined_idea || '',
                },
            }));
        }
        if (paper?.content) {
            document.dispatchEvent(new CustomEvent('maars:paper-complete', {
                detail: {
                    ideaId,
                    planId,
                    content: paper.content,
                    format: paper.format || 'markdown',
                },
            }));
        }

        // Auto-run pipeline when entering research page.
        // Only auto-run on first entry (idle). On revisit, show snapshot and let user Retry manually.
        try {
            const stageStatus = String(research.stageStatus || '').trim().toLowerCase();
            if (stageStatus === 'idle') {
                await api.runResearch(researchId);
            }
        } catch (e) {
            // Ignore 409 conflicts (already running)
            const msg = String(e?.message || '');
            if (!/already running|409/.test(msg)) console.warn('runResearch failed', e);
        }
    }

    function initDetailControls(researchId) {
        const bindStageAction = (stage, action, handler) => {
            const btn = stageActionBtns?.[stage]?.[action];
            if (!btn) return;
            btn.addEventListener('click', async () => {
                if (!researchId) return;
                btn.disabled = true;
                try {
                    await handler();
                    document.dispatchEvent(new CustomEvent('maars:research-list-refresh'));
                } catch (e) {
                    console.error(e);
                    alert(e?.message || `Failed to ${action} stage`);
                } finally {
                    renderStageStatusDetails();
                }
            });
        };

        ['refine', 'plan', 'execute', 'paper'].forEach((stage) => {
            bindStageAction(stage, 'run', async () => {
                await api.runResearchStage(researchId, stage);
                setActiveStage(stage);
            });
            bindStageAction(stage, 'resume', async () => {
                await api.resumeResearchStage(researchId, stage);
                setActiveStage(stage);
            });
            bindStageAction(stage, 'retry', async () => {
                await api.retryResearchStage(researchId, stage);
                setActiveStage(stage);
            });
            bindStageAction(stage, 'stop', async () => {
                await api.stopResearchStage(researchId, stage);
            });
        });
    }

    function initEventBridges() {
        // Update stage state based on live pipeline events.
        document.addEventListener('maars:idea-start', () => setStageStarted('refine', true));
        document.addEventListener('maars:plan-start', () => setStageStarted('plan', true));
        document.addEventListener('maars:task-start', () => setStageStarted('execute', true));
        document.addEventListener('maars:paper-start', () => setStageStarted('paper', true));
        document.addEventListener('maars:task-start', () => refreshExecutionRuntimeStatus());

        document.addEventListener('maars:research-stage', (e) => {
            const d = e?.detail || {};
            if (d.researchId && currentResearchId && d.researchId !== currentResearchId) return;
            const stage = String(d.stage || '').trim();
            const status = String(d.status || '').trim() || 'idle';
            const error = String(d.error || '').trim();
            if (stage && currentStageState[stage] != null) {
                if (status === 'running' || status === 'completed' || status === 'stopped' || status === 'failed') {
                    setStageStarted(stage, true);
                }
                stageStatusDetails[stage] = {
                    status,
                    message: error || status,
                };
                renderStageButtons(stage);
                if (status === 'running' || status === 'completed') {
                    setActiveStage(stage);
                }
            }
            document.dispatchEvent(new CustomEvent('maars:research-list-refresh'));
        });

        document.addEventListener('maars:research-error', (e) => {
            const d = e?.detail || {};
            if (d.researchId && currentResearchId && d.researchId !== currentResearchId) return;
            if (d.error) {
                console.warn('Research error:', d.error);
                const msg = String(d.error || '').trim();
                if (refineLogicEl && !String(stageData.refined || '').trim()) {
                    refineLogicEl.innerHTML = _mdToHtml(`> Refine failed\n\n${msg}`);
                }
            }
        });

        // Keep sidebar list in sync
        document.addEventListener('maars:research-list-refresh', () => {
            window.MAARS?.sidebar?.refreshResearchList?.();
        });

        // Keep refine/paper panels updated
        document.addEventListener('maars:idea-complete', (e) => {
            const d = e?.detail || {};
            if (d.idea) stageData.originalIdea = String(d.idea || '').trim() || stageData.originalIdea;
            if (Array.isArray(d.papers)) stageData.papers = d.papers;
            if (typeof d.refined_idea === 'string') stageData.refined = d.refined_idea;
            stageData.refineThinking = '';
            _renderRefinePanel();
        });

        document.addEventListener('maars:idea-thinking', (e) => {
            const d = e?.detail || {};
            const chunk = String(d.chunk || '').trim();
            const toolName = String(d?.scheduleInfo?.tool_name || '').trim();
            const turn = d?.scheduleInfo?.turn;
            const maxTurns = d?.scheduleInfo?.max_turns;
            const parts = [];
            if (toolName) parts.push(`Running tool: **${toolName}**`);
            if (Number.isFinite(turn) && Number.isFinite(maxTurns)) parts.push(`Turn ${turn}/${maxTurns}`);
            if (chunk) parts.push(chunk);
            if (!parts.length) return;
            stageData.refineThinking = parts.join('\n\n');
            if (!String(stageData.refined || '').trim()) {
                _renderRefinePanel();
            }
        });
        document.addEventListener('maars:paper-complete', (e) => {
            const d = e?.detail || {};
            if (typeof d.content === 'string') stageData.paper = d.content;
            _renderPaperPanel();
        });

        document.addEventListener('maars:task-states-update', (e) => {
            const d = e?.detail || {};
            const tasks = Array.isArray(d.tasks) ? d.tasks : [];
            if (!tasks.length) return;
            tasks.forEach((t) => {
                if (!t?.task_id) return;
                const id = _ensureTaskInOrder(t.task_id);
                _upsertTaskMeta(t);
                if (!id) return;
                const nextStatus = String(t.status || '');
                const prevStatus = executeState.statuses.get(id) || '';
                executeState.statuses.set(id, nextStatus);
                if (nextStatus && nextStatus !== prevStatus) {
                    const meta = _getTaskMetaById(id) || {};
                    _appendExecuteMessage({
                        taskId: id,
                        kind: nextStatus === 'execution-failed' || nextStatus === 'validation-failed' ? 'error' : 'assistant',
                        title: meta.title || id,
                        body: meta.description || `${id} status changed.`,
                        status: nextStatus,
                        dedupeKey: `status:${id}:${nextStatus}`,
                    });
                }
            });
            if (activeStage === 'execute') {
                renderExecuteStream();
            }
        });

        document.addEventListener('maars:task-thinking', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            const chunk = String(d.chunk || '').trim();
            if (!taskId || !chunk) return;

            _ensureTaskInOrder(taskId);
            _upsertExecuteThinkingMessage(
                taskId,
                d.operation || 'Execute',
                chunk,
                d.scheduleInfo || null,
            );

            if (activeStage === 'execute') {
                renderExecuteStream();
            }
        });

        document.addEventListener('maars:task-output', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            if (!taskId) return;
            _ensureTaskInOrder(taskId);
            const outputText = _stringifyOutput(d.output);
            _pushRecentOutput(taskId, outputText);
            const meta = _getTaskMetaById(taskId) || {};
            _appendExecuteMessage({
                taskId,
                kind: 'output',
                title: meta.title || taskId,
                body: outputText,
                status: executeState.statuses.get(taskId) || meta.status || '',
            });
            if (activeStage === 'execute') {
                renderExecuteStream();
            }
        });

        document.addEventListener('maars:execution-sync', (e) => {
            const d = e?.detail || {};
            const tasks = Array.isArray(d.tasks) ? d.tasks : [];
            if (!tasks.length) return;
            tasks.forEach((task) => {
                _upsertTaskMeta(task);
                const id = _ensureTaskInOrder(task.task_id);
                if (!id) return;
                const nextStatus = String(task.status || '');
                if (nextStatus) executeState.statuses.set(id, nextStatus);
            });
            if (activeStage === 'execute') {
                renderExecuteStream();
            }
            refreshExecutionRuntimeStatus();
        });

        document.addEventListener('maars:task-complete', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            if (!taskId) return;
            const meta = _getTaskMetaById(taskId) || {};
            _appendExecuteMessage({
                taskId,
                kind: 'assistant',
                title: meta.title || taskId,
                body: 'Step completed.',
                status: 'done',
                dedupeKey: `complete:${taskId}`,
            });
            executeState.statuses.set(taskId, 'done');
            if (activeStage === 'execute') renderExecuteStream();
            refreshExecutionRuntimeStatus();
        });

        document.addEventListener('maars:task-error', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            const errorText = String(d.error || '').trim();
            if (!taskId && !errorText) return;
            const meta = _getTaskMetaById(taskId) || {};
            _appendExecuteMessage({
                taskId: taskId || '',
                kind: 'error',
                title: meta.title || taskId || 'Execution Error',
                body: errorText || 'Unknown execution error.',
                status: taskId ? (executeState.statuses.get(taskId) || 'execution-failed') : 'execution-failed',
            });
            if (taskId) executeState.statuses.set(taskId, 'execution-failed');
            if (activeStage === 'execute') renderExecuteStream();
            refreshExecutionRuntimeStatus();
        });

        document.addEventListener('maars:execution-runtime-status', (e) => {
            renderExecutionRuntimeStatus(e?.detail || {});
        });

        document.addEventListener('maars:execution-layout', (e) => {
            const d = e?.detail || {};
            const treeData = Array.isArray(d?.layout?.treeData) ? d.layout.treeData : [];
            const graphLayout = d?.layout?.layout || null;
            if (!treeData.length || !graphLayout) return;
            executionGraphPayload = { treeData, layout: graphLayout };
            treeData.forEach(_upsertTaskMeta);
            if (activeStage === 'execute') {
                window.MAARS?.taskTree?.renderExecutionTree?.(treeData, graphLayout);
                renderExecuteStream();
            }
        });
    }

    function init() {
        initStageNav();
        initTreeTabs();
        initExecuteSplitter();
        initEventBridges();

        // Create page (index.html / research.html)
        if (homeView && promptInput && createBtn) {
            createBtn.addEventListener('click', createResearchFromHome);
            // Prefer focusing the prompt on the dedicated research create page.
            try {
                if (/research\.html$/.test(window.location.pathname || '')) {
                    promptInput.focus();
                }
            } catch (_) {}
        }

        // Detail page (research_detail.html)
        if (researchView) {
            const rid = _getResearchIdFromUrl();
            if (rid) {
                initDetailControls(rid);
                // Default to Refine view on entry.
                setActiveStage('refine');
                renderExecutionRuntimeStatus({ enabled: true, available: true, connected: false });
                loadResearch(rid).catch((e) => {
                    console.error(e);
                    alert(e?.message || 'Failed to load research');
                    navigateToCreateResearch();
                });
            } else {
                // No id - send user to create page
                navigateToCreateResearch();
            }
        }
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.research = { init, navigateToResearch, navigateToCreateResearch };
})();
