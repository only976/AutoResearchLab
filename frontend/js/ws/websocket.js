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
            const res = await fetch(`${cfg.API_BASE_URL}/execution/status?ideaId=${encodeURIComponent(ideaId)}&planId=${encodeURIComponent(planId)}`);
            const data = await res.json();
            if (!data.tasks?.length) return;
            document.dispatchEvent(new CustomEvent('maars:execution-sync', { detail: data }));
        } catch (_) {
            /* ignore sync errors */
        }
    }

    function init() {
        if (state.socket && state.socket.connected) return;
        state.socket = io(cfg.WS_URL, { reconnection: true, reconnectionAttempts: 10, reconnectionDelay: 1000 });

        state.socket.on('connect', () => {
            console.log('WebSocket connected');
            syncExecutionStateOnConnect();
        });
        state.socket.on('disconnect', () => console.log('WebSocket disconnected'));

        state.socket.on('plan-start', () => {});
        state.socket.on('idea-start', () => {});

        state.socket.on('idea-error', (data) => {
            document.dispatchEvent(new CustomEvent('maars:idea-error', { detail: { error: data?.error } }));
        });
        state.socket.on('idea-complete', (data) => {
            document.dispatchEvent(new CustomEvent('maars:idea-complete', { detail: data }));
        });

        window.MAARS?.wsHandlers?.thinking?.register(state.socket);

        state.socket.on('plan-tree-update', (data) => {
            document.dispatchEvent(new CustomEvent('maars:plan-tree-update', { detail: data }));
        });

        state.socket.on('plan-complete', (data) => {
            document.dispatchEvent(new CustomEvent('maars:plan-complete', { detail: data }));
        });

        state.socket.on('plan-error', () => {
            document.dispatchEvent(new CustomEvent('maars:plan-error'));
        });

        state.socket.on('execution-layout', (data) => {
            document.dispatchEvent(new CustomEvent('maars:execution-layout', { detail: data }));
        });

        state.socket.on('task-start', () => {});

        state.socket.on('task-states-update', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-states-update', { detail: data }));
        });

        state.socket.on('task-output', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-output', { detail: data }));
        });

        state.socket.on('task-error', (data) => {
            document.dispatchEvent(new CustomEvent('maars:task-error', { detail: data }));
        });

        state.socket.on('task-complete', (data) => {
            console.log(`Execution complete: ${data.completed}/${data.total} tasks completed`);
            document.dispatchEvent(new CustomEvent('maars:task-complete', { detail: data }));
        });
    }

    window.MAARS.ws = { init };
})();
