/**
 * MAARS Paper 流程 - 生成论文草稿（第四个 Agent，LLM 管道）。
 * 与 idea/plan/task 统一：HTTP 仅触发，数据由 WebSocket paper-complete 回传。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    const api = window.MAARS?.api;
    if (!cfg || !api) return;
    const toast = window.MAARS.toast;

    const generatePaperBtn = document.getElementById('generatePaperBtn');
    const stopPaperBtn = document.getElementById('stopPaperBtn');

    let isGenerating = false;

    function resetPaperUI(errorMsg) {
        const isStoppedByUser = (errorMsg || '').includes('stopped by user');
        if (errorMsg && !isStoppedByUser) {
            console.error('Paper error:', errorMsg);
            toast.error('Paper generation failed: ' + errorMsg);
        }
        isGenerating = false;
        if (stopPaperBtn) stopPaperBtn.hidden = true;
        if (generatePaperBtn) generatePaperBtn.disabled = false;
    }

    function stopPaper() {
        resetPaperUI();
        api.stopAgent('paper').catch(() => {});
    }

    async function runGeneratePaper() {
        const socket = await window.MAARS.ws?.requireConnected?.();
        if (!socket) return;
        try {
            const { ideaId, planId } = await cfg.resolvePlanIds();
            if (!ideaId || !planId) {
                toast.warning('Please Refine and Plan first.');
                return;
            }
            
            isGenerating = true;
            generatePaperBtn.disabled = true;
            if (stopPaperBtn) stopPaperBtn.hidden = false;
            document.dispatchEvent(new CustomEvent('maars:paper-start'));
            document.dispatchEvent(new CustomEvent('maars:switch-view', { detail: { view: 'output' } }));
            const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/paper/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ideaId, planId, format: 'latex' }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to start paper generation');
        } catch (err) {
            resetPaperUI(err.message || 'Unknown error');
        }
    }

    function onPaperComplete(e) {
        isGenerating = false;
        if (stopPaperBtn) stopPaperBtn.hidden = true;
        if (generatePaperBtn) generatePaperBtn.disabled = false;
    }

    function init() {
        generatePaperBtn?.addEventListener('click', runGeneratePaper);
        stopPaperBtn?.addEventListener('click', stopPaper);
        document.addEventListener('maars:paper-complete', onPaperComplete);
        document.addEventListener('maars:paper-error', (e) => {
            resetPaperUI(e.detail?.error);
        });
    }

    window.MAARS.paper = { init, resetPaperUI };
})();
