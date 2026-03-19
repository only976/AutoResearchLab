/**
 * MAARS Task 流程 - run/stop execution、layout、stats。
 * 独立模块，不依赖 idea/plan。派发 maars:task-start / 监听 idea-start、plan-start 清空，plan-complete 更新按钮。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
    if (!cfg || !api) return;
    const toast = window.MAARS.toast;

    const executionBtn = document.getElementById('executionBtn');
    const stopExecutionBtn = document.getElementById('stopExecutionBtn');

    window.MAARS.state = window.MAARS.state || {};
    const state = window.MAARS.state;
    state.executionLayout = state.executionLayout ?? null;
    state.chainCache = state.chainCache ?? [];
    state.previousTaskStates = state.previousTaskStates ?? new Map();
    const executionStateHelpers = window.MAARS?.createTaskExecutionStateHelpers?.(state) || {};
    const runControlHelpers = window.MAARS?.createTaskRunControlHelpers?.({
        cfg,
        api,
        state,
        executionBtn,
        stopExecutionBtn,
        clear,
    }) || {};

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
        if (typeof executionStateHelpers.buildChainCacheFromLayout === 'function') {
            return executionStateHelpers.buildChainCacheFromLayout(layout);
        }
        return [];
    }

    function renderExecutionDiagram() {
        executionStateHelpers.renderExecutionDiagram?.();
    }

    function animateConnectionLines(taskId, color, direction) {
        executionStateHelpers.animateConnectionLines?.(taskId, color, direction);
    }

    function renderExecutionStats(data) {
        executionStateHelpers.renderExecutionStats?.(data);
    }

    function startExecutionUI() {
        runControlHelpers.startExecutionUI?.();
    }

    async function runExecution() {
        await runControlHelpers.runExecution?.();
    }

    function stopExecution() {
        runControlHelpers.stopExecution?.();
    }

    function resetExecutionButtons() {
        runControlHelpers.resetExecutionButtons?.();
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
                toast.warning('Current plan has no executable atomic tasks. Refine/Plan must finish successfully first.');
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
            toast.error('Error: ' + msg);
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

    function applyTaskStates(tasks) {
        executionStateHelpers.applyTaskStates?.(tasks);
    }

    function handleExecutionSync(data) {
        executionStateHelpers.handleExecutionSync?.(data, executionBtn, stopExecutionBtn);
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
        if (stopExecutionBtn) stopExecutionBtn.hidden = true;
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
        runControlHelpers.onTaskError?.(e);
    }

    function onExecutionSync(e) {
        const data = e?.detail;
        if (!data?.tasks?.length) return;
        runControlHelpers.onExecutionSyncRunning?.(data);
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
        runControlHelpers.onTaskRetry?.(e);
    }

    function onTaskResume(e) {
        runControlHelpers.onTaskResume?.(e);
    }

    function init() {
        if (executionBtn) executionBtn.addEventListener('click', runExecution);
        if (stopExecutionBtn) stopExecutionBtn.addEventListener('click', stopExecution);
        document.addEventListener('maars:idea-start', onIdeaStart);
        document.addEventListener('maars:plan-start', onPlanStart);
        document.addEventListener('maars:task-start', () => runControlHelpers.onExecutionStartClear?.());
        document.addEventListener('maars:plan-complete', onPlanComplete);
        document.addEventListener('maars:plan-complete', onPlanCompleteForLayout);
        document.addEventListener('maars:task-complete', onExecutionComplete);
        document.addEventListener('maars:restore-complete', onRestoreComplete);
        document.addEventListener('maars:execution-layout', onExecutionLayout);
        document.addEventListener('maars:task-states-update', onTaskStatesUpdate);
        document.addEventListener('maars:task-error', onTaskError);
        document.addEventListener('maars:execution-sync', onExecutionSync);
        document.addEventListener('maars:attempt-retry-request', onTaskRetry);
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
