/**
 * MAARS API - backend API calls.
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    if (!cfg) return;

    function loadExampleIdea() {
        const ideaInput = document.getElementById('ideaInput');
        if (ideaInput) ideaInput.value = 'Compare Python vs JavaScript for backend development: define evaluation criteria (JSON), research each ecosystem (runtime, frameworks, tooling), and produce a comparison report with pros/cons and scenario-based recommendation.';
    }

    async function loadExecution() {
        try {
            const planId = await cfg.resolvePlanId();
            const response = await fetch(`${cfg.API_BASE_URL}/execution?planId=${encodeURIComponent(planId)}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to load execution');
            return data.execution || null;
        } catch (error) {
            console.error('Error loading execution:', error);
            return null;
        }
    }

    async function clearDb() {
        const res = await fetch(`${cfg.API_BASE_URL}/db/clear`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to clear DB');
        return await res.json();
    }

    async function restoreRecentPlan() {
        if (window.MAARS?.thinking?.clear) window.MAARS.thinking.clear();

        const plansRes = await fetch(`${cfg.API_BASE_URL}/plans`);
        const plansData = await plansRes.json();
        const ids = plansData.planIds || [];
        if (ids.length === 0) {
            throw new Error('No task to restore');
        }
        const planId = ids[0];
        cfg.setCurrentPlanId(planId);

        const [planRes, treeRes, execRes] = await Promise.all([
            fetch(`${cfg.API_BASE_URL}/plan?planId=${encodeURIComponent(planId)}`),
            fetch(`${cfg.API_BASE_URL}/plan/tree?planId=${encodeURIComponent(planId)}`),
            fetch(`${cfg.API_BASE_URL}/execution?planId=${encodeURIComponent(planId)}`),
        ]);
        const planData = await planRes.json();
        const treeData = await treeRes.json();
        const execData = await execRes.json();

        const plan = planData.plan;
        const treePayload = { treeData: treeData.treeData || [], layout: treeData.layout };
        let execution = execData.execution;

        if (plan && plan.idea) {
            const ideaInput = document.getElementById('ideaInput');
            if (ideaInput) ideaInput.value = plan.idea;
        }

        if (treePayload.treeData.length) {
            const taskTree = window.MAARS?.taskTree;
            if (taskTree?.renderPlanAgentTree) taskTree.renderPlanAgentTree(treePayload.treeData, treePayload.layout);
            if (plan?.qualityScore != null && taskTree?.updatePlanAgentQualityBadge) taskTree.updatePlanAgentQualityBadge(plan.qualityScore, plan.qualityComment);
        }

        if (!execution || !execution.tasks?.length) {
            const genRes = await fetch(`${cfg.API_BASE_URL}/execution/generate-from-plan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ planId }),
            });
            const genData = await genRes.json();
            if (!genRes.ok) throw new Error(genData.error || 'Failed to generate execution');
            execution = genData.execution;
        }

        if (execution?.tasks?.length) {
            const layoutRes = await fetch(`${cfg.API_BASE_URL}/plan/layout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ execution, planId }),
            });
            if (!layoutRes.ok) {
                const err = await layoutRes.json();
                throw new Error(err.error || 'Failed to generate layout');
            }
            const layoutData = await layoutRes.json();
            const layout = layoutData.layout;
            if (layout && window.MAARS?.views?.restoreExecution) {
                window.MAARS.views.restoreExecution(layout, execution);
                const socket = window.MAARS?.state?.socket;
                if (socket?.connected) socket.emit('execution-layout', { layout });
            }
        }

        const outRes = await fetch(`${cfg.API_BASE_URL}/plan/outputs?planId=${encodeURIComponent(planId)}`);
        const outData = await outRes.json();
        const outputs = outData.outputs || {};
        if (Object.keys(outputs).length && window.MAARS?.output?.setTaskOutput) {
            Object.entries(outputs).forEach(([taskId, out]) => {
                const val = out && typeof out === 'object' && 'content' in out ? out.content : out;
                window.MAARS.output.setTaskOutput(taskId, val);
            });
            window.MAARS.output.applyOutputHighlight?.();
        }

        return { planId };
    }

    async function retryTask(taskId) {
        const planId = await cfg.resolvePlanId();
        const response = await fetch(`${cfg.API_BASE_URL}/execution/retry-task`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ taskId, planId }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to retry task');
        return data;
    }

    async function resumeFromTask(taskId) {
        const planId = await cfg.resolvePlanId();
        const response = await fetch(`${cfg.API_BASE_URL}/execution/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ planId, resumeFromTaskId: taskId }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to start execution');
        return data;
    }

    window.MAARS.api = { loadExampleIdea, loadExecution, clearDb, restoreRecentPlan, retryTask, resumeFromTask };
})();
