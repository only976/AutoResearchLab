/**
 * MAARS plan - generate plan, stop.
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
    if (!cfg || !api) return;

    const ideaInput = document.getElementById('ideaInput');
    const generatePlanBtn = document.getElementById('generatePlanBtn');
    const stopPlanBtn = document.getElementById('stopPlanBtn');
    const loadExampleIdeaBtn = document.getElementById('loadExampleIdeaBtn');

    let planRunAbortController = null;

    async function generatePlan() {
        const idea = (ideaInput?.value || '').trim();
        if (!idea) {
            alert('Please enter an idea first.');
            return;
        }
        let socket = window.MAARS?.state?.socket;
        if (!socket || !socket.connected) {
            window.MAARS.ws?.init();
            await new Promise(resolve => setTimeout(resolve, 500));
            socket = window.MAARS?.state?.socket;
            if (!socket || !socket.connected) {
                alert('WebSocket not connected. Please wait and try again.');
                return;
            }
        }

        try {
            generatePlanBtn.disabled = true;
            if (stopPlanBtn) stopPlanBtn.style.display = '';
            planRunAbortController = new AbortController();

            window.MAARS.taskTree?.clearPlanAgentTree();
            window.MAARS.taskTree?.clearExecutionTree();
            if (window.MAARS?.thinking) window.MAARS.thinking.clear();
            const views = window.MAARS?.views;
            if (views?.state) {
                views.state.executionLayout = null;
                views.state.chainCache = [];
                views.state.previousTaskStates?.clear?.();
            }
            const response = await fetch(`${cfg.API_BASE_URL}/plan/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ idea }),
                signal: planRunAbortController.signal
            });

            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to generate plan');
            if (data.planId) cfg.setCurrentPlanId(data.planId);
        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error('Error generating plan:', error);
            alert('Error: ' + (error.message || 'Failed to generate plan'));
        } finally {
            resetPlanUI();
        }
    }

    function stopPlanRun() {
        fetch(`${cfg.API_BASE_URL}/plan/stop`, { method: 'POST' }).catch(() => {});
        if (planRunAbortController) planRunAbortController.abort();
    }

    function resetPlanUI() {
        if (generatePlanBtn) { generatePlanBtn.disabled = false; generatePlanBtn.textContent = 'Plan'; }
        if (stopPlanBtn) stopPlanBtn.style.display = 'none';
        planRunAbortController = null;
    }

    function init() {
        if (generatePlanBtn) generatePlanBtn.addEventListener('click', generatePlan);
        if (stopPlanBtn) stopPlanBtn.addEventListener('click', stopPlanRun);
        if (loadExampleIdeaBtn) loadExampleIdeaBtn.addEventListener('click', api.loadExampleIdea);
    }

    window.MAARS.plan = { init, generatePlan, stopPlanRun, resetPlanUI };
})();
