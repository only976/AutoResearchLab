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
    const createPopoverController = window.MAARS?.createTaskTreePopoverController;
    const createZoomController = window.MAARS?.createTaskTreeZoomController;
    const createTaskTreeRenderer = window.MAARS?.createTaskTreeRenderer;
    const bindTaskTreeEvents = window.MAARS?.bindTaskTreeEvents;

    const escapeHtml = (window.MAARS?.utils?.escapeHtml) || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));

    function deriveDisplayTitle(task) {
        const explicit = String(task?.title || '').replace(/\s+/g, ' ').trim();
        const raw = explicit || String(task?.description || task?.objective || '').replace(/\s+/g, ' ').trim();
        if (!raw) return String(task?.task_id || 'Task');
        const first = raw.split(/[\n\.;:!?]/, 1)[0].trim() || raw;
        if (/[\u4e00-\u9fff]/.test(first)) {
            if (first.length <= 12) return first;
            return first.slice(0, 12).replace(/[，。；：、\s]+$/g, '') + '…';
        }
        const words = first.split(/\s+/).filter(Boolean);
        if (words.length > 8) return words.slice(0, 8).join(' ') + '…';
        if (first.length <= 48) return first;
        return first.slice(0, 47).trimEnd() + '…';
    }

    let planAgentTreeData = [];
    let planAgentLayout = null;

    function getTreeContainer(areaSelector) {
        const area = document.querySelector(areaSelector);
        const tree = area?.querySelector('.tasks-tree');
        return area && tree ? { area, tree } : null;
    }

    let renderFull = () => {};
    let clearRenderedTree = () => {};
    let aggregateStatus = () => 'undone';

    const zoomController = createZoomController
        ? createZoomController({
            getTreeContainer,
            onZoomChange: (areaSelector) => {
                if (areaSelector === AREA.decomposition) {
                    renderFull(planAgentTreeData, planAgentLayout, areaSelector);
                }
            },
        })
        : {
            getLevel: () => 1.0,
            initZoomControls: () => {},
            loadZoomLevel: () => {},
            setLevel: () => {},
            updateZoomDisplay: () => {},
        };

    const renderer = createTaskTreeRenderer
        ? createTaskTreeRenderer({
            AREA,
            deriveDisplayTitle,
            getTreeContainer,
            getZoomLevel: () => zoomController.getLevel(),
        })
        : null;

    if (renderer) {
        renderFull = renderer.renderFull;
        clearRenderedTree = renderer.clear;
        aggregateStatus = renderer.aggregateStatus;
    }

    const popoverController = createPopoverController
        ? createPopoverController({ deriveDisplayTitle, escapeHtml })
        : { initClickHandlers: () => {} };

    function clear(areaSelector) {
        if (areaSelector === AREA.decomposition) {
            planAgentTreeData = [];
            planAgentLayout = null;
        }
        clearRenderedTree(areaSelector);
    }

    function renderPlanAgentTree(treeData, layout) {
        if (!Array.isArray(treeData)) return;
        planAgentTreeData = treeData || [];
        planAgentLayout = layout || null;
        zoomController.loadZoomLevel();
        renderFull(treeData, layout, AREA.decomposition);
        zoomController.initZoomControls(AREA.decomposition);
        zoomController.updateZoomDisplay(AREA.decomposition);
    }

    function renderExecutionTree(data, layout) {
        zoomController.loadZoomLevel();
        renderFull(data, layout, AREA.execution);
        zoomController.initZoomControls(AREA.execution);
        zoomController.updateZoomDisplay(AREA.execution);
    }

    function initClickHandlers() {
        popoverController.initClickHandlers();
    }

    function updateTaskStates(tasks) {
        if (!tasks || !Array.isArray(tasks)) return;
        const areas = document.querySelectorAll('.plan-agent-tree-area, .plan-agent-execution-tree-area');
        tasks.forEach((taskState) => {
            const taskId = String(taskState?.task_id || taskState?.taskId || '').trim();
            const status = String(taskState?.status || '').trim();
            if (!taskId) return;
            areas.forEach((treeArea) => {
                if (!treeArea) return;
                const byId = treeArea.querySelectorAll(`[data-task-id="${taskId}"]`);
                const byIds = treeArea.querySelectorAll('[data-task-ids]');
                const cells = Array.from(byId);
                byIds.forEach((cell) => {
                    const ids = (cell.getAttribute('data-task-ids') || '').split(',').map((s) => s.trim());
                    if (ids.includes(taskId)) cells.push(cell);
                });
                cells.forEach((cell) => {
                    cell.classList.remove('task-status-undone', 'task-status-doing', 'task-status-validating', 'task-status-done', 'task-status-validation-failed', 'task-status-execution-failed');
                    const dataAttr = cell.getAttribute('data-task-data');
                    if (dataAttr) {
                        try {
                            const parsed = JSON.parse(dataAttr);
                            const arr = Array.isArray(parsed) ? parsed : [parsed];
                            const updated = arr.map((t) => (t.task_id === taskId ? { ...t, status } : t));
                            cell.setAttribute('data-task-data', JSON.stringify(Array.isArray(parsed) ? updated : updated[0]));
                            const mergedStatus = arr.length === 1 ? status : aggregateStatus(updated);
                            if (mergedStatus && mergedStatus !== 'undone') cell.classList.add(`task-status-${mergedStatus}`);
                        } catch (_) {
                            if (status && status !== 'undone') cell.classList.add(`task-status-${status}`);
                        }
                    } else if (status && status !== 'undone') {
                        cell.classList.add(`task-status-${status}`);
                    }
                    document.querySelectorAll(`.task-detail-tab[data-tab-task-id="${taskId}"]`).forEach((tab) => {
                        tab.classList.remove('task-status-undone', 'task-status-doing', 'task-status-validating', 'task-status-done', 'task-status-validation-failed', 'task-status-execution-failed');
                        if (status && status !== 'undone') tab.classList.add(`task-status-${status}`);
                    });
                });
            });
        });
    }

    function updatePlanAgentQualityBadge(score, comment) {
        const badge = document.getElementById('planAgentQualityBadge');
        if (!badge) return;
        if (score == null || score === undefined) {
            badge.hidden = true;
            return;
        }
        badge.textContent = `Quality: ${score}`;
        badge.title = comment || '';
        badge.hidden = false;
        badge.classList.remove('quality-high', 'quality-mid', 'quality-low');
        if (score >= 80) badge.classList.add('quality-high');
        else if (score >= 60) badge.classList.add('quality-mid');
        else badge.classList.add('quality-low');
    }

    if (bindTaskTreeEvents) {
        bindTaskTreeEvents({
            AREA,
            clear,
            renderPlanAgentTree,
            updatePlanAgentQualityBadge,
            updateTaskStates,
        });
    }

    window.MAARS.taskTree = {
        aggregateStatus,
        renderPlanAgentTree,
        renderExecutionTree,
        clearPlanAgentTree: () => { clear(AREA.decomposition); updatePlanAgentQualityBadge(null); },
        clearExecutionTree: () => clear(AREA.execution),
        initClickHandlers,
        updatePlanAgentQualityBadge,
        updateTaskStates,
        setTreeZoom: (level) => zoomController.setLevel(level),
    };
})();
