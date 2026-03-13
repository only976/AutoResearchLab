/**
 * MAARS WebSocket - Thinking 事件处理器。
 * 按事件前缀（plan/idea/task）确定样式，流式写入 thinking 区域。
 */
(function () {
    'use strict';

    const EVENTS = ['plan-thinking', 'idea-thinking', 'task-thinking', 'paper-thinking'];

    /** 从事件名推导 source，用于 thinking 区域样式区分 */
    function sourceFromEvent(eventName) {
        const prefix = eventName.split('-')[0];
        return prefix || 'thinking';
    }

    /**
     * 注册 thinking 相关 realtime 事件。
     * @param {object} transport - Socket.io 实例 (on) 或 EventSource (addEventListener)
     */
    function register(transport) {
        if (!transport) return;
        const thinking = window.MAARS?.thinking;
        if (!thinking?.appendChunk) return;

        EVENTS.forEach((eventName) => {
            if (typeof transport.on === 'function') {
                transport.on(eventName, (data) => {
                    const source = (data && data.source) || sourceFromEvent(eventName);
                    thinking.appendChunk(
                        (data && data.chunk) || '',
                        data && data.taskId,
                        data && data.operation,
                        data && data.scheduleInfo,
                        source
                    );
                });
            } else if (typeof transport.addEventListener === 'function') {
                transport.addEventListener(eventName, (e) => {
                    let data = null;
                    try { data = e?.data ? JSON.parse(e.data) : null; } catch (_) { data = null; }
                    const source = (data && data.source) || sourceFromEvent(eventName);
                    try {
                        document.dispatchEvent(new CustomEvent(`maars:${eventName}`, { detail: data || {} }));
                    } catch (_) {}
                    thinking.appendChunk(
                        (data && data.chunk) || '',
                        data && data.taskId,
                        data && data.operation,
                        data && data.scheduleInfo,
                        source
                    );
                });
            }
        });
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.wsHandlers = window.MAARS.wsHandlers || {};
    window.MAARS.wsHandlers.thinking = { register };
})();
