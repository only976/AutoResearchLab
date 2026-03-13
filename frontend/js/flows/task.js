/**
 * MAARS Task 流程 - run/stop execution、layout、stats。
 * 独立模块，不依赖 idea/plan。派发 maars:task-start / 监听 idea-start、plan-start 清空，plan-complete 更新按钮。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
    if (!cfg || !api) return;

    const executionBtn = document.getElementById('executionBtn');
    const stopExecutionBtn = document.getElementById('stopExecutionBtn');

    window.MAARS.state = window.MAARS.state || {};
    const state = window.MAARS.state;
    state.executionLayout = state.executionLayout ?? null;
    state.chainCache = state.chainCache ?? [];
    state.previousTaskStates = state.previousTaskStates ?? new Map();

    function clear() {
        state.executionLayout = null;
        state.chainCache = [];
        state.previousTaskStates.clear();
        window.MAARS.taskTree?.clearExecutionTree();
    }

    /** 仅更新 Execute 按钮状态：需同时有合法 ideaId 和 planId。 */
    async function updateButtonState() {
        const status = await api.fetchStatus?.() || { hasIdea: false, hasPlan: false };
        const executing = executionBtn?.textContent === 'Executing...';
        const canExecute = status.hasIdea && status.hasPlan;
        if (executionBtn) executionBtn.disabled = !canExecute || executing;
    }

    function buildChainCacheFromLayout(layout) {
        const cache = [];
        if (!layout) return cache;
        const treeData = layout.treeData || [];
        treeData.forEach(task => {
            if (task && task.task_id) {
                cache.push({ task_id: task.task_id, dependencies: task.dependencies || [], status: task.status || 'undone' });
            }
        });
        return cache;
    }

    function renderExecutionDiagram() {
        const layout = state.executionLayout;
        const treeData = layout?.treeData || [];
        window.MAARS.taskTree?.renderExecutionTree(treeData, layout?.layout);
    }

    function animateConnectionLines(taskId, color, direction) {
        const area = document.querySelector('.plan-agent-execution-tree-area');
        const svg = area?.querySelector('.tree-connection-lines');
        if (!svg) return;
        const paths = Array.from(svg.querySelectorAll('path.connection-line'));
        const lines = direction === 'upstream'
            ? paths.filter(p => {
                const to = p.getAttribute('data-to-task');
                const toTasks = p.getAttribute('data-to-tasks');
                if (to === taskId) return true;
                if (toTasks) return toTasks.split(',').map(s => s.trim()).includes(taskId);
                return false;
            })
            : paths.filter(p => {
                const from = p.getAttribute('data-from-task');
                const fromTasks = p.getAttribute('data-from-tasks');
                if (from === taskId) return true;
                if (fromTasks) return fromTasks.split(',').map(s => s.trim()).includes(taskId);
                return false;
            });
        if (lines.length === 0) return;
        const animClass = color === 'yellow' ? 'animate-yellow-glow' : 'animate-red-glow';
        lines.forEach(line => line.classList.remove('animate-yellow-glow', 'animate-red-glow'));
        void svg.offsetHeight;
        const order = color === 'yellow' ? lines : [...lines].reverse();
        order.forEach((line, i) => {
            setTimeout(() => {
                line.classList.add(animClass);
                setTimeout(() => line.classList.remove(animClass), 1000);
            }, i * 50);
        });
    }

    function renderExecutionStats(data) {
        if (!data?.stats) return;
        const stats = data.stats;
        const concurrent = (stats.busy ?? 0) + (stats.validating ?? 0);
        const max = stats.max ?? 7;
        const concurrentEl = document.getElementById('taskAgentConcurrent');
        const maxEl = document.getElementById('taskAgentMax');
        if (concurrentEl) concurrentEl.textContent = concurrent;
        if (maxEl) maxEl.textContent = max;
    }

    function startExecutionUI() {
        if (executionBtn) {
            executionBtn.disabled = true;
            executionBtn.textContent = 'Executing...';
        }
        if (stopExecutionBtn) stopExecutionBtn.style.display = '';
    }

    async function runExecution() {
        if (!executionBtn) return;
        const { ideaId, planId } = await cfg.resolvePlanIds();
        if (!ideaId || !planId) {
            alert('Current research has no valid plan yet. Please finish Refine/Plan first.');
            return;
        }
        const btn = executionBtn;
        const originalText = btn.textContent;
        document.dispatchEvent(new CustomEvent('maars:task-start'));
        document.dispatchEvent(new CustomEvent('maars:switch-view', { detail: { view: 'execution' } }));
        startExecutionUI();
        try {
            let stream = window.MAARS?.state?.es;
            if (!stream || stream.readyState !== 1) {
                stream = await window.MAARS.ws?.requireConnected?.();
                if (!stream || stream.readyState !== 1) {
                    resetExecutionButtons();
                    return;
                }
            }
            const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ideaId, planId })
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to start execution');
            }
            if (stopExecutionBtn) stopExecutionBtn.style.display = '';
        } catch (error) {
            console.error('Error in execution:', error);
            alert('Error: ' + error.message);
            btn.textContent = originalText;
            btn.disabled = false;
            if (stopExecutionBtn) stopExecutionBtn.style.display = 'none';
        }
    }

    function stopExecution() {
        resetExecutionButtons(); /* 立即恢复按钮，不等待后端 */
        api.stopAgent('task').catch(() => {});
    }

    function resetExecutionButtons() {
        if (executionBtn) { executionBtn.disabled = false; executionBtn.textContent = 'Execution'; }
        if (stopExecutionBtn) stopExecutionBtn.style.display = 'none';
    }

    async function generateExecutionLayout(explicitIds) {
        try {
            if (state.executionRunning) {
                console.warn('Skip layout update: execution is running');
                return;
            }
            const ids = explicitIds && explicitIds.ideaId && explicitIds.planId
                ? explicitIds
                : await cfg.resolvePlanIds();
            const ideaId = ids?.ideaId || '';
            const planId = ids?.planId || '';
            if (!ideaId || !planId) {
                console.warn('Skip execution layout generation: missing ideaId/planId', { ideaId, planId });
                return;
            }
            const genRes = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution/generate-from-plan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ideaId, planId })
            });
            const genData = await genRes.json();
            if (!genRes.ok) throw new Error(genData.error || 'Failed to generate execution from plan');
            const execData = genData.execution;
            if (!execData || !execData.tasks?.length) {
                alert('Current plan has no executable atomic tasks. Refine/Plan must finish successfully first.');
                return;
            }
            const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/plan/layout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ execution: execData, ideaId, planId })
            });
            if (!response.ok) {
                const error = await response.json();
                const msg = String(error.error || 'Failed to generate layout');
                // Benign race: backend disallows layout changes during execution.
                if (msg.includes('Cannot set layout while execution is running')) {
                    console.warn('Layout update blocked while running; ignoring.');
                    return;
                }
                throw new Error(msg);
            }
            const data = await response.json();
            state.executionLayout = data.layout;
            state.previousTaskStates.clear();
            state.chainCache = buildChainCacheFromLayout(state.executionLayout);
            renderExecutionDiagram();
            const socket = window.MAARS?.state?.socket;
            if (socket && socket.connected) socket.emit('execution-layout', { layout: state.executionLayout });
        } catch (error) {
            console.error('Error generating layout:', error);
            const msg = String(error?.message || error || '');
            if (msg.includes('Cannot set layout while execution is running')) {
                console.warn('Layout update blocked while running; ignoring.');
                return;
            }
            alert('Error: ' + msg);
        }
    }

    function setExecutionLayout(data) {
        if (!data?.layout) return;
        state.executionLayout = data.layout;
        state.chainCache = buildChainCacheFromLayout(data.layout);
        renderExecutionDiagram();
    }

    function restoreExecution(layout, execution) {
        state.executionLayout = layout;
        state.previousTaskStates.clear();
        (execution?.tasks || []).forEach((t) => {
            if (t.task_id && t.status) state.previousTaskStates.set(t.task_id, t.status);
        });
        state.chainCache = buildChainCacheFromLayout(layout);
        renderExecutionDiagram();
    }

    /** 应用任务状态到 chainCache、previousTaskStates，并触发连线动画 */
    function applyTaskStates(tasks) {
        if (!tasks || !Array.isArray(tasks)) return;
        tasks.forEach((taskState) => {
            const cacheNode = state.chainCache.find((node) => node.task_id === taskState.task_id);
            const previousStatus = state.previousTaskStates.get(taskState.task_id);
            if (cacheNode) cacheNode.status = taskState.status;
            if (previousStatus !== undefined && previousStatus !== taskState.status) {
                if (taskState.status === 'doing' && (previousStatus === 'undone' || previousStatus === 'validating')) {
                    setTimeout(() => animateConnectionLines(taskState.task_id, 'yellow', 'upstream'), 50);
                } else if (taskState.status === 'undone' && previousStatus === 'done') {
                    setTimeout(() => animateConnectionLines(taskState.task_id, 'red', 'downstream'), 50);
                }
            }
            state.previousTaskStates.set(taskState.task_id, taskState.status);
        });
    }

    /** 连接时同步执行状态（chainCache、stats、按钮） */
    function handleExecutionSync(data) {
        if (!data?.tasks?.length) return;
        renderExecutionStats({ stats: data.stats });
        data.tasks.forEach((taskState) => {
            const cacheNode = state.chainCache.find((node) => node.task_id === taskState.task_id);
            if (cacheNode) cacheNode.status = taskState.status;
            state.previousTaskStates.set(taskState.task_id, taskState.status);
        });
        if (data.running) {
            if (executionBtn) { executionBtn.disabled = true; executionBtn.textContent = 'Executing...'; }
            if (stopExecutionBtn) stopExecutionBtn.style.display = '';
        }
    }

    function onIdeaStart() {
        clear();
    }

    function onPlanStart() {
        clear();
    }

    function onPlanComplete() {
        updateButtonState();
    }

    function onExecutionComplete() {
        if (stopExecutionBtn) stopExecutionBtn.style.display = 'none';
        if (executionBtn) {
            executionBtn.disabled = false;
            executionBtn.textContent = 'Execution Complete!';
            setTimeout(() => { executionBtn.textContent = 'Execution'; }, 2000);
        }
    }

    function onRestoreComplete(e) {
        const { layout, execution } = e.detail || {};
        if (layout && execution?.tasks?.length) {
            restoreExecution(layout, execution);
            const socket = window.MAARS?.state?.socket;
            if (socket?.connected) socket.emit('execution-layout', { layout });
        }
        updateButtonState();
    }

    function onExecutionLayout(e) {
        const data = e?.detail;
        if (data?.layout) setExecutionLayout(data);
    }

    function onTaskStatesUpdate(e) {
        const data = e?.detail;
        if (data?.tasks && Array.isArray(data.tasks)) {
            applyTaskStates(data.tasks);
        }
    }

    function onTaskError(e) {
        const data = e?.detail || {};
        const isStoppedByUser = (data.error || '').includes('stopped by user');
        if (!isStoppedByUser) {
            console.error('Execution error:', data.error);
            alert('Execution error: ' + data.error);
        }
        resetExecutionButtons();
    }

    function onExecutionSync(e) {
        const data = e?.detail;
        if (!data?.tasks?.length) return;
        // Track running flag so we can avoid layout mutations mid-execution.
        state.executionRunning = !!data.running;
        handleExecutionSync(data);
    }

    function onPlanCompleteForLayout(e) {
        const data = e?.detail;
        if (!data) return;
        if (state.executionRunning) return;
        if (state.executionLayout) return;
        const ideaId = String(data.ideaId || '').trim();
        const planId = String(data.planId || '').trim();
        if (!ideaId || !planId) {
            console.warn('Skip plan-complete layout generation: missing plan identifiers', data);
            return;
        }
        if (generateExecutionLayout) generateExecutionLayout({ ideaId, planId });
    }

    function onTaskRetry(e) {
        const taskId = e?.detail?.taskId;
        if (!taskId || !api) return;
        api.retryTask(taskId).then(() => startExecutionUI()).catch((err) => {
            console.error('Retry failed:', err);
            alert('Failed: ' + (err.message || err));
        });
    }

    function onTaskResume(e) {
        const taskId = e?.detail?.taskId;
        if (!taskId || !api) return;
        api.resumeFromTask(taskId).then(() => startExecutionUI()).catch((err) => {
            console.error('Resume failed:', err);
            alert('Failed: ' + (err.message || err));
        });
    }

    function init() {
        if (executionBtn) executionBtn.addEventListener('click', runExecution);
        if (stopExecutionBtn) stopExecutionBtn.addEventListener('click', stopExecution);
        document.addEventListener('maars:idea-start', onIdeaStart);
        document.addEventListener('maars:plan-start', onPlanStart);
        document.addEventListener('maars:task-start', () => clear());
        document.addEventListener('maars:plan-complete', onPlanComplete);
        document.addEventListener('maars:plan-complete', onPlanCompleteForLayout);
        document.addEventListener('maars:task-complete', onExecutionComplete);
        document.addEventListener('maars:restore-complete', onRestoreComplete);
        document.addEventListener('maars:execution-layout', onExecutionLayout);
        document.addEventListener('maars:task-states-update', onTaskStatesUpdate);
        document.addEventListener('maars:task-error', onTaskError);
        document.addEventListener('maars:execution-sync', onExecutionSync);
        document.addEventListener('maars:task-retry', onTaskRetry);
        document.addEventListener('maars:task-resume', onTaskResume);
        executionBtn && (executionBtn.disabled = true);
        updateButtonState();
    }

    window.MAARS.task = {
        init,
        state,
        clear,
        setExecutionLayout,
        restoreExecution,
        animateConnectionLines,
        renderExecutionStats,
        resetExecutionButtons,
        generateExecutionLayout,
        startExecutionUI,
        updateButtonState,
        applyTaskStates,
        handleExecutionSync,
    };
})();
