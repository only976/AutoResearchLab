/**
 * Research loading function extracted from research-large-helpers.
 */
(function () {
    'use strict';

    const { seedExecutionState } = window.MAARS?.researchExecuteState || {};

    async function loadResearch(ctx, researchId) {
        ctx.setCurrentResearchId(researchId);
        ctx.cfg.setCurrentResearchId?.(researchId);

        document.dispatchEvent(new CustomEvent('maars:restore-start'));

        const data = await ctx.api.getResearch(researchId);
        const research = data?.research || {};
        const idea = data?.idea || null;
        const plan = data?.plan || null;
        const execution = data?.execution || null;
        const outputs = data?.outputs || {};
        const stepEvents = data?.stepEvents || { runId: '', events: [] };
        const paper = data?.paper || null;

        if (ctx.breadcrumbEl) ctx.breadcrumbEl.textContent = 'Research';
        if (ctx.titleEl) ctx.titleEl.textContent = research.title || research.researchId || 'Research';

        ctx.stageData.originalIdea = (idea?.idea || research.prompt || '').trim();
        ctx.stageData.papers = Array.isArray(idea?.papers) ? idea.papers : [];
        ctx.stageData.refined = (idea?.refined_idea || '').trim();
        ctx.stageData.refineThinking = '';
        ctx.stageData.paper = (paper?.content || '').trim();
        ctx.stageData.paperFormat = (paper?.format || 'markdown').trim();
        ctx.stageData.pdfUrl = (ctx.stageData.paperFormat === 'latex' && execution?.runId) ? `/api/paper/pdf/${execution.runId}` : '';
        ctx.renderRefinePanel();
        ctx.renderPaperPanel();

        ctx.setCurrentStageState({
            refine: { started: !!(research.currentIdeaId || ctx.stageData.refined || ctx.stageData.papers.length) },
            plan: { started: !!(plan && Array.isArray(plan.tasks) && plan.tasks.length) },
            execute: { started: !!(execution && Array.isArray(execution.tasks) && execution.tasks.length) },
            paper: { started: !!(paper && String(paper.content || '').trim()) },
        });
        ctx.setStageStatusDetails({
            refine: { status: 'idle', message: 'idle' },
            plan: { status: 'idle', message: 'idle' },
            execute: { status: 'idle', message: 'idle' },
            paper: { status: 'idle', message: 'idle' },
        });
        const rs = String(research.stage || 'refine').trim() || 'refine';
        const rss = String(research.stageStatus || 'idle').trim() || 'idle';
        const order = ['refine', 'plan', 'execute', 'paper'];
        const rank = order.indexOf(rs);
        const stageStatusDetails = ctx.getStageStatusDetails();
        if (rank >= 0) {
            if (rss === 'completed') {
                for (let i = 0; i <= rank; i += 1) {
                    const s = order[i];
                    stageStatusDetails[s] = { status: 'completed', message: 'completed' };
                }
            } else if (rss === 'running' || rss === 'stopped' || rss === 'failed') {
                for (let i = 0; i < rank; i += 1) {
                    const s = order[i];
                    stageStatusDetails[s] = { status: 'completed', message: 'completed' };
                }
                stageStatusDetails[rs] = { status: rss, message: rss };
            } else {
                stageStatusDetails[rs] = { status: rss, message: rss };
            }
        }
        ctx.renderStageButtons();

        const ideaId = research.currentIdeaId || '';
        const planId = research.currentPlanId || '';
        ctx.cfg.setCurrentIdeaId?.(ideaId);
        ctx.cfg.setCurrentPlanId?.(planId);

        let treePayload = { treeData: [], layout: null };
        let executionLayout = null;
        let executionForRestore = execution;
        if (ideaId && planId) {
            try {
                const res = await ctx.cfg.fetchWithSession(`${ctx.cfg.API_BASE_URL}/plan/tree?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`);
                const json = await res.json();
                if (res.ok) treePayload = { treeData: json.treeData || [], layout: json.layout || null };
            } catch (_) { }

            try {
                let executionSnapshot = execution;
                let execTasks = Array.isArray(executionSnapshot?.tasks) ? executionSnapshot.tasks : [];
                if (!execTasks.length) {
                    const genRes = await ctx.cfg.fetchWithSession(`${ctx.cfg.API_BASE_URL}/execution/generate-from-plan`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ideaId, planId }),
                    });
                    const genJson = await genRes.json().catch(() => ({}));
                    const generatedExecution = genJson?.execution;
                    if (genRes.ok && Array.isArray(generatedExecution?.tasks) && generatedExecution.tasks.length) {
                        executionSnapshot = generatedExecution;
                        execTasks = generatedExecution.tasks;
                    }
                }
                if (execTasks.length) {
                    executionForRestore = executionSnapshot;
                    const layoutRes = await ctx.cfg.fetchWithSession(`${ctx.cfg.API_BASE_URL}/plan/layout`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ execution: executionSnapshot, ideaId, planId }),
                    });
                    const layoutJson = await layoutRes.json().catch(() => ({}));
                    if (layoutRes.ok && layoutJson?.layout) {
                        executionLayout = layoutJson.layout;
                        ctx.setExecutionGraphPayload({
                            treeData: Array.isArray(layoutJson.layout?.treeData) ? layoutJson.layout.treeData : [],
                            layout: layoutJson.layout?.layout || null,
                        });
                        ctx.invalidateExecutionGraphRender();
                    }
                }
            } catch (_) { }
        }

        document.dispatchEvent(new CustomEvent('maars:restore-complete', {
            detail: {
                ideaId,
                planId,
                treePayload,
                plan,
                layout: executionLayout,
                execution: executionForRestore,
                outputs: outputs || {},
                ideaText: idea?.idea || research.prompt || '',
            },
        }));

        const hasPersistedTimeline = Array.isArray(stepEvents?.events) && stepEvents.events.length > 0;
        seedExecutionState(ctx, treePayload.treeData, executionForRestore, outputs, {
            skipOutputSeed: hasPersistedTimeline,
        });
        if (hasPersistedTimeline) {
            ctx.replayPersistedStepEvents(stepEvents);
        }
        if (ctx.getExecutionGraphPayload()?.layout) {
            ctx.scheduleExecutionGraphRender({ force: true, allowInactive: true, delays: [0, 100, 320, 700] });
        }
        if (ctx.getActiveStage() === 'execute') ctx.renderExecuteStream();
        ctx.refreshExecutionRuntimeStatus({ ideaId, planId });

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
                    pdfUrl: ctx.stageData.pdfUrl
                },
            }));
        }

        try {
            const stageStatus = String(research.stageStatus || '').trim().toLowerCase();
            if (stageStatus === 'idle') {
                await ctx.api.runResearch(researchId);
            }
        } catch (e) {
            const msg = String(e?.message || '');
            if (!/already running|409/.test(msg)) console.warn('runResearch failed', e);
        }
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.researchLoader = { loadResearch };
})();
