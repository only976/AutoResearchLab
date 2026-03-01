/**
 * MAARS theme - 主题切换（light / dark / black）。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    if (!cfg) return;

    async function initTheme() {
        try {
            const raw = await cfg.fetchSettings();
            const theme = raw.theme && cfg.THEMES.includes(raw.theme) ? raw.theme : 'black';
            applyTheme(theme);
        } catch (_) {
            applyTheme('black');
        }
    }

    function applyTheme(theme) {
        if (theme === 'light') {
            document.documentElement.removeAttribute('data-theme');
        } else {
            document.documentElement.setAttribute('data-theme', theme);
        }
    }

    window.MAARS.theme = { initTheme, applyTheme };
})();
