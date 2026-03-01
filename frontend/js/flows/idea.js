/**
 * MAARS Idea 流程 - Refine（Idea Agent 文献收集）。
 * 与 plan/task 统一：HTTP 仅触发，数据由 WebSocket idea-complete 回传。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
    if (!cfg || !api) return;

    const ideaInput = document.getElementById('ideaInput');
    const loadExampleIdeaBtn = document.getElementById('loadExampleIdeaBtn');
    const refineIdeaBtn = document.getElementById('refineIdeaBtn');
    const stopRefineBtn = document.getElementById('stopRefineBtn');

    let isRefining = false;

    function updateRefineState() {
        if (isRefining) return;
        const hasInput = (ideaInput?.value || '').trim().length > 0;
        if (refineIdeaBtn) refineIdeaBtn.disabled = !hasInput;
    }

    function onIdeaComplete(e) {
        const data = e.detail || {};
        if (data.ideaId) cfg.setCurrentIdeaId(data.ideaId);
        isRefining = false;
        if (stopRefineBtn) stopRefineBtn.style.display = 'none';
        updateRefineState();
    }

    function resetRefineUI(errorMsg) {
        const isStoppedByUser = (errorMsg || '').includes('stopped by user');
        if (errorMsg && !isStoppedByUser) {
            console.error('Refine error:', errorMsg);
            alert('Refine failed: ' + errorMsg);
        }
        isRefining = false;
        if (stopRefineBtn) stopRefineBtn.style.display = 'none';
        updateRefineState();
    }

    function stopRefine() {
        resetRefineUI(); /* 立即恢复按钮，不等待后端 */
        api.stopAgent('idea').catch(() => {});
    }

    async function runRefine() {
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
            isRefining = true;
            refineIdeaBtn.disabled = true;
            if (stopRefineBtn) stopRefineBtn.style.display = '';
            document.dispatchEvent(new CustomEvent('maars:idea-start'));
            await api.refineIdea(idea, 10);
        } catch (err) {
            resetRefineUI(err.message || 'Unknown error');
        }
    }

    document.addEventListener('maars:restore-complete', (e) => {
        const ideaText = (e.detail?.ideaText || '').trim();
        if (ideaText && ideaInput) ideaInput.value = ideaText;
        updateRefineState();
    });

    document.addEventListener('maars:idea-error', (e) => {
        resetRefineUI(e.detail?.error);
    });

    function init() {
        refineIdeaBtn?.addEventListener('click', runRefine);
        stopRefineBtn?.addEventListener('click', stopRefine);
        document.addEventListener('maars:idea-complete', onIdeaComplete);
        if (loadExampleIdeaBtn) {
            loadExampleIdeaBtn.addEventListener('click', () => {
                api.loadExampleIdea();
                updateRefineState();
            });
        }
        if (ideaInput) ideaInput.addEventListener('input', updateRefineState);
        refineIdeaBtn && (refineIdeaBtn.disabled = true);
    }

    window.MAARS.idea = { init, updateRefineState, resetRefineUI };
})();
