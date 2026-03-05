/**
 * MAARS Research flow - Home (create) + Research page (auto pipeline).
 */
(function () {
    'use strict';

    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
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

    let currentResearchId = null;
    let currentStageState = {
        refine: { started: false },
        plan: { started: false },
        execute: { started: false },
        paper: { started: false },
    };

    function setStageStarted(stage, started) {
        if (!currentStageState[stage]) return;
        currentStageState[stage].started = !!started;
        renderStageButtons();
    }

    function renderStageButtons(activeStage) {
        Object.entries(stageButtons).forEach(([stage, btn]) => {
            if (!btn) return;
            const started = !!currentStageState?.[stage]?.started;
            btn.disabled = !started;
            btn.setAttribute('aria-disabled', started ? 'false' : 'true');
            btn.classList.toggle('is-active', stage === activeStage);
        });
    }

    function showHome() {
        currentResearchId = null;
        try { cfg.setCurrentResearchId?.(''); } catch (_) {}
        if (homeView) homeView.hidden = false;
        if (researchView) researchView.hidden = true;
    }

    function showResearch() {
        if (homeView) homeView.hidden = true;
        if (researchView) researchView.hidden = false;
    }

    function parseHash() {
        const hash = (window.location.hash || '').replace(/^#/, '');
        const m = hash.match(/^\/r\/(.+)$/);
        if (m) return { view: 'research', researchId: decodeURIComponent(m[1]) };
        return { view: 'home' };
    }

    function navigateToResearch(researchId) {
        window.location.hash = `#/r/${encodeURIComponent(researchId)}`;
    }

    function _scrollToDetails() {
        const host = document.getElementById('researchDetailHost');
        if (!host) return;
        host.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function initStageNav() {
        Object.entries(stageButtons).forEach(([stage, btn]) => {
            if (!btn) return;
            btn.addEventListener('click', () => {
                if (btn.disabled) return;
                renderStageButtons(stage);
                // minimal interpretation: clicking stage focuses the details area
                _scrollToDetails();
            });
        });
    }

    async function createResearchFromHome() {
        const prompt = (promptInput?.value || '').trim();
        if (!prompt) return;
        createBtn && (createBtn.disabled = true);
        try {
            const { researchId } = await api.createResearch(prompt);
            if (!researchId) throw new Error('Create failed');
            document.dispatchEvent(new CustomEvent('maars:research-list-refresh'));
            navigateToResearch(researchId);
        } catch (e) {
            console.error(e);
            alert(e?.message || 'Failed to create research');
        } finally {
            createBtn && (createBtn.disabled = false);
        }
    }

    async function loadResearch(researchId) {
        currentResearchId = researchId;
        cfg.setCurrentResearchId?.(researchId);
        showResearch();

        // clear UI, then restore from DB snapshot
        document.dispatchEvent(new CustomEvent('maars:restore-start'));

        const data = await api.getResearch(researchId);
        const research = data?.research || {};
        const idea = data?.idea || null;
        const plan = data?.plan || null;
        const execution = data?.execution || null;
        const outputs = data?.outputs || {};
        const paper = data?.paper || null;

        if (breadcrumbEl) breadcrumbEl.textContent = 'Research';
        if (titleEl) titleEl.textContent = research.title || research.researchId || 'Research';

        // Stage enablement: stage becomes clickable once started.
        // Use DB snapshot heuristics + runtime events.
        currentStageState = {
            refine: { started: !!research.currentIdeaId },
            plan: { started: !!research.currentPlanId },
            execute: { started: !!(execution && execution.tasks && execution.tasks.length) },
            paper: { started: !!paper },
        };
        renderStageButtons();

        const ideaId = research.currentIdeaId || '';
        const planId = research.currentPlanId || '';
        if (ideaId) cfg.setCurrentIdeaId?.(ideaId);
        if (planId) cfg.setCurrentPlanId?.(planId);

        let treePayload = { treeData: [], layout: null };
        if (ideaId && planId) {
            try {
                const res = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/plan/tree?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`);
                const json = await res.json();
                if (res.ok) treePayload = { treeData: json.treeData || [], layout: json.layout || null };
            } catch (_) {}
        }

        document.dispatchEvent(new CustomEvent('maars:restore-complete', {
            detail: {
                ideaId,
                planId,
                treePayload,
                plan,
                execution,
                outputs: outputs || {},
                ideaText: idea?.idea || research.prompt || '',
            },
        }));

        // Restore refine + paper output using their normal event paths.
        if (idea && (idea.keywords || idea.papers || idea.refined_idea)) {
            document.dispatchEvent(new CustomEvent('maars:idea-complete', {
                detail: {
                    ideaId,
                    keywords: idea.keywords || [],
                    papers: idea.papers || [],
                    refined_idea: idea.refined_idea || '',
                },
            }));
        }
        if (paper?.content) {
            document.dispatchEvent(new CustomEvent('maars:paper-complete', {
                detail: {
                    ideaId,
                    planId,
                    content: paper.content,
                    format: paper.format || 'markdown',
                },
            }));
        }

        // Auto-run pipeline when entering research page.
        try {
            await api.runResearch(researchId);
        } catch (e) {
            // Ignore 409 conflicts (already running)
            const msg = String(e?.message || '');
            if (!/already running|409/.test(msg)) console.warn('runResearch failed', e);
        }
    }

    async function onRouteChange() {
        const route = parseHash();
        if (route.view === 'research' && route.researchId) {
            try {
                await loadResearch(route.researchId);
            } catch (e) {
                console.error(e);
                alert(e?.message || 'Failed to load research');
                showHome();
            }
            return;
        }
        showHome();
    }

    function initEventBridges() {
        // Update stage state based on live pipeline events.
        document.addEventListener('maars:idea-start', () => setStageStarted('refine', true));
        document.addEventListener('maars:plan-start', () => setStageStarted('plan', true));
        document.addEventListener('maars:task-start', () => setStageStarted('execute', true));
        document.addEventListener('maars:paper-start', () => setStageStarted('paper', true));

        document.addEventListener('maars:research-stage', (e) => {
            const d = e?.detail || {};
            if (d.researchId && currentResearchId && d.researchId !== currentResearchId) return;
            if (d.stage && currentStageState[d.stage] != null) {
                setStageStarted(d.stage, true);
                renderStageButtons(d.stage);
            }
            document.dispatchEvent(new CustomEvent('maars:research-list-refresh'));
        });

        document.addEventListener('maars:research-error', (e) => {
            const d = e?.detail || {};
            if (d.researchId && currentResearchId && d.researchId !== currentResearchId) return;
            if (d.error) console.warn('Research error:', d.error);
        });

        // Keep sidebar list in sync
        document.addEventListener('maars:research-list-refresh', () => {
            window.MAARS?.sidebar?.refreshResearchList?.();
        });
    }

    function init() {
        initStageNav();
        initEventBridges();

        createBtn?.addEventListener('click', createResearchFromHome);
        promptInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                createResearchFromHome();
            }
        });

        window.addEventListener('hashchange', () => {
            onRouteChange().catch(() => {});
        });

        onRouteChange().catch(() => {});
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.research = { init, navigateToResearch };
})();
