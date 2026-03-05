/*
 * Frontend log capture -> backend /api/log/frontend.
 * Keeps UX unchanged; best-effort only.
 */
(function () {
    'use strict';

    const cfg = window.MAARS && window.MAARS.config;
    if (!cfg || !cfg.API_BASE_URL || !cfg.fetchWithSession) return;

    const endpoint = `${cfg.API_BASE_URL}/log/frontend`;
    const buffer = [];
    let flushing = false;

    function toMessage(args) {
        try {
            return (args || []).map((a) => {
                if (typeof a === 'string') return a;
                if (a instanceof Error) return a.stack || a.message || String(a);
                try { return JSON.stringify(a); } catch (_) { return String(a); }
            }).join(' ');
        } catch (_) {
            return '';
        }
    }

    function enqueue(level, args, context) {
        const message = toMessage(args);
        if (!message) return;
        buffer.push({
            level: String(level || 'info'),
            message,
            ts: Date.now() / 1000,
            url: (typeof location !== 'undefined' && location.href) ? location.href : '',
            context: context || {},
        });
        if (buffer.length >= 10) flush();
    }

    async function flush() {
        if (flushing || buffer.length === 0) return;
        flushing = true;
        const entries = buffer.splice(0, buffer.length);
        try {
            await cfg.fetchWithSession(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entries }),
                keepalive: true,
            });
        } catch (_) {
            // best-effort
        } finally {
            flushing = false;
        }
    }

    const original = {
        log: console.log ? console.log.bind(console) : null,
        info: console.info ? console.info.bind(console) : null,
        warn: console.warn ? console.warn.bind(console) : null,
        error: console.error ? console.error.bind(console) : null,
        debug: console.debug ? console.debug.bind(console) : null,
    };

    ['log', 'info', 'warn', 'error', 'debug'].forEach((level) => {
        const orig = original[level];
        if (!orig) return;
        console[level] = function (...args) {
            enqueue(level, args);
            return orig(...args);
        };
    });

    window.addEventListener('error', (ev) => {
        enqueue('error', [ev.message], { filename: ev.filename, lineno: ev.lineno, colno: ev.colno });
        flush();
    });

    window.addEventListener('unhandledrejection', (ev) => {
        enqueue('error', ['UnhandledRejection', ev.reason], {});
        flush();
    });

    setInterval(flush, 2000);

    window.MAARS = window.MAARS || {};
    window.MAARS.frontendLogger = { flush };
})();
