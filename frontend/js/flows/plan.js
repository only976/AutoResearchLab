/**
 * MAARS Plan 流程 - Plan 生成、Stop。
 * 独立模块，不依赖 idea/task。派发 maars:plan-start / 监听 maars:idea-complete。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
    if (!cfg || !api) return;

    const ideaInput = document.getElementById('ideaInput');
    const generatePlanBtn = document.getElementById('generatePlanBtn');
    const stopPlanBtn = document.getElementById('stopPlanBtn');

    let isPlanRunning = false;

    /** 仅更新 Plan 按钮状态：看 db 是否有 idea_id。 */
    async function updateButtonStates() {
        const status = await api.fetchStatus?.() || { hasIdea: false };
        if (generatePlanBtn) generatePlanBtn.disabled = !status.hasIdea || isPlanRunning;
    }

    async function generatePlan() {
        const idea = (ideaInput?.value || '').trim();
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
            isPlanRunning = true;
            generatePlanBtn.disabled = true;
            if (stopPlanBtn) stopPlanBtn.style.display = '';
            document.dispatchEvent(new CustomEvent('maars:plan-start'));
            const ideaId = cfg.getCurrentIdeaId?.() || null;
            const response = await fetch(`${cfg.API_BASE_URL}/plan/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ idea, ideaId: ideaId || undefined }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to generate plan');
            if (data.ideaId) cfg.setCurrentIdeaId(data.ideaId);
            if (data.planId) cfg.setCurrentPlanId(data.planId);
            /* 完成数据由 WebSocket plan-complete 回传，onPlanComplete 负责 resetPlanUI */
        } catch (error) {
            console.error('Error generating plan:', error);
            alert('Error: ' + (error.message || 'Failed to generate plan'));
            resetPlanUI();
        }
    }

    function stopPlanRun() {
        resetPlanUI(); /* 立即恢复按钮，不等待后端 */
        api.stopAgent('plan').catch(() => {});
    }

    function resetPlanUI() {
        if (generatePlanBtn) generatePlanBtn.textContent = 'Plan';
        if (stopPlanBtn) stopPlanBtn.style.display = 'none';
        isPlanRunning = false;
        updateButtonStates();
    }

    function onRefineComplete() {
        updateButtonStates();
    }

    function onPlanComplete(e) {
        const data = e?.detail || {};
        if (data.ideaId) cfg.setCurrentIdeaId(data.ideaId);
        if (data.planId) cfg.setCurrentPlanId(data.planId);
        resetPlanUI();
    }

    document.addEventListener('maars:plan-error', () => resetPlanUI());

    document.addEventListener('maars:restore-complete', () => updateButtonStates());

    function init() {
        if (generatePlanBtn) generatePlanBtn.addEventListener('click', generatePlan);
        if (stopPlanBtn) stopPlanBtn.addEventListener('click', stopPlanRun);
        document.addEventListener('maars:idea-complete', onRefineComplete);
        document.addEventListener('maars:plan-complete', onPlanComplete);
        generatePlanBtn && (generatePlanBtn.disabled = true);
        updateButtonStates();
    }

    window.MAARS.plan = { init, generatePlan, stopPlanRun, resetPlanUI, updateButtonStates };
})();
