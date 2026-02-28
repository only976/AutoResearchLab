/**
 * MAARS WebSocket - Socket.io connection and event handlers.
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    const plan = window.MAARS?.plan;
    const views = window.MAARS?.views;
    const thinking = window.MAARS?.thinking;
    const output = window.MAARS?.output;
    if (!cfg || !plan || !views) return;

    const state = window.MAARS.state || {};
    state.socket = null;
    window.MAARS.state = state;

    const executionBtn = document.getElementById('executionBtn');
    const stopExecutionBtn = document.getElementById('stopExecutionBtn');

    async function syncExecutionStateOnConnect() {
        const views = window.MAARS?.views;
        if (!views?.state?.executionLayout || !cfg?.resolvePlanId) return;
        try {
            const planId = await cfg.resolvePlanId();
            const res = await fetch(`${cfg.API_BASE_URL}/execution/status?planId=${encodeURIComponent(planId)}`);
            const data = await res.json();
            if (!data.tasks?.length) return;
            views.renderExecutionStats({ stats: data.stats });
            data.tasks.forEach(taskState => {
                const cacheNode = views.state.chainCache.find(node => node.task_id === taskState.task_id);
                if (cacheNode) cacheNode.status = taskState.status;
                views.state.previousTaskStates.set(taskState.task_id, taskState.status);
            });
            const areas = document.querySelectorAll('.plan-agent-tree-area, .plan-agent-execution-tree-area');
            data.tasks.forEach(taskState => {
                areas.forEach((treeArea) => {
                    if (!treeArea) return;
                    const byId = treeArea.querySelectorAll(`[data-task-id="${taskState.task_id}"]`);
                    const byIds = treeArea.querySelectorAll('[data-task-ids]');
                    const cells = Array.from(byId);
                    byIds.forEach(cell => {
                        const ids = (cell.getAttribute('data-task-ids') || '').split(',').map(s => s.trim());
                        if (ids.includes(taskState.task_id)) cells.push(cell);
                    });
                    cells.forEach(cell => {
                        cell.classList.remove('task-status-undone', 'task-status-doing', 'task-status-validating', 'task-status-done', 'task-status-validation-failed', 'task-status-execution-failed');
                        const dataAttr = cell.getAttribute('data-task-data');
                        if (dataAttr) {
                            try {
                                const d = JSON.parse(dataAttr);
                                const arr = Array.isArray(d) ? d : [d];
                                const updated = arr.map(t => t.task_id === taskState.task_id ? { ...t, status: taskState.status } : t);
                                cell.setAttribute('data-task-data', JSON.stringify(Array.isArray(d) ? updated : updated[0]));
                                const status = arr.length === 1 ? taskState.status : (window.MAARS?.taskTree?.aggregateStatus ? window.MAARS.taskTree.aggregateStatus(updated) : taskState.status);
                                if (status && status !== 'undone') cell.classList.add(`task-status-${status}`);
                            } catch (_) {
                                if (taskState.status && taskState.status !== 'undone') cell.classList.add(`task-status-${taskState.status}`);
                            }
                        } else {
                            if (taskState.status && taskState.status !== 'undone') cell.classList.add(`task-status-${taskState.status}`);
                        }
                        document.querySelectorAll(`.task-detail-tab[data-tab-task-id="${taskState.task_id}"]`).forEach(tab => {
                            tab.classList.remove('task-status-undone', 'task-status-doing', 'task-status-validating', 'task-status-done', 'task-status-validation-failed', 'task-status-execution-failed');
                            if (taskState.status && taskState.status !== 'undone') tab.classList.add(`task-status-${taskState.status}`);
                        });
                    });
                });
            });
            if (data.running) {
                if (executionBtn) { executionBtn.disabled = true; executionBtn.textContent = 'Executing...'; }
                if (stopExecutionBtn) stopExecutionBtn.style.display = '';
            }
        } catch (_) {
            /* ignore sync errors */
        }
    }

    function init() {
        if (state.socket && state.socket.connected) return;
        state.socket = io(cfg.WS_URL, { reconnection: true, reconnectionAttempts: 10, reconnectionDelay: 1000 });

        state.socket.on('connect', () => {
            console.log('WebSocket connected');
            syncExecutionStateOnConnect();
        });
        state.socket.on('disconnect', () => console.log('WebSocket disconnected'));

        const taskTree = window.MAARS?.taskTree;
        state.socket.on('plan-start', () => {
            if (thinking) thinking.clear();
            taskTree?.clearPlanAgentTree();
        });

        state.socket.on('plan-thinking', (data) => {
            if (!thinking) return;
            thinking.appendChunk(data.chunk || '', data.taskId, data.operation, data.scheduleInfo);
        });

        state.socket.on('plan-tree-update', (data) => {
            if (data.treeData) taskTree?.renderPlanAgentTree(data.treeData, data.layout);
        });

        state.socket.on('plan-complete', (data) => {
            if (data.treeData) taskTree?.renderPlanAgentTree(data.treeData, data.layout);
            if (data.planId) cfg.setCurrentPlanId(data.planId);
            taskTree?.updatePlanAgentQualityBadge(data.qualityScore, data.qualityComment);
            plan.resetPlanUI();
            if (thinking) thinking.applyHighlight();
            if (views?.generateExecutionLayout) views.generateExecutionLayout();
        });

        state.socket.on('plan-error', () => plan.resetPlanUI());

        state.socket.on('execution-layout', (data) => { views.setExecutionLayout(data); });

        state.socket.on('task-states-update', (data) => {
            if (data.tasks && Array.isArray(data.tasks)) {
                data.tasks.forEach(taskState => {
                    const cacheNode = views.state.chainCache.find(node => node.task_id === taskState.task_id);
                    const previousStatus = views.state.previousTaskStates.get(taskState.task_id);
                    if (cacheNode) cacheNode.status = taskState.status;
                    if (previousStatus !== undefined && previousStatus !== taskState.status) {
                        if (taskState.status === 'doing' && (previousStatus === 'undone' || previousStatus === 'validating')) {
                            setTimeout(() => views.animateConnectionLines(taskState.task_id, 'yellow', 'upstream'), 50);
                        } else if (taskState.status === 'undone' && previousStatus === 'done') {
                            setTimeout(() => views.animateConnectionLines(taskState.task_id, 'red', 'downstream'), 50);
                        }
                    }
                    views.state.previousTaskStates.set(taskState.task_id, taskState.status);
                });
                data.tasks.forEach(taskState => {
                    const areas = document.querySelectorAll('.plan-agent-tree-area, .plan-agent-execution-tree-area');
                    areas.forEach((treeArea) => {
                    if (treeArea) {
                        const byId = treeArea.querySelectorAll(`[data-task-id="${taskState.task_id}"]`);
                        const byIds = treeArea.querySelectorAll('[data-task-ids]');
                        const cells = Array.from(byId);
                        byIds.forEach(cell => {
                            const ids = (cell.getAttribute('data-task-ids') || '').split(',').map(s => s.trim());
                            if (ids.includes(taskState.task_id)) cells.push(cell);
                        });
                        cells.forEach(cell => {
                            cell.classList.remove('task-status-undone', 'task-status-doing', 'task-status-validating', 'task-status-done', 'task-status-validation-failed', 'task-status-execution-failed');
                            const dataAttr = cell.getAttribute('data-task-data');
                            if (dataAttr) {
                                try {
                                    const d = JSON.parse(dataAttr);
                                    const arr = Array.isArray(d) ? d : [d];
                                    const updated = arr.map(t => t.task_id === taskState.task_id ? { ...t, status: taskState.status } : t);
                                    cell.setAttribute('data-task-data', JSON.stringify(Array.isArray(d) ? updated : updated[0]));
                                    const status = arr.length === 1 ? taskState.status : (taskTree?.aggregateStatus ? taskTree.aggregateStatus(updated) : taskState.status);
                                    if (status && status !== 'undone') cell.classList.add(`task-status-${status}`);
                                } catch (_) {
                                    if (taskState.status && taskState.status !== 'undone') cell.classList.add(`task-status-${taskState.status}`);
                                }
                            } else {
                                if (taskState.status && taskState.status !== 'undone') cell.classList.add(`task-status-${taskState.status}`);
                            }
                            document.querySelectorAll(`.task-detail-tab[data-tab-task-id="${taskState.task_id}"]`).forEach(tab => {
                                tab.classList.remove('task-status-undone', 'task-status-doing', 'task-status-validating', 'task-status-done', 'task-status-validation-failed', 'task-status-execution-failed');
                                if (taskState.status && taskState.status !== 'undone') tab.classList.add(`task-status-${taskState.status}`);
                            });
                        });
                    }
                    });
                });
            }
        });

        state.socket.on('task-thinking', (data) => {
            if (!thinking) return;
            thinking.appendChunk(data.chunk || '', data.taskId, data.operation, data.scheduleInfo);
        });

        state.socket.on('task-output', (data) => {
            if (!output || !data.taskId) return;
            output.setTaskOutput(data.taskId, data.output);
        });

        state.socket.on('execution-stats-update', (data) => {
            views.renderExecutionStats(data);
        });

        state.socket.on('execution-error', (data) => {
            const isStoppedByUser = (data.error || '').includes('stopped by user');
            if (!isStoppedByUser) {
                console.error('Execution error:', data.error);
                alert('Execution error: ' + data.error);
            }
            views.resetExecutionButtons();
        });

        state.socket.on('execution-complete', (data) => {
            console.log(`Execution complete: ${data.completed}/${data.total} tasks completed`);
            if (thinking) thinking.applyHighlight();
            if (output) output.applyOutputHighlight();
            if (stopExecutionBtn) stopExecutionBtn.style.display = 'none';
            if (executionBtn) {
                executionBtn.disabled = false;
                executionBtn.textContent = 'Execution Complete!';
                setTimeout(() => { executionBtn.textContent = 'Execution'; }, 2000);
            }
        });
    }

    window.MAARS.ws = { init };
})();
