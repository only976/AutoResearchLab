/**
 * MAARS SSE override - replaces WebSocket usage with EventSource.
 */
(function () {
    'use strict';
    window.MAARS = window.MAARS || {};

    function ensureDelegatedLoadIdeaClick() {
        if (window.__maarsDelegatedLoadIdeaClickAttached) return;
        window.__maarsDelegatedLoadIdeaClickAttached = true;

        document.addEventListener('click', async (event) => {
            try {
                const target = event.target;
                const btn = target && target.closest ? target.closest('#loadExampleIdeaBtn') : null;
                if (!btn) return;
                event.preventDefault();
                event.stopPropagation();
                await loadIdeaFromSnapshots();
            } catch (_) {
                // best-effort
            }
        }, true);
    }

    function logClient(message) {
        try {
            const payload = String(message || '').slice(0, 2000);
            if (navigator.sendBeacon) {
                const blob = new Blob([payload], { type: 'text/plain' });
                navigator.sendBeacon('/api/client-log', blob);
                return;
            }
            fetch('/api/client-log', { method: 'POST', body: payload }).catch(() => {});
        } catch (_) {}
    }

    async function loadIdeaFromSnapshots() {
        logClient('[maars] Load Idea clicked');
        const input = document.getElementById('ideaInput');
        if (!input) return;
        try {
            logClient('[maars] Fetching snapshots list');
            const listRes = await fetch('/api/ideas/snapshots');
            const listData = await listRes.json();
            const files = listData.files || [];
            logClient('[maars] Snapshots list ' + JSON.stringify(files));
            if (!files.length) return;
            const latest = files[0].filename || files[0].name || files[0];
            logClient('[maars] Loading snapshot ' + latest);
            const snapRes = await fetch(`/api/ideas/snapshots/${encodeURIComponent(latest)}`);
            const snap = await snapRes.json();
            logClient('[maars] Snapshot payload keys ' + Object.keys(snap || {}).join(','));

            let ideaText = '';
            const refinement = snap.refinement_data;
            if (refinement) {
                if (typeof refinement === 'string') ideaText = refinement;
                else ideaText = refinement.title || refinement.topic || refinement.scope || '';
            }

            if (!ideaText && Array.isArray(snap.results) && snap.results.length) {
                const first = snap.results[0] || {};
                const topic = first.topic || {};
                ideaText = topic.title || topic.topic || topic.scope || '';
                if (!ideaText && Array.isArray(first.ideas) && first.ideas.length) {
                    const idea = first.ideas[0] || {};
                    ideaText = idea.title || idea.idea || idea.summary || idea.description || '';
                }
            }

            if (!ideaText) {
                ideaText = JSON.stringify(snap, null, 2).slice(0, 500);
            }

            input.value = String(ideaText).trim();
        } catch (err) {
            logClient('[maars] Load idea snapshot failed ' + (err && err.message ? err.message : String(err)));
        }
    }

    function attachLoadIdeaOverride() {
        const api = window.MAARS?.api;
        if (!api) return false;
        api.loadExampleIdea = loadIdeaFromSnapshots;
        return true;
    }

    function init() {
        const cfg = window.MAARS?.config;
        const plan = window.MAARS?.plan;
        const views = window.MAARS?.views;
        const thinking = window.MAARS?.thinking;
        const output = window.MAARS?.output;
        if (!cfg || !plan || !views) return;

        ensureDelegatedLoadIdeaClick();

        document.addEventListener('click', (event) => {
            const target = event.target;
            const el = target && target.closest ? target.closest('button,a') : null;
            if (!el) return;
            const label = (el.textContent || '').trim().slice(0, 120);
            const id = el.id ? `#${el.id}` : '';
            const cls = el.className ? `.${String(el.className).split(' ').filter(Boolean).join('.')}` : '';
            const href = el.getAttribute ? el.getAttribute('href') : '';
            logClient(`[maars] Click ${el.tagName}${id}${cls} ${label} ${href || ''}`.trim());
        }, true);

        if (!attachLoadIdeaOverride()) {
            const maxWait = 20;
            let attempts = 0;
            const timer = setInterval(() => {
                attempts += 1;
                if (attachLoadIdeaOverride() || attempts >= maxWait) {
                    clearInterval(timer);
                }
            }, 200);
        }

        const state = window.MAARS.state || {};
        if (state.sse) return;

        state.socket = { connected: true, emit: function () {} };
        window.MAARS.state = state;

        const eventsUrl = (cfg.API_BASE_URL || '/api/maars') + '/events';
        const es = new EventSource(eventsUrl);
        state.sse = es;

        es.addEventListener('plan-start', () => {
            if (thinking) thinking.clear();
            window.MAARS.taskTree?.clearPlanAgentTree();
        });

        es.addEventListener('plan-thinking', (evt) => {
            if (!thinking) return;
            try {
                const data = JSON.parse(evt.data || '{}');
                thinking.appendChunk(data.chunk || '', data.taskId, data.operation, data.scheduleInfo);
            } catch (_) {}
        });

        es.addEventListener('plan-tree-update', (evt) => {
            try {
                const data = JSON.parse(evt.data || '{}');
                if (data.treeData) window.MAARS.taskTree?.renderPlanAgentTree(data.treeData, data.layout);
            } catch (_) {}
        });

        es.addEventListener('plan-complete', (evt) => {
            try {
                const data = JSON.parse(evt.data || '{}');
                if (data.treeData) window.MAARS.taskTree?.renderPlanAgentTree(data.treeData, data.layout);
                if (data.planId) cfg.setCurrentPlanId(data.planId);
                window.MAARS.taskTree?.updatePlanAgentQualityBadge(data.qualityScore, data.qualityComment);
                plan.resetPlanUI();
                if (thinking) thinking.applyHighlight();
                if (views?.generateExecutionLayout) views.generateExecutionLayout();
            } catch (_) {
                plan.resetPlanUI();
            }
        });

        es.addEventListener('plan-error', () => {
            plan.resetPlanUI();
        });

        es.addEventListener('execution-layout', (evt) => {
            try {
                const data = JSON.parse(evt.data || '{}');
                views.setExecutionLayout(data);
            } catch (_) {}
        });

        es.addEventListener('task-states-update', (evt) => {
            try {
                const data = JSON.parse(evt.data || '{}');
                if (!data.tasks || !Array.isArray(data.tasks)) return;
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
            } catch (_) {}
        });

        es.addEventListener('task-thinking', (evt) => {
            if (!thinking) return;
            try {
                const data = JSON.parse(evt.data || '{}');
                thinking.appendChunk(data.chunk || '', data.taskId, data.operation, data.scheduleInfo);
            } catch (_) {}
        });

        es.addEventListener('task-output', (evt) => {
            if (!output) return;
            try {
                const data = JSON.parse(evt.data || '{}');
                if (data.taskId) output.setTaskOutput(data.taskId, data.output);
            } catch (_) {}
        });

        es.addEventListener('execution-stats-update', (evt) => {
            try {
                const data = JSON.parse(evt.data || '{}');
                views.renderExecutionStats(data);
            } catch (_) {}
        });

        es.addEventListener('execution-error', (evt) => {
            try {
                const data = JSON.parse(evt.data || '{}');
                const isStoppedByUser = (data.error || '').includes('stopped by user');
                if (!isStoppedByUser) {
                    console.error('Execution error:', data.error);
                    alert('Execution error: ' + data.error);
                }
            } catch (_) {}
            views.resetExecutionButtons();
        });

        es.addEventListener('execution-complete', (evt) => {
            try {
                const data = JSON.parse(evt.data || '{}');
                console.log(`Execution complete: ${data.completed}/${data.total} tasks completed`);
            } catch (_) {}
            if (thinking) thinking.applyHighlight();
            if (output) output.applyOutputHighlight?.();
            const stopExecutionBtn = document.getElementById('stopExecutionBtn');
            const executionBtn = document.getElementById('executionBtn');
            if (stopExecutionBtn) stopExecutionBtn.style.display = 'none';
            if (executionBtn) {
                executionBtn.disabled = false;
                executionBtn.textContent = 'Execution Complete!';
                setTimeout(() => { executionBtn.textContent = 'Execution'; }, 2000);
            }
        });

        es.addEventListener('error', () => {
            // Let the browser retry; UI should remain usable.
        });
    }

    window.MAARS.ws = { init };

    // In this Next.js integration, scripts are injected after DOMContentLoaded,
    // so the original app init may not run. Make sure the Load Idea button works
    // even if MAARS init doesn't execute.
    ensureDelegatedLoadIdeaClick();

    // Best-effort: bind/override API when it becomes available.
    if (!attachLoadIdeaOverride()) {
        const maxWait = 50;
        let attempts = 0;
        const timer = setInterval(() => {
            attempts += 1;
            if (attachLoadIdeaOverride() || attempts >= maxWait) clearInterval(timer);
        }, 200);
    }
})();
