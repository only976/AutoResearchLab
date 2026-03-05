/**
 * MAARS app - main entry point, wires modules together.
 */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', () => {
        const cfg = window.MAARS?.config;
        const theme = window.MAARS?.theme;
        const idea = window.MAARS?.idea;
        const plan = window.MAARS?.plan;
        const task = window.MAARS?.task;
        const paper = window.MAARS?.paper;
        const ws = window.MAARS?.ws;

        if (theme) theme.initTheme().catch(() => {});
        const settings = window.MAARS?.settings;
        if (settings) settings.initSettingsModal();
        const sidebar = window.MAARS?.sidebar;
        if (sidebar) sidebar.initSidebar();
        if (cfg && cfg.resolvePlanId) cfg.resolvePlanId().catch(() => {});
        if (idea) idea.init();
        if (plan) plan.init();
        if (task) task.init();
        if (paper) paper.init();
        (async () => {
            try {
                if (cfg?.ensureSession) await cfg.ensureSession();
                if (ws) await ws.init();
            } catch (_) {
                /* ignore bootstrap failures */
            }
        })();

        const taskTree = window.MAARS?.taskTree;
        if (taskTree?.initClickHandlers) taskTree.initClickHandlers();

        initTreeViewTabs();

        (async () => {
            const api = window.MAARS?.api;
            if (!api?.restoreRecentPlan) return;
            try {
                await api.restoreRecentPlan();
                /* restore 流程由 api 派发 maars:restore-complete，各模块自行监听并恢复 UI */
            } catch (_) {
                /* 无 plan 时静默忽略 */
            }
        })();
    });

    function initTreeViewTabs() {
        const tabs = document.querySelectorAll('.tree-view-tab');
        const panels = document.querySelectorAll('.tree-view-panel');

        function switchToView(view) {
            const tab = Array.from(tabs).find((t) => t.getAttribute('data-view') === view);
            if (tab) tab.click();
        }

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

        document.addEventListener('maars:switch-to-output-tab', () => switchToView('output'));
        document.addEventListener('maars:switch-view', (e) => {
            if (e.detail?.view) switchToView(e.detail.view);
        });
    }
})();
