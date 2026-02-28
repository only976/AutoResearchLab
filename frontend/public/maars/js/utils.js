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

    function _cleanTextForMessage(text) {
        if (!text) return '';
        let t = String(text).trim();
        if (!t) return '';
        // If it's HTML, strip tags.
        if (t.includes('<') && t.includes('>')) {
            t = t.replace(/<[^>]*>/g, ' ');
        }
        // Collapse whitespace.
        t = t.replace(/\s+/g, ' ').trim();
        return t;
    }

    async function readErrorMessage(response, fallbackMessage) {
        const fallback = fallbackMessage || 'Request failed';
        if (!response) return fallback;

        let bodyText = '';
        try {
            bodyText = await response.text();
        } catch (_) {
            bodyText = '';
        }

        // Try JSON first (common: {error: ...}).
        if (bodyText) {
            try {
                const obj = JSON.parse(bodyText);
                const msg = obj?.error || obj?.message;
                if (msg) return `${msg} (HTTP ${response.status})`;
            } catch (_) {
                // fall through to plain text handling
            }
        }

        const cleaned = _cleanTextForMessage(bodyText);
        const msg = cleaned || response.statusText || fallback;
        return `${msg} (HTTP ${response.status})`;
    }

    window.MAARS.utils = { escapeHtml, escapeHtmlAttr, readErrorMessage };
})();
