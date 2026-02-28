/**
 * MAARS app - main entry point, wires modules together.
 */
(function () {
    'use strict';

    function init() {
        const cfg = window.MAARS?.config;
        const theme = window.MAARS?.theme;
        const plan = window.MAARS?.plan;
        const views = window.MAARS?.views;
        const ws = window.MAARS?.ws;

        if (theme) {
            theme.initTheme().catch(() => {});
            theme.initSettingsModal();
        }
        if (cfg && cfg.resolvePlanId) cfg.resolvePlanId().catch(() => {});
        if (plan) plan.init();
        if (views) views.init();
        if (ws) ws.init();

        const taskTree = window.MAARS?.taskTree;
        if (taskTree?.initClickHandlers) taskTree.initClickHandlers();

        initTreeViewTabs();

        (async () => {
            const api = window.MAARS?.api;
            if (!api?.restoreRecentPlan) return;
            try {
                await api.restoreRecentPlan();
            } catch (_) {
                /* 无 plan 时静默忽略 */
            }
        })();
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.app = window.MAARS.app || {};
    window.MAARS.app.init = init;

    // In this Next.js integration, scripts are injected after DOMContentLoaded.
    // If the DOM is already ready, init immediately.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }

    function initTreeViewTabs() {
        const tabs = document.querySelectorAll('.tree-view-tab');
        const panels = document.querySelectorAll('.tree-view-panel');
        tabs.forEach((tab) => {
            tab.addEventListener('click', () => {
                const view = tab.getAttribute('data-view');
                tabs.forEach((t) => {
                    t.classList.toggle('active', t === tab);
                    t.setAttribute('aria-pressed', t === tab ? 'true' : 'false');
                });
                panels.forEach((p) => {
                    const match = p.getAttribute('data-view-panel') === view;
                    p.classList.toggle('active', match);
                });
            });
        });
    }
})();
