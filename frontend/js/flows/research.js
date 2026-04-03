/**
 * MAARS Research flow - Create page + Research detail page (auto pipeline).
 */
(function () {
    'use strict';

    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
    const executeUtils = window.MAARS?.researchExecuteUtils || {};
    const navUtils = window.MAARS?.researchNavUtils || {};
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
    const executeToggleAllBtnEl = document.getElementById('researchExecuteToggleAllBtn');
    const executeJumpLatestBtnEl = document.getElementById('researchExecuteJumpLatestBtn');
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
    const executionGraphHelpers = window.MAARS?.createResearchExecutionGraphHelpers?.({
        getPayload: () => executionGraphPayload,
        setPayload: (payload) => { executionGraphPayload = payload || { treeData: [], layout: null }; },
        upsertTaskMeta: (task) => _upsertTaskMeta(task),
        getStatuses: () => executeState.statuses,
        getActiveStage: () => activeStage,
    });

    let executeState = {
        order: [],
        statuses: new Map(),
        latestStepBByTask: new Map(),
        recentOutputsByTask: new Map(),
        taskMetaById: new Map(),
        messages: [],
        taskExpandedById: new Map(),
        currentAttemptByTask: new Map(),
        attemptExpandedById: new Map(),
    };
    let executionRuntimeStatus = null;
    let runtimeStatusRequestId = 0;
    let executeElapsedTimerId = 0;
    let executeAutoFollow = true;
    let executeSplitRatio = 80;
    const EXECUTE_TIMELINE_MAX_MESSAGES = 2000;
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
    const execState = window.MAARS?.researchExecuteState || {};
    const loader = window.MAARS?.researchLoader || {};
    const bridges = window.MAARS?.researchEventBridges || {};
    const stageUI = window.MAARS?.researchStageUI || {};
    const coreUtils = window.MAARS?.researchCoreUtils || {};

    function _largeHelperContext() {
        return {
            cfg,
            api,
            executeUtils,
            navUtils,
            homeView,
            researchView,
            promptInput,
            createBtn,
            stageButtons,
            stageMetaEls,
            stageActionBtns,
            panelRefine,
            panelWorkbench,
            panelPaper,
            executeStreamEl,
            executeSplitterEl,
            treeTabButtons,
            treePanels,
            breadcrumbEl,
            titleEl,
            stageData,
            executeState,
            executeStreamBodyEl,
            executeToggleAllBtnEl,
            executeJumpLatestBtnEl,
            executeRuntimeBadgeEl,
            executeRuntimeMetaEl,
            EXECUTE_TIMELINE_MAX_MESSAGES,
            getCurrentResearchId: () => currentResearchId,
            setCurrentResearchId: (id) => { currentResearchId = id; },
            getActiveStage: () => activeStage,
            setActiveStageValue: (stage) => { activeStage = String(stage || '').trim(); },
            getExecuteAutoFollow: () => executeAutoFollow,
            setExecuteAutoFollow: (v) => { executeAutoFollow = !!v; },
            getExecuteSplitRatio: () => executeSplitRatio,
            setExecuteSplitRatio: (v) => { executeSplitRatio = Number(v) || executeSplitRatio; },
            getExecuteElapsedTimerId: () => executeElapsedTimerId,
            setExecuteElapsedTimerId: (id) => { executeElapsedTimerId = id || 0; },
            setCurrentStageState: (next) => { currentStageState = next; },
            getCurrentStageState: () => currentStageState,
            setStageStatusDetails: (next) => { stageStatusDetails = next; },
            getStageStatusDetails: () => stageStatusDetails,
            getExecutionRuntimeStatus: () => executionRuntimeStatus,
            setExecutionRuntimeStatus: (next) => { executionRuntimeStatus = next; },
            getExecutionGraphPayload: () => executionGraphPayload,
            setExecutionGraphPayload: (next) => { executionGraphPayload = next || { treeData: [], layout: null }; },
            refineLogicEl,
            setStageStarted,
            setActiveStage,
            mdToHtml: _mdToHtml,
            ensureTaskInOrder: _ensureTaskInOrder,
            upsertTaskMeta: _upsertTaskMeta,
            getTaskMetaById: _getTaskMetaById,
            setCurrentAttempt: _setCurrentAttempt,
            getCurrentAttempt: _getCurrentAttempt,
            appendExecuteMessage: _appendExecuteMessage,
            stringifyOutput: _stringifyOutput,
            pushRecentOutput: _pushRecentOutput,
            extractValidationDirectReason: _extractValidationDirectReason,
            buildValidationSummaryBody: _buildValidationSummaryBody,
            statusTone: _statusTone,
            statusLabel: _statusLabel,
            updateExecuteToggleAllButton: _updateExecuteToggleAllButton,
            setAllExecuteTaskExpanded: _setAllExecuteTaskExpanded,
            renderRefinePanel: _renderRefinePanel,
            renderPaperPanel: _renderPaperPanel,
            renderExecuteStream,
            scheduleExecutionGraphRender,
            invalidateExecutionGraphRender,
            renderExecutionRuntimeStatus,
            refreshExecutionRuntimeStatus,
            replayPersistedStepEvents: _replayPersistedStepEvents,
            renderStageButtons,
            renderStageStatusDetails,
            syncExecuteElapsedTicker: _syncExecuteElapsedTicker,
            resetExecuteTimelineForNewRun: _resetExecuteTimelineForNewRun,
            loadResearch,
            initExecuteStreamControls,
            initEventBridges,
            _mdToHtml,
            _renderRefinePanel,
            _renderPaperPanel,
            _ensureTaskInOrder,
            _upsertTaskMeta,
            _getTaskMetaById,
            _setCurrentAttempt,
            _getCurrentAttempt,
            _appendExecuteMessage,
            _stringifyOutput,
            _pushRecentOutput,
            _extractValidationDirectReason,
            _buildValidationSummaryBody,
            get activeStage() { return activeStage; },
            get currentResearchId() { return currentResearchId; },
            get currentStageState() { return currentStageState; },
            get stageStatusDetails() { return stageStatusDetails; },
            get executionGraphPayload() { return executionGraphPayload; },
            set executionGraphPayload(next) { executionGraphPayload = next || { treeData: [], layout: null }; },
        };
    }

    function setStageStarted(stage, started) {
        stageUI.setStageStarted?.(_largeHelperContext(), stage, started);
    }

    function _isStagePrerequisiteCompleted(stage) {
        if (typeof stageUI.isStagePrerequisiteCompleted === 'function') {
            return !!stageUI.isStagePrerequisiteCompleted(_largeHelperContext(), stage);
        }
        return true;
    }

    function renderStageButtons(activeStage) {
        stageUI.renderStageButtons?.(_largeHelperContext(), activeStage);
    }

    function renderStageStatusDetails() {
        stageUI.renderStageStatusDetails?.(_largeHelperContext());
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
        } catch (_) { }
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

        const paperStatus = stageStatusDetails?.paper?.status || 'idle';
        if (paperStatus === 'running') {
            const escapeHtml = (s) => String(s || '').replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');
            const logs = stageData.paperLogs || [];
            if (logs.length > 0) {
                const logsHtml = logs.map(line => `<div>${escapeHtml(line)}</div>`).join('');
                paperBodyEl.innerHTML = `<div class="paper-logs" style="line-height: 1.6; white-space: pre-wrap; overflow-y: auto; max-height: 800px; padding: 10px;">${logsHtml}</div>`;
                const container = paperBodyEl.querySelector('.paper-logs');
                if (container) container.scrollTop = container.scrollHeight;
            } else {
                paperBodyEl.innerHTML = '<div>Starting Paper Agent...</div>';
            }
            return;
        }

        const format = (stageData.paperFormat || 'markdown').trim();
        if (format === 'latex' && stageData.pdfUrl) {
            paperBodyEl.innerHTML = `<iframe src="${stageData.pdfUrl}" width="100%" height="800px" style="border: 1px solid #ccc; border-radius: 4px;"></iframe>`;
        } else if (format === 'latex' && !stageData.pdfUrl && stageData.paper) {
            paperBodyEl.innerHTML = '—';
        } else {
            const content = (stageData.paper || '').trim();
            paperBodyEl.innerHTML = content ? _mdToHtml(content) : '—';
        }
    }

    function setTreeView(view) {
        stageUI.setTreeView?.(_largeHelperContext(), view);
    }

    function setActiveStage(stage) {
        stageUI.setActiveStage?.(_largeHelperContext(), stage);
    }

    function _stringifyOutput(val) {
        return coreUtils.stringifyOutput?.(_largeHelperContext(), val) ?? String(val || '');
    }

    function _ensureTaskInOrder(taskId) {
        return coreUtils.ensureTaskInOrder?.(_largeHelperContext(), taskId) ?? '';
    }

    function _updateExecuteToggleAllButton() {
        coreUtils.updateExecuteToggleAllButton?.(_largeHelperContext());
    }

    function _setAllExecuteTaskExpanded(expanded) {
        coreUtils.setAllExecuteTaskExpanded?.(_largeHelperContext(), expanded);
    }

    function _upsertTaskMeta(task) {
        coreUtils.upsertTaskMeta?.(_largeHelperContext(), task);
    }

    function _getTaskMetaById(taskId) {
        return coreUtils.getTaskMetaById?.(_largeHelperContext(), taskId) ?? null;
    }

    function _pushRecentOutput(taskId, outputText) {
        coreUtils.pushRecentOutput?.(_largeHelperContext(), taskId, outputText);
    }

    function _statusLabel(status) {
        return coreUtils.statusLabel?.(_largeHelperContext(), status) ?? String(status || 'undone');
    }

    function _statusTone(status) {
        return coreUtils.statusTone?.(_largeHelperContext(), status) ?? 'pending';
    }

    function _extractValidationDirectReason(reportText) {
        return coreUtils.extractValidationDirectReason?.(_largeHelperContext(), reportText) ?? 'Validation gate failed.';
    }

    function _buildValidationSummaryBody(taskId, detail, meta, options = {}) {
        return coreUtils.buildValidationSummaryBody?.(_largeHelperContext(), taskId, detail, meta, options) ?? 'Validation report unavailable.';
    }

    function renderExecutionRuntimeStatus(status) {
        coreUtils.renderExecutionRuntimeStatus?.(_largeHelperContext(), status);
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
        execState.appendExecuteMessage?.(_largeHelperContext(), message);
    }

    function _syncExecuteElapsedTicker() {
        coreUtils.syncExecuteElapsedTicker?.(_largeHelperContext());
    }

    function _getAttemptKey(taskId, attempt) {
        return coreUtils.getAttemptKey?.(_largeHelperContext(), taskId, attempt)
            ?? `${String(taskId || '').trim()}:${Number(attempt) || 1}`;
    }

    function _getCurrentAttempt(taskId) {
        return coreUtils.getCurrentAttempt?.(_largeHelperContext(), taskId) ?? 1;
    }

    function _setCurrentAttempt(taskId, attempt) {
        coreUtils.setCurrentAttempt?.(_largeHelperContext(), taskId, attempt);
    }

    function _replayPersistedStepEvents(stepEvents) {
        coreUtils.replayPersistedStepEvents?.(_largeHelperContext(), stepEvents);
    }

    function scheduleExecutionGraphRender(options = {}) {
        executionGraphHelpers?.schedule?.(options);
    }

    function invalidateExecutionGraphRender() {
        executionGraphHelpers?.invalidate?.();
    }

    function _upsertExecuteThinkingMessage(taskId, operation, body, scheduleInfo, attemptHint) {
        execState.upsertExecuteThinkingMessage?.(
            _largeHelperContext(),
            taskId,
            operation,
            body,
            scheduleInfo,
            attemptHint,
        );
    }

    function _seedExecutionState(treeData, execution, outputs, options = {}) {
        execState.seedExecutionState?.(_largeHelperContext(), treeData, execution, outputs, options);
    }

    function _resetExecuteTimelineForNewRun() {
        execState.resetExecuteTimelineForNewRun?.(_largeHelperContext());
    }

    function renderExecuteStream() {
        execState.renderExecuteStream?.(_largeHelperContext());
    }

    function initExecuteStreamControls() {
        execState.initExecuteStreamControls?.(_largeHelperContext());
    }

    function navigateToCreateResearch() {
        if (typeof stageUI.navigateToCreateResearch === 'function') {
            stageUI.navigateToCreateResearch(_largeHelperContext());
            return;
        }
        if (typeof navUtils.navigateToCreateResearch === 'function') navUtils.navigateToCreateResearch();
    }

    function navigateToResearch(researchId) {
        if (typeof stageUI.navigateToResearch === 'function') {
            stageUI.navigateToResearch(_largeHelperContext(), researchId);
            return;
        }
        if (typeof navUtils.navigateToResearch === 'function') navUtils.navigateToResearch(researchId);
    }

    function initStageNav() {
        stageUI.initStageNav?.(_largeHelperContext());
    }

    function initTreeTabs() {
        stageUI.initTreeTabs?.(_largeHelperContext());
    }

    function initExecuteSplitter() {
        stageUI.initExecuteSplitter?.(_largeHelperContext());
    }

    async function createResearchFromHome() {
        await stageUI.createResearchFromHome?.(_largeHelperContext());
    }

    async function loadResearch(researchId) {
        await loader.loadResearch?.(_largeHelperContext(), researchId);
    }

    function initDetailControls(researchId) {
        stageUI.initDetailControls?.(_largeHelperContext(), researchId);
    }

    function initEventBridges() {
        bridges.initEventBridges?.(_largeHelperContext());
    }

    function init() {
        if (typeof stageUI.init === 'function') {
            stageUI.init(_largeHelperContext());
            return;
        }
        initExecuteStreamControls();
        initEventBridges();
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.research = { init, navigateToResearch, navigateToCreateResearch };
})();
