/**
 * Task tree rendering module.
 * Uses pre-computed layout from backend (decomposition: level-order by task_id; execution: stage-based).
 */
(function () {
    'use strict';
    window.MAARS = window.MAARS || {};

    const AREA = {
        decomposition: '.plan-agent-tree-area',
        execution: '.plan-agent-execution-tree-area',
    };

    const escapeHtml = (window.MAARS?.utils?.escapeHtml) || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));

    let planAgentTreeData = [];
    let planAgentLayout = null;

    function getTreeContainer(areaSelector) {
        const area = document.querySelector(areaSelector);
        const tree = area?.querySelector('.tasks-tree');
        return area && tree ? { area, tree } : null;
    }

    function getTaskDataForPopover(task) {
        return {
            task_id: task.task_id,
            description: task.description,
            objective: task.objective,
            dependencies: task.dependencies,
            status: task.status,
            input: task.input,
            output: task.output,
            validation: task.validation,
            task_type: task.task_type,
            inputs: task.inputs,
            outputs: task.outputs,
            target: task.target,
            timeout_seconds: task.timeout_seconds,
        };
    }

    function createTaskNodeEl(task) {
        const tid = task.task_id;
        const desc = (task.description || task.objective || '').trim() || tid || 'Task';

        const el = document.createElement('div');
        el.className = 'tree-task';
        el.setAttribute('data-task-id', tid);
        el.setAttribute('data-task-data', JSON.stringify(getTaskDataForPopover(task)));
        el.setAttribute('title', desc);

        return el;
    }

    function aggregateStatus(tasks) {
        const hasError = tasks.some(t => t?.status === 'execution-failed' || t?.status === 'validation-failed');
        const allDone = tasks.length > 0 && tasks.every(t => t?.status === 'done');
        const allUndone = tasks.length > 0 && tasks.every(t => !t?.status || t?.status === 'undone');
        if (hasError) return 'execution-failed';
        if (allDone) return 'done';
        if (allUndone) return 'undone';
        return 'doing';
    }

    function createMergedTaskNodeEl(taskIds, taskById) {
        const tid = taskIds[0] || '?';
        const taskDatas = taskIds.map(id => getTaskDataForPopover(taskById.get(id) || { task_id: id }));
        const status = aggregateStatus(taskDatas);
        const desc = taskIds.join(', ');

        const el = document.createElement('div');
        el.className = 'tree-task tree-task-leaf tree-task-merged';
        if (status && status !== 'undone') el.classList.add('task-status-' + status);
        el.setAttribute('data-task-id', tid);
        el.setAttribute('data-task-ids', taskIds.join(','));
        el.setAttribute('data-task-data', JSON.stringify(taskDatas));
        el.setAttribute('title', desc);

        const badge = document.createElement('span');
        badge.className = 'tree-task-count';
        badge.textContent = String(taskIds.length);
        el.appendChild(badge);

        return el;
    }

    function buildSmoothPath(pts) {
        if (!pts || pts.length < 2) return '';
        const [x1, y1] = pts[0];
        const [x2, y2] = pts[1];
        const my = (y1 + y2) / 2;
        return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`;
    }

    function renderFull(treeData, layout, areaSelector) {
        const ctx = getTreeContainer(areaSelector);
        if (!ctx) return;

        const tasks = (treeData || []).filter(t => t?.task_id);

        if (areaSelector === AREA.decomposition) {
            planAgentTreeData = treeData || [];
            planAgentLayout = layout || null;
        }

        ctx.tree.innerHTML = '';

        if (tasks.length === 0 || !layout) return;

        const { nodes, edges, width, height } = layout;
        if (!nodes) return;

        ctx.tree.style.width = width + 'px';
        ctx.tree.style.height = height + 'px';
        ctx.tree.style.minHeight = height + 'px';

        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'tree-connection-lines');
        svg.setAttribute('width', width);
        svg.setAttribute('height', height);
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        ctx.tree.appendChild(svg);

        (edges || []).forEach(edge => {
            const pts = edge.points;
            if (!pts || pts.length < 2) return;
            const d = buildSmoothPath(pts);
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', d);
            path.setAttribute('stroke-width', '1.5');
            path.setAttribute('fill', 'none');
            const fromVal = edge.from;
            const toVal = edge.to;
            if (Array.isArray(fromVal)) {
                path.setAttribute('data-from-tasks', fromVal.join(','));
            } else {
                path.setAttribute('data-from-task', fromVal);
            }
            if (Array.isArray(toVal)) {
                path.setAttribute('data-to-tasks', toVal.join(','));
            } else {
                path.setAttribute('data-to-task', toVal);
            }
            path.setAttribute('class', 'connection-line' + (areaSelector === AREA.execution && edge.adjacent === false ? ' connection-line-cross-layer' : ''));
            svg.appendChild(path);
        });

        const nodesContainer = document.createElement('div');
        nodesContainer.className = 'tree-nodes-container';
        nodesContainer.style.cssText = `position:absolute;top:0;left:0;width:${width}px;height:${height}px;`;
        ctx.tree.appendChild(nodesContainer);

        const taskById = new Map(tasks.map(t => [t.task_id, t]));
        const parentIds = new Set();
        (edges || []).forEach(e => {
            const f = e.from;
            if (Array.isArray(f)) f.forEach(id => parentIds.add(id));
            else parentIds.add(f);
        });
        const leafIds = new Set(Object.keys(nodes).filter(id => !parentIds.has(id)));

        for (const [taskId, pos] of Object.entries(nodes)) {
            const ids = pos.ids;
            const isMerged = ids && ids.length >= 2;
            let el;
            if (isMerged && areaSelector === AREA.execution) {
                el = createMergedTaskNodeEl(ids, taskById);
            } else {
                const task = taskById.get(taskId);
                if (!task) continue;
                el = createTaskNodeEl(task);
                if (areaSelector === AREA.decomposition && leafIds.has(taskId)) {
                    el.classList.add('tree-task-leaf');
                }
                if (areaSelector === AREA.execution && task.status && task.status !== 'undone') {
                    el.classList.add('task-status-' + task.status);
                }
            }
            el.style.position = 'absolute';
            el.style.left = pos.x + 'px';
            el.style.top = pos.y + 'px';
            el.style.width = pos.w + 'px';
            el.style.height = pos.h + 'px';
            nodesContainer.appendChild(el);
        }
    }

    function clear(areaSelector) {
        if (areaSelector === AREA.decomposition) {
            planAgentTreeData = [];
            planAgentLayout = null;
        }
        const ctx = getTreeContainer(areaSelector);
        if (!ctx) return;
        ctx.tree.innerHTML = '';
        ctx.tree.style.width = '';
        ctx.tree.style.height = '';
        ctx.tree.style.minHeight = '';
    }

    function renderPlanAgentTree(treeData, layout) {
        if (!Array.isArray(treeData)) return;
        renderFull(treeData, layout, AREA.decomposition);
    }

    let popoverEl = null;
    let popoverAnchor = null;
    let popoverOutsideClickHandler = null;
    let popoverKeydownHandler = null;

    function buildTaskDetailBody(task) {
        const desc = (task.description || task.objective || '').trim() || '-';
        const deps = (task.dependencies || []).length > 0 ? (task.dependencies || []).join(', ') : 'None';
        const hasStatus = task.status != null;
        const isFailed = task.status === 'execution-failed' || task.status === 'validation-failed';
        const isUndone = !task.status || task.status === 'undone';
        const statusRow = hasStatus ? `<div class="task-detail-row"><span class="task-detail-label">Status:</span><span class="task-detail-value task-status-${task.status}">${escapeHtml(task.status)}</span></div>` : '';
        const actionRow = isFailed
            ? `<div class="task-detail-row task-detail-actions"><button type="button" class="btn-default task-retry-btn" data-retry-task-id="${escapeHtml(task.task_id)}">Retry</button></div>`
            : isUndone
                ? `<div class="task-detail-row task-detail-actions"><button type="button" class="btn-default task-resume-btn" data-resume-task-id="${escapeHtml(task.task_id)}">Run from here</button></div>`
                : '';
        const hasInputOutput = task.input && task.output;
        const inputRow = hasInputOutput ? `<div class="task-detail-row"><span class="task-detail-label">Input:</span><span class="task-detail-value">${escapeHtml(task.input.description || '-')}</span></div>` : '';
        const out = task.output || {};
        const outputDesc = hasInputOutput ? [out.artifact || out.description, out.format].filter(Boolean).join(' · ') || '-' : '-';
        const outputRow = hasInputOutput ? `<div class="task-detail-row"><span class="task-detail-label">Output:</span><span class="task-detail-value">${escapeHtml(outputDesc)}</span></div>` : '';
        const v = task.validation;
        const hasValidation = v && (v.description || (Array.isArray(v.criteria) && v.criteria.length > 0));
        const validationRow = hasValidation ? (() => {
            const vdesc = v.description ? `<div class="validation-desc">${escapeHtml(v.description)}</div>` : '';
            const criteriaList = (v.criteria || []).map(c => `<li>${escapeHtml(c)}</li>`).join('');
            const criteriaHtml = criteriaList ? `<ul class="validation-criteria">${criteriaList}</ul>` : '';
            const optionalList = (v.optionalChecks || []).map(c => `<li>${escapeHtml(c)}</li>`).join('');
            const optionalHtml = optionalList ? `<ul class="validation-optional">${optionalList}</ul>` : '';
            return `<div class="task-detail-row task-detail-validation"><span class="task-detail-label">Validation:</span><div class="task-detail-value">${vdesc}${criteriaHtml}${optionalHtml}</div></div>`;
        })() : '';
        return `<div class="task-detail-row"><span class="task-detail-label">Description:</span><span class="task-detail-value">${escapeHtml(desc)}</span></div>
                <div class="task-detail-row"><span class="task-detail-label">Dependencies:</span><span class="task-detail-value">${escapeHtml(deps)}</span></div>
                ${statusRow}
                ${inputRow}
                ${outputRow}
                ${validationRow}
                ${actionRow}`;
    }

    function showTaskPopover(taskOrTasks, anchorEl) {
        if (popoverEl && popoverAnchor === anchorEl) {
            hideTaskPopover();
            return;
        }
        hideTaskPopover();

        const tasks = Array.isArray(taskOrTasks) ? taskOrTasks : [taskOrTasks];
        const single = tasks.length === 1;

        popoverEl = document.createElement('div');
        popoverEl.className = 'task-detail-popover';
        popoverEl.setAttribute('role', 'dialog');
        popoverEl.setAttribute('aria-label', 'Task details');

        if (single) {
            const task = tasks[0];
            popoverEl.innerHTML = `
                <div class="task-detail-popover-header">
                    <span class="task-detail-popover-title">${escapeHtml(task.task_id)}</span>
                    <button class="task-detail-popover-close" aria-label="Close">&times;</button>
                </div>
                <div class="task-detail-popover-body">${buildTaskDetailBody(task)}</div>
            `;
        } else {
            const tabsHtml = tasks.map((t, i) => {
                const statusClass = (t.status && t.status !== 'undone') ? ` task-status-${t.status}` : '';
                return `<button type="button" class="task-detail-tab${statusClass}" data-tab-index="${i}" data-tab-task-id="${escapeHtml(t.task_id)}" aria-pressed="${i === 0}">${escapeHtml(t.task_id)}</button>`;
            }).join('');
            popoverEl.innerHTML = `
                <div class="task-detail-popover-header task-detail-popover-header-tabs">
                    <div class="task-detail-tabs">${tabsHtml}</div>
                    <button class="task-detail-popover-close" aria-label="Close">&times;</button>
                </div>
                <div class="task-detail-popover-body">${buildTaskDetailBody(tasks[0])}</div>
            `;
            const tabs = popoverEl.querySelectorAll('.task-detail-tab');
            const body = popoverEl.querySelector('.task-detail-popover-body');
            tabs.forEach((tab, i) => {
                tab.addEventListener('click', () => {
                    tabs.forEach(t => t.setAttribute('aria-pressed', 'false'));
                    tab.setAttribute('aria-pressed', 'true');
                    body.innerHTML = buildTaskDetailBody(tasks[i]);
                });
            });
        }

        document.body.appendChild(popoverEl);
        popoverAnchor = anchorEl;

        const rect = anchorEl.getBoundingClientRect();
        const gap = 8;
        let left = rect.right + gap;
        let top = rect.top + rect.height / 2 - popoverEl.offsetHeight / 2;
        if (left + popoverEl.offsetWidth > window.innerWidth - 12) left = rect.left - popoverEl.offsetWidth - gap;
        if (left < 12) left = 12;
        if (top < 12) top = 12;
        if (top + popoverEl.offsetHeight > window.innerHeight - 12) top = window.innerHeight - popoverEl.offsetHeight - 12;

        popoverEl.style.left = left + 'px';
        popoverEl.style.top = top + 'px';

        popoverEl.querySelector('.task-detail-popover-close').addEventListener('click', hideTaskPopover);
        popoverEl.addEventListener('click', (e) => {
            const retryBtn = e.target.closest('.task-retry-btn');
            const resumeBtn = e.target.closest('.task-resume-btn');
            const taskId = retryBtn?.getAttribute('data-retry-task-id') || resumeBtn?.getAttribute('data-resume-task-id');
            if (taskId && window.MAARS?.api) {
                const fn = retryBtn ? window.MAARS.api.retryTask : window.MAARS.api.resumeFromTask;
                if (fn) {
                    fn.call(window.MAARS.api, taskId).then(() => {
                        if (window.MAARS?.views?.startExecutionUI) {
                            window.MAARS.views.startExecutionUI();
                        }
                    }).catch((err) => {
                        console.error('Action failed:', err);
                        alert('Failed: ' + (err.message || err));
                    });
                    hideTaskPopover();
                }
            }
        });
        popoverOutsideClickHandler = (e) => {
            if (popoverEl && !popoverEl.contains(e.target) && !e.target.closest('.tree-task')) hideTaskPopover();
        };
        popoverKeydownHandler = (e) => { if (e.key === 'Escape') hideTaskPopover(); };
        document.addEventListener('click', popoverOutsideClickHandler);
        document.addEventListener('keydown', popoverKeydownHandler);
    }

    function hideTaskPopover() {
        if (popoverOutsideClickHandler) {
            document.removeEventListener('click', popoverOutsideClickHandler);
            popoverOutsideClickHandler = null;
        }
        if (popoverKeydownHandler) {
            document.removeEventListener('keydown', popoverKeydownHandler);
            popoverKeydownHandler = null;
        }
        if (popoverEl) {
            popoverEl.remove();
            popoverEl = null;
            popoverAnchor = null;
        }
    }

    function initClickHandlers() {
        document.addEventListener('click', (e) => {
            const node = e.target.closest('.tree-task');
            if (!node) return;
            const data = node.getAttribute('data-task-data');
            if (!data) return;
            try {
                showTaskPopover(JSON.parse(data), node);
                e.stopPropagation();
            } catch (_) {}
        });
    }

    function updatePlanAgentQualityBadge(score, comment) {
        const badge = document.getElementById('planAgentQualityBadge');
        if (!badge) return;
        if (score == null || score === undefined) {
            badge.style.display = 'none';
            return;
        }
        badge.textContent = `Quality: ${score}`;
        badge.title = comment || '';
        badge.style.display = '';
        badge.classList.remove('quality-high', 'quality-mid', 'quality-low');
        if (score >= 80) badge.classList.add('quality-high');
        else if (score >= 60) badge.classList.add('quality-mid');
        else badge.classList.add('quality-low');
    }

    window.MAARS.taskTree = {
        aggregateStatus,
        renderPlanAgentTree,
        renderExecutionTree: (data, layout) => renderFull(data, layout, AREA.execution),
        clearPlanAgentTree: () => { clear(AREA.decomposition); updatePlanAgentQualityBadge(null); },
        clearExecutionTree: () => clear(AREA.execution),
        initClickHandlers,
        updatePlanAgentQualityBadge,
    };
})();
