/**
 * MAARS Tree View - 任务树渲染（Decomposition / Execution 两视图）。
 * 与 region-responsibilities 中 Tree View 对应。
 */
(function () {
    'use strict';
    window.MAARS = window.MAARS || {};

    const AREA = {
        decomposition: '.plan-agent-tree-area',
        execution: '.plan-agent-execution-tree-area',
    };

    const escapeHtml = (window.MAARS?.utils?.escapeHtml) || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));

    function deriveDisplayTitle(task) {
        const explicit = String(task?.title || '').replace(/\s+/g, ' ').trim();
        const raw = explicit || String(task?.description || task?.objective || '').replace(/\s+/g, ' ').trim();
        if (!raw) return String(task?.task_id || 'Task');
        const first = raw.split(/[\n\.;:!?]/, 1)[0].trim() || raw;

        // Chinese text: short phrase (~12 chars)
        if (/[\u4e00-\u9fff]/.test(first)) {
            if (first.length <= 12) return first;
            return first.slice(0, 12).replace(/[，。；：、\s]+$/g, '') + '…';
        }

        // Space-separated text: ~8 words
        const words = first.split(/\s+/).filter(Boolean);
        if (words.length > 8) return words.slice(0, 8).join(' ') + '…';
        if (first.length <= 48) return first;
        return first.slice(0, 47).trimEnd() + '…';
    }

    let planAgentTreeData = [];
    let planAgentLayout = null;
    let treeZoomLevel = 1.0;  // User-controlled zoom factor

    // Load saved zoom level from sessionStorage
    function loadZoomLevel() {
        const saved = sessionStorage.getItem('maars-tree-zoom-level');
        if (saved) {
            treeZoomLevel = parseFloat(saved) || 1.0;
        }
    }

    function saveZoomLevel() {
        sessionStorage.setItem('maars-tree-zoom-level', String(treeZoomLevel));
    }

    function calculateAdaptiveScale(treeData, baseLayout, areaSelector) {
        if (!baseLayout) return treeZoomLevel;

        const ctx = getTreeContainer(areaSelector);
        if (!ctx) return treeZoomLevel;

        const containerWidth = ctx.area.clientWidth || 800;
        const containerHeight = ctx.area.clientHeight || 600;

        // Base layout dimensions (from backend, unscaled)
        const baseWidth = baseLayout.width || 500;
        const baseHeight = baseLayout.height || 400;

        // Calculate scale to fit within container with some padding
        const scaleByWidth = (containerWidth - 40) / baseWidth;
        const scaleByHeight = (containerHeight - 40) / baseHeight;
        const fitScale = Math.min(scaleByWidth, scaleByHeight, 2.0);  // Cap at 2.0x

        // Title-based scaling: ensure nodes are wide enough for titles
        // Estimate: each character needs ~7px for English, ~8px for Chinese
        // Node base width is 180px in backend constants
        let titleScale = 1.0;
        if (treeData && Array.isArray(treeData)) {
            treeData.forEach((task) => {
                const title = deriveDisplayTitle(task) || '';
                const isChinese = /[\u4e00-\u9fff]/.test(title);
                const charWidth = isChinese ? 8 : 7;
                const requiredWidth = Math.min(title.length * charWidth + 20, 350);  // Cap at 350px
                if (requiredWidth > 180) {
                    titleScale = Math.max(titleScale, requiredWidth / 180);
                }
            });
        }

        // Combine: use the larger of fit-to-viewport or title-based scale
        const baseScale = Math.max(fitScale, titleScale);
        return baseScale * treeZoomLevel;
    }

    function scaleLayout(layout, factor) {
        if (!layout || !factor || factor === 1) return layout;
        const nodes = layout.nodes || {};
        const edges = Array.isArray(layout.edges) ? layout.edges : [];

        const scaledNodes = {};
        Object.entries(nodes).forEach(([id, n]) => {
            scaledNodes[id] = {
                ...n,
                x: Number((n.x * factor).toFixed(1)),
                y: Number((n.y * factor).toFixed(1)),
                w: Number((n.w * factor).toFixed(1)),
                h: Number((n.h * factor).toFixed(1)),
            };
        });

        const scaledEdges = edges.map((e) => ({
            ...e,
            points: (e.points || []).map((pt) => [
                Number(((pt?.[0] || 0) * factor).toFixed(1)),
                Number(((pt?.[1] || 0) * factor).toFixed(1)),
            ]),
        }));

        return {
            ...layout,
            nodes: scaledNodes,
            edges: scaledEdges,
            width: Number(((layout.width || 0) * factor).toFixed(1)),
            height: Number(((layout.height || 0) * factor).toFixed(1)),
        };
    }

    function getTreeContainer(areaSelector) {
        const area = document.querySelector(areaSelector);
        const tree = area?.querySelector('.tasks-tree');
        return area && tree ? { area, tree } : null;
    }

    function getTaskDataForPopover(task) {
        return {
            task_id: task.task_id,
            title: task.title,
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
        const title = deriveDisplayTitle(task);

        const el = document.createElement('div');
        el.className = 'tree-task';
        el.setAttribute('data-task-id', tid);
        el.setAttribute('data-task-data', JSON.stringify(getTaskDataForPopover(task)));
        el.setAttribute('title', desc);

        const label = document.createElement('span');
        label.className = 'tree-task-label';
        label.textContent = title;
        el.appendChild(label);

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

        const adaptiveScale = calculateAdaptiveScale(treeData, layout, areaSelector);
        const scaledLayout = scaleLayout(layout, adaptiveScale);
        const { nodes, edges, width, height } = scaledLayout;
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

    function initZoomControls(areaSelector) {
        // Create zoom controls if they don't exist
        const ctx = getTreeContainer(areaSelector);
        if (!ctx || ctx.area.querySelector('.tree-zoom-controls')) return;  // Already exists

        const controlsDiv = document.createElement('div');
        controlsDiv.className = 'tree-zoom-controls';
        controlsDiv.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px;
            background: rgba(255,255,255,0.9);
            border-radius: 4px;
            font-size: 12px;
            position: absolute;
            top: 8px;
            right: 8px;
            z-index: 100;
        `;

        const minusBtn = document.createElement('button');
        minusBtn.className = 'tree-zoom-button';
        minusBtn.textContent = '−';
        minusBtn.style.cssText = `padding: 4px 8px; cursor: pointer; border: 1px solid #ccc; background: #f5f5f5; border-radius: 3px;`;
        minusBtn.onclick = () => changeZoomLevel(-0.1, areaSelector);

        const zoomLabel = document.createElement('span');
        zoomLabel.className = 'tree-zoom-label';
        zoomLabel.textContent = `100%`;
        zoomLabel.style.cssText = `width: 35px; text-align: center;`;

        const plusBtn = document.createElement('button');
        plusBtn.className = 'tree-zoom-button';
        plusBtn.textContent = '+';
        plusBtn.style.cssText = `padding: 4px 8px; cursor: pointer; border: 1px solid #ccc; background: #f5f5f5; border-radius: 3px;`;
        plusBtn.onclick = () => changeZoomLevel(0.1, areaSelector);

        const resetBtn = document.createElement('button');
        resetBtn.className = 'tree-zoom-reset';
        resetBtn.textContent = 'Reset';
        resetBtn.style.cssText = `padding: 4px 8px; cursor: pointer; border: 1px solid #ccc; background: #f5f5f5; border-radius: 3px; font-size: 11px;`;
        resetBtn.onclick = () => resetZoomLevel(areaSelector);

        controlsDiv.appendChild(minusBtn);
        controlsDiv.appendChild(zoomLabel);
        controlsDiv.appendChild(plusBtn);
        controlsDiv.appendChild(resetBtn);

        ctx.area.style.position = 'relative';
        ctx.area.appendChild(controlsDiv);
    }

    function changeZoomLevel(delta, areaSelector) {
        treeZoomLevel = Math.max(0.5, Math.min(2.0, treeZoomLevel + delta));
        saveZoomLevel();
        updateZoomDisplay(areaSelector);
        
        // Re-render the tree with new zoom level
        if (areaSelector === AREA.decomposition) {
            renderFull(planAgentTreeData, planAgentLayout, areaSelector);
        }
    }

    function resetZoomLevel(areaSelector) {
        treeZoomLevel = 1.0;
        saveZoomLevel();
        updateZoomDisplay(areaSelector);
        
        // Re-render the tree with new zoom level
        if (areaSelector === AREA.decomposition) {
            renderFull(planAgentTreeData, planAgentLayout, areaSelector);
        }
    }

    function updateZoomDisplay(areaSelector) {
        const ctx = getTreeContainer(areaSelector);
        if (!ctx) return;
        const label = ctx.area.querySelector('.tree-zoom-label');
        if (label) {
            label.textContent = `${Math.round(treeZoomLevel * 100)}%`;
        }
    }

    function renderPlanAgentTree(treeData, layout) {
        if (!Array.isArray(treeData)) return;
        loadZoomLevel();  // Load saved zoom before rendering
        renderFull(treeData, layout, AREA.decomposition);
        initZoomControls(AREA.decomposition);
        updateZoomDisplay(AREA.decomposition);
    }

    let popoverEl = null;
    let popoverAnchor = null;
    let popoverOutsideClickHandler = null;
    let popoverKeydownHandler = null;

    function buildTaskDetailBody(task) {
        const title = deriveDisplayTitle(task);
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
        return `<div class="task-detail-row"><span class="task-detail-label">Title:</span><span class="task-detail-value">${escapeHtml(title)}</span></div>
            <div class="task-detail-row"><span class="task-detail-label">Description:</span><span class="task-detail-value">${escapeHtml(desc)}</span></div>
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
            if (taskId) {
                document.dispatchEvent(new CustomEvent(retryBtn ? 'maars:task-retry' : 'maars:task-resume', { detail: { taskId } }));
                hideTaskPopover();
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

    /**
     * 批量更新任务状态（DOM），供 websocket task-states-update / sync 调用。
     * @param {Array<{task_id: string, status: string}>} tasks
     */
    function updateTaskStates(tasks) {
        if (!tasks || !Array.isArray(tasks)) return;
        const areas = document.querySelectorAll('.plan-agent-tree-area, .plan-agent-execution-tree-area');
        tasks.forEach((taskState) => {
            areas.forEach((treeArea) => {
                if (!treeArea) return;
                const byId = treeArea.querySelectorAll(`[data-task-id="${taskState.task_id}"]`);
                const byIds = treeArea.querySelectorAll('[data-task-ids]');
                const cells = Array.from(byId);
                byIds.forEach((cell) => {
                    const ids = (cell.getAttribute('data-task-ids') || '').split(',').map((s) => s.trim());
                    if (ids.includes(taskState.task_id)) cells.push(cell);
                });
                cells.forEach((cell) => {
                    cell.classList.remove('task-status-undone', 'task-status-doing', 'task-status-validating', 'task-status-done', 'task-status-validation-failed', 'task-status-execution-failed');
                    const dataAttr = cell.getAttribute('data-task-data');
                    if (dataAttr) {
                        try {
                            const d = JSON.parse(dataAttr);
                            const arr = Array.isArray(d) ? d : [d];
                            const updated = arr.map((t) => (t.task_id === taskState.task_id ? { ...t, status: taskState.status } : t));
                            cell.setAttribute('data-task-data', JSON.stringify(Array.isArray(d) ? updated : updated[0]));
                            const status = arr.length === 1 ? taskState.status : aggregateStatus(updated);
                            if (status && status !== 'undone') cell.classList.add(`task-status-${status}`);
                        } catch (_) {
                            if (taskState.status && taskState.status !== 'undone') cell.classList.add(`task-status-${taskState.status}`);
                        }
                    } else {
                        if (taskState.status && taskState.status !== 'undone') cell.classList.add(`task-status-${taskState.status}`);
                    }
                    document.querySelectorAll(`.task-detail-tab[data-tab-task-id="${taskState.task_id}"]`).forEach((tab) => {
                        tab.classList.remove('task-status-undone', 'task-status-doing', 'task-status-validating', 'task-status-done', 'task-status-validation-failed', 'task-status-execution-failed');
                        if (taskState.status && taskState.status !== 'undone') tab.classList.add(`task-status-${taskState.status}`);
                    });
                });
            });
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

    (function initFlowStartListeners() {
        const onFlowStart = () => { clear(AREA.decomposition); updatePlanAgentQualityBadge(null); };
        document.addEventListener('maars:idea-start', onFlowStart);
        document.addEventListener('maars:plan-start', onFlowStart);
    })();

    document.addEventListener('maars:plan-tree-update', (e) => {
        const { treeData, layout } = e.detail || {};
        if (treeData) renderPlanAgentTree(treeData, layout);
    });

    document.addEventListener('maars:plan-complete', (e) => {
        const data = e.detail || {};
        if (data.treeData) renderPlanAgentTree(data.treeData, data.layout);
        updatePlanAgentQualityBadge(data.qualityScore, data.qualityComment);
    });

    document.addEventListener('maars:task-states-update', (e) => {
        const data = e.detail;
        if (data?.tasks && Array.isArray(data.tasks)) updateTaskStates(data.tasks);
    });

    document.addEventListener('maars:execution-sync', (e) => {
        const data = e.detail;
        if (data?.tasks && Array.isArray(data.tasks)) updateTaskStates(data.tasks);
    });

    document.addEventListener('maars:restore-complete', (e) => {
        const { treePayload, plan, execution } = e.detail || {};
        if (treePayload?.treeData?.length) {
            renderPlanAgentTree(treePayload.treeData, treePayload.layout);
            if (plan?.qualityScore != null) updatePlanAgentQualityBadge(plan.qualityScore, plan.qualityComment);
        }

        // On page reload, execution may be idle so no realtime task-state events arrive.
        // Apply persisted execution statuses from snapshot to restore node colors immediately.
        const snapshotTasks = Array.isArray(execution?.tasks) ? execution.tasks : [];
        if (snapshotTasks.length) {
            updateTaskStates(snapshotTasks.map((t) => ({
                task_id: t?.task_id,
                status: t?.status || 'undone',
            })).filter((t) => t.task_id));
        }
    });

    window.MAARS.taskTree = {
        aggregateStatus,
        renderPlanAgentTree,
        renderExecutionTree: (data, layout) => {
            loadZoomLevel();
            renderFull(data, layout, AREA.execution);
            initZoomControls(AREA.execution);
            updateZoomDisplay(AREA.execution);
        },
        clearPlanAgentTree: () => { clear(AREA.decomposition); updatePlanAgentQualityBadge(null); },
        clearExecutionTree: () => clear(AREA.execution),
        initClickHandlers,
        updatePlanAgentQualityBadge,
        updateTaskStates,
        setTreeZoom: (level) => { treeZoomLevel = Math.max(0.5, Math.min(2.0, level)); saveZoomLevel(); },
    };
})();
