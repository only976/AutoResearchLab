/**
 * MAARS API - backend API calls.
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    const researchApi = window.MAARS?.researchApi || {};
    if (!cfg) return;

    function loadExampleIdea() {
        const ideaInput = document.getElementById('ideaInput');
        if (ideaInput) ideaInput.value = 'Compare Python vs JavaScript for backend development: define evaluation criteria (JSON), research each ecosystem (runtime, frameworks, tooling), and produce a comparison report with pros/cons and scenario-based recommendation.';
    }

    async function getExecutionRuntimeStatus(ideaId, planId) {
        const params = new URLSearchParams();
        if (ideaId) params.set('ideaId', ideaId);
        if (planId) params.set('planId', planId);

        const query = params.toString();
        const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution/runtime-status${query ? `?${query}` : ''}`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Failed to load execution runtime status');
        return data;
    }

    async function fetchStatus() {
        try {
            const res = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/status`);
            if (!res.ok) return { hasIdea: false, hasPlan: false };
            const data = await res.json();
            return { hasIdea: !!data.hasIdea, hasPlan: !!data.hasPlan };
        } catch (_) {
            return { hasIdea: false, hasPlan: false };
        }
    }

    async function clearDb() {
        const res = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/db/clear`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to clear DB');
        return await res.json();
    }

    async function restoreRecentPlan() {
        document.dispatchEvent(new CustomEvent('maars:restore-start'));

        const plansRes = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/plans`);
        const plansData = await plansRes.json();
        const items = plansData.items || [];
        if (items.length === 0) {
            throw new Error('No task to restore');
        }
        const { ideaId, planId } = items[0];
        cfg.setCurrentIdeaId(ideaId);
        cfg.setCurrentPlanId(planId);

        const [planRes, treeRes, execRes, ideaRes] = await Promise.all([
            cfg.fetchWithSession(`${cfg.API_BASE_URL}/plan?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`),
            cfg.fetchWithSession(`${cfg.API_BASE_URL}/plan/tree?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`),
            cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`),
            cfg.fetchWithSession(`${cfg.API_BASE_URL}/idea?ideaId=${encodeURIComponent(ideaId)}`),
        ]);
        const planData = await planRes.json();
        const treeData = await treeRes.json();
        const execData = await execRes.json();
        const ideaData = await ideaRes.json();

        const plan = planData.plan;
        const ideaObj = ideaData.idea;
        const treePayload = { treeData: treeData.treeData || [], layout: treeData.layout };
        let execution = execData.execution;

        if (!execution || !execution.tasks?.length) {
            const genRes = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution/generate-from-plan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ideaId, planId }),
            });
            const genData = await genRes.json();
            if (!genRes.ok) throw new Error(genData.error || 'Failed to generate execution');
            execution = genData.execution;
        }

        let layout = null;
        if (execution?.tasks?.length) {
            const layoutRes = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/plan/layout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ execution, ideaId, planId }),
            });
            if (!layoutRes.ok) {
                const err = await layoutRes.json();
                throw new Error(err.error || 'Failed to generate layout');
            }
            const layoutData = await layoutRes.json();
            layout = layoutData.layout;
        }

        const outRes = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/plan/outputs?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`);
        const outData = await outRes.json();
        const outputs = outData.outputs || {};

        document.dispatchEvent(new CustomEvent('maars:restore-complete', {
            detail: {
                ideaId,
                planId,
                treePayload,
                plan,
                layout,
                execution,
                outputs,
                ideaText: ideaObj?.idea || '',
            },
        }));

        return { ideaId, planId };
    }

    async function retryTask(taskId) {
        const { ideaId, planId } = await cfg.resolvePlanIds();
        const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution/retry-task`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ taskId, ideaId, planId }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to retry task');
        return data;
    }

    /**
     * 统一终止函数：停止指定 agent 的运行。
     * @param {'idea'|'plan'|'task'} agent - idea=Refine, plan=Plan, task=Execution
     */
    async function stopAgent(agent) {
        const routes = { idea: '/idea/stop', plan: '/plan/stop', task: '/execution/stop', paper: '/paper/stop' };
        const path = routes[agent];
        if (!path) return;
        const res = await cfg.fetchWithSession(`${cfg.API_BASE_URL}${path}`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to stop');
        return res.json();
    }

    async function refineIdea(idea, limit) {
        const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/idea/collect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ idea: idea || '', limit: limit || 10 }),
        });
        const data = await response.json();
        if (!response.ok) {
            if (data.ideaId) cfg.setCurrentIdeaId(data.ideaId);
            throw new Error(data.error || 'Refine failed');
        }
        return data;
    }

    async function generateIdea(ideaId, generateIdeaInput) {
        const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/ideas/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ideaId: ideaId || undefined,
                generateIdeaInput: generateIdeaInput || undefined,
            }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || data.detail || 'Generate idea failed');
        return data;
    }

    async function resumeFromTask(taskId) {
        const { ideaId, planId } = await cfg.resolvePlanIds();
        const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ideaId, planId, resumeFromTaskId: taskId }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to start execution');
        return data;
    }

    window.MAARS.api = {
        loadExampleIdea,
        getExecutionRuntimeStatus,
        clearDb,
        fetchStatus,
        restoreRecentPlan,
        retryTask,
        resumeFromTask,
        refineIdea,
        generateIdea,
        stopAgent,
        createResearch: researchApi.createResearch,
        listResearches: researchApi.listResearches,
        getResearch: researchApi.getResearch,
        runResearch: researchApi.runResearch,
        stopResearch: researchApi.stopResearch,
        retryResearch: researchApi.retryResearch,
        runResearchStage: researchApi.runResearchStage,
        resumeResearchStage: researchApi.resumeResearchStage,
        retryResearchStage: researchApi.retryResearchStage,
        stopResearchStage: researchApi.stopResearchStage,
        deleteResearch: researchApi.deleteResearch,
    };
})();
