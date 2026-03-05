/**
 * MAARS app - main entry point, wires modules together.
 */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', () => {
        const cfg = window.MAARS?.config;
        const theme = window.MAARS?.theme;
        const task = window.MAARS?.task;
        const ws = window.MAARS?.ws;
        const research = window.MAARS?.research;

        if (theme) theme.initTheme().catch(() => {});
        const settings = window.MAARS?.settings;
        if (settings) settings.initSettingsModal();
        const sidebar = window.MAARS?.sidebar;
        if (sidebar) sidebar.initSidebar();
        if (task) task.init();
        if (research) research.init();
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

        // Home view is the default; research view loads via hash route.
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
