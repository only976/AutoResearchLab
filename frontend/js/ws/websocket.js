/**
 * MAARS WebSocket - Socket.io 连接，仅转发后端事件为前端 maars:* 事件。
 * 各模块自行监听事件处理，websocket 不直接调用业务模块。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    if (!cfg) return;

    const state = window.MAARS.state || {};
    state.socket = state.socket ?? null;
    window.MAARS.state = state;

    async function syncExecutionStateOnConnect() {
        if (!cfg?.resolvePlanIds) return;
        try {
            const { ideaId, planId } = await cfg.resolvePlanIds();
            if (!ideaId || !planId) return;
            const res = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution/status?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`);
            const data = await res.json();
            if (!data.tasks?.length) return;
            document.dispatchEvent(new CustomEvent('maars:execution-sync', { detail: data }));
        } catch (_) {
            /* ignore sync errors */
        }
    }

    function bindSseEvents(es) {
        if (!es) return;

        es.addEventListener('open', () => {
            console.log('SSE connected');
            syncExecutionStateOnConnect();
        });
        es.addEventListener('error', (err) => {
            console.warn('SSE error:', err);
        });

        function onJsonEvent(name, handler) {
            es.addEventListener(name, (e) => {
                try {
                    const data = e?.data ? JSON.parse(e.data) : null;
                    handler(data);
                } catch (_) {
                    handler(null);
                }
            });
        }

        onJsonEvent('idea-error', (data) => {
            document.dispatchEvent(new CustomEvent('maars:idea-error', { detail: { error: data?.error } }));
        });
        onJsonEvent('idea-complete', (data) => {
            document.dispatchEvent(new CustomEvent('maars:idea-complete', { detail: data || {} }));
        });

        window.MAARS?.wsHandlers?.thinking?.register(es);

        onJsonEvent('plan-tree-update', (data) => {
            document.dispatchEvent(new CustomEvent('maars:plan-tree-update', { detail: data || {} }));
        });
        onJsonEvent('plan-complete', (data) => {
            document.dispatchEvent(new CustomEvent('maars:plan-complete', { detail: data || {} }));
        });
        onJsonEvent('plan-error', (data) => {
            document.dispatchEvent(new CustomEvent('maars:plan-error', { detail: { error: data?.error } }));
        });

        onJsonEvent('paper-complete', (data) => {
            document.dispatchEvent(new CustomEvent('maars:paper-complete', { detail: data || {} }));
        });
        onJsonEvent('paper-error', (data) => {
            document.dispatchEvent(new CustomEvent('maars:paper-error', { detail: { error: data?.error } }));
        });

        onJsonEvent('research-stage', (data) => {
            document.dispatchEvent(new CustomEvent('maars:research-stage', { detail: data || {} }));
        });
        onJsonEvent('research-error', (data) => {
            document.dispatchEvent(new CustomEvent('maars:research-error', { detail: { error: data?.error, researchId: data?.researchId } }));
        });

        onJsonEvent('execution-layout', (data) => {
            document.dispatchEvent(new CustomEvent('maars:execution-layout', { detail: data || {} }));
        });

        onJsonEvent('execution-runtime-status', (data) => {
            document.dispatchEvent(new CustomEvent('maars:execution-runtime-status', { detail: data || {} }));
        });

        onJsonEvent('task-states-update', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-states-update', { detail: data || {} }));
        });
        onJsonEvent('task-output', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-output', { detail: data || {} }));
        });
        onJsonEvent('task-error', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-error', { detail: data || {} }));
        });
        onJsonEvent('task-retry', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-retry', { detail: data || {} }));
        });
        onJsonEvent('task-started', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-started', { detail: data || {} }));
        });
        onJsonEvent('task-completed', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-completed', { detail: data || {} }));
        });
        onJsonEvent('task-complete', (data) => {
            if (data?.completed != null && data?.total != null) {
                console.log(`Execution complete: ${data.completed}/${data.total} tasks completed`);
            }
            document.dispatchEvent(new CustomEvent('maars:task-complete', { detail: data || {} }));
        });
    }

    async function init() {
        if (state.socket) {
            // legacy: keep slot name but store EventSource
            try { state.socket.close?.(); } catch (_) {}
            state.socket = null;
        }
        if (state.es && state.es.readyState === 1) return;
        if (typeof EventSource !== 'function') {
            console.warn('EventSource not available in this browser.');
            return;
        }
        let creds = await cfg.ensureSession?.();
        // Validate cached credentials using an auth-protected endpoint.
        try {
            let probe = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/session/verify`, { cache: 'no-store' });
            if (probe && probe.status === 401) {
                creds = await cfg.ensureSession?.(true);
                probe = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/session/verify`, { cache: 'no-store' });
            }
        } catch (_) {
            /* ignore probe errors */
        }
        const sid = creds?.sessionId || cfg.getSessionId?.();
        const token = creds?.sessionToken || cfg.getSessionToken?.();
        const url = `${cfg.API_BASE_URL}/events/stream?sessionId=${encodeURIComponent(sid || '')}&sessionToken=${encodeURIComponent(token || '')}`;
        console.log('Connecting SSE:', url);
        state.es = new EventSource(url);
        // One-shot auto refresh if credentials were stale.
        let refreshed = false;
        state.es.addEventListener('error', async () => {
            if (refreshed) return;
            refreshed = true;
            try { state.es.close(); } catch (_) {}
            try {
                await cfg.ensureSession?.(true);
            } catch (_) {
                return;
            }
            // Re-init once with fresh credentials
            try {
                await init();
            } catch (_) {
                /* ignore */
            }
        });
        bindSseEvents(state.es);
    }

    async function ensureConnected(timeoutMs = 4000) {
        if (state.es && state.es.readyState === 1) return state.es;
        await init();
        const startedAt = Date.now();
        while (Date.now() - startedAt < timeoutMs) {
            if (state.es && state.es.readyState === 1) return state.es;
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
        return state.es;
    }

    async function requireConnected(timeoutMs = 4000) {
        const socket = await ensureConnected(timeoutMs);
        if (socket && socket.readyState === 1) return socket;
        alert('Realtime stream not connected. Please wait and try again.');
        return null;
    }

    window.MAARS.ws = { init, ensureConnected, requireConnected };
})();
