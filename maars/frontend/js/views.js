/**
 * MAARS views - tree (decomposition/execution), output, execution stats.
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
        const execution = await api.loadExecution();
        if (!execution) {
            alert('Plan first.');
            return;
        }
        const planId = await cfg.resolvePlanId();
        const btn = executionBtn;
        const originalText = btn.textContent;
        startExecutionUI();
        try {
            const socket = window.MAARS?.state?.socket;
            if (!socket || !socket.connected) {
                window.MAARS.ws?.init();
                await new Promise(resolve => setTimeout(resolve, 500));
            }
            const response = await fetch(`${cfg.API_BASE_URL}/execution/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ planId })
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
        fetch(`${cfg.API_BASE_URL}/execution/stop`, { method: 'POST' }).catch(() => {});
    }

    function resetExecutionButtons() {
        if (executionBtn) { executionBtn.disabled = false; executionBtn.textContent = 'Execution'; }
        if (stopExecutionBtn) stopExecutionBtn.style.display = 'none';
    }

    async function generateExecutionLayout() {
        try {
            const planId = await cfg.resolvePlanId();
            const genRes = await fetch(`${cfg.API_BASE_URL}/execution/generate-from-plan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ planId })
            });
            const genData = await genRes.json();
            if (!genRes.ok) throw new Error(genData.error || 'Failed to generate execution from plan');
            const execution = genData.execution;
            if (!execution || !execution.tasks?.length) {
                alert('No atomic tasks. Plan first.');
                return;
            }
            const response = await fetch(`${cfg.API_BASE_URL}/plan/layout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ execution, planId })
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to generate layout');
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
            alert('Error: ' + error.message);
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

    function init() {
        if (executionBtn) executionBtn.addEventListener('click', runExecution);
        if (stopExecutionBtn) stopExecutionBtn.addEventListener('click', stopExecution);
    }

    window.MAARS.views = {
        init,
        state,
        setExecutionLayout,
        restoreExecution,
        animateConnectionLines,
        renderExecutionStats,
        resetExecutionButtons,
        generateExecutionLayout,
        startExecutionUI,
    };
})();
