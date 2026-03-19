/**
 * MAARS Task execution-state helpers.
 * Contains pure-ish state transition and visualization utilities.
 */
(function () {
    'use strict';

    function createTaskExecutionStateHelpers(state) {
        function buildChainCacheFromLayout(layout) {
            const cache = [];
            if (!layout) return cache;
            const treeData = layout.treeData || [];
            treeData.forEach((task) => {
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
                ? paths.filter((path) => {
                    const to = path.getAttribute('data-to-task');
                    const toTasks = path.getAttribute('data-to-tasks');
                    if (to === taskId) return true;
                    if (toTasks) return toTasks.split(',').map((s) => s.trim()).includes(taskId);
                    return false;
                })
                : paths.filter((path) => {
                    const from = path.getAttribute('data-from-task');
                    const fromTasks = path.getAttribute('data-from-tasks');
                    if (from === taskId) return true;
                    if (fromTasks) return fromTasks.split(',').map((s) => s.trim()).includes(taskId);
                    return false;
                });
            if (!lines.length) return;

            const animClass = color === 'yellow' ? 'animate-yellow-glow' : 'animate-red-glow';
            lines.forEach((line) => line.classList.remove('animate-yellow-glow', 'animate-red-glow'));
            void svg.offsetHeight;
            const ordered = color === 'yellow' ? lines : [...lines].reverse();
            ordered.forEach((line, index) => {
                setTimeout(() => {
                    line.classList.add(animClass);
                    setTimeout(() => line.classList.remove(animClass), 1000);
                }, index * 50);
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

        function applyTaskStates(tasks) {
            if (!Array.isArray(tasks)) return;
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

        function handleExecutionSync(data, executionBtn, stopExecutionBtn) {
            if (!data?.tasks?.length) return;
            renderExecutionStats({ stats: data.stats });
            data.tasks.forEach((taskState) => {
                const cacheNode = state.chainCache.find((node) => node.task_id === taskState.task_id);
                if (cacheNode) cacheNode.status = taskState.status;
                state.previousTaskStates.set(taskState.task_id, taskState.status);
            });
            if (data.running) {
                if (executionBtn) {
                    executionBtn.disabled = true;
                    executionBtn.textContent = 'Executing...';
                }
                if (stopExecutionBtn) stopExecutionBtn.hidden = false;
            }
        }

        return {
            buildChainCacheFromLayout,
            renderExecutionDiagram,
            animateConnectionLines,
            renderExecutionStats,
            applyTaskStates,
            handleExecutionSync,
        };
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.createTaskExecutionStateHelpers = createTaskExecutionStateHelpers;
})();
