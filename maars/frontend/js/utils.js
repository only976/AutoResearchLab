/**
 * MAARS utils - shared utilities (escapeHtml, escapeHtmlAttr).
 * Load before modules that need HTML escaping.
 */
(function () {
    'use strict';
    window.MAARS = window.MAARS || {};

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function escapeHtmlAttr(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    window.MAARS.utils = { escapeHtml, escapeHtmlAttr };
})();
