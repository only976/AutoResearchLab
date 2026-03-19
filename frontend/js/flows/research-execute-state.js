/**
 * Execution message/state management functions extracted from research-large-helpers.
 */
(function () {
    'use strict';

    // Reuse helpers from research-execute-render.js (loaded first)
    const {
        _isExecuteStreamNearBottom,
        _scrollExecuteStreamToLatest,
        _updateExecuteJumpLatestButton,
        _formatElapsedDuration,
        _hasActiveExecuteBubble,
        _syncExecuteElapsedTicker,
        _getAttemptKey,
        _getCurrentAttempt,
        _getAttemptStatus,
        _getAttemptSummary,
    } = (window.MAARS && window.MAARS.researchExecuteRender && window.MAARS.researchExecuteRender._helpers) || {};

    function _setCurrentAttempt(ctx, taskId, attempt) {
        const id = String(taskId || '').trim();
        const n = Number(attempt);
        if (!id || !Number.isFinite(n) || n < 1) return;
        const current = _getCurrentAttempt(ctx, id);
        const next = Math.max(current, n);
        ctx.executeState.currentAttemptByTask.set(id, next);
        const key = _getAttemptKey(ctx, id, next);
        if (!ctx.executeState.attemptExpandedById.has(key)) {
            ctx.executeState.attemptExpandedById.set(key, true);
        }
    }

    function appendExecuteMessage(ctx, message) {
        if (!message || !message.taskId && message.kind !== 'system') return;
        const taskId = String(message.taskId || '').trim();
        let attempt = Number(message.attempt);
        if (taskId) {
            if (!Number.isFinite(attempt) || attempt < 1) {
                attempt = Number(ctx.executeState.currentAttemptByTask.get(taskId));
            }
            if (!Number.isFinite(attempt) || attempt < 1) attempt = 1;
            ctx.executeState.currentAttemptByTask.set(taskId, attempt);
            if (!ctx.executeState.attemptExpandedById.has(`${taskId}:${attempt}`)) {
                ctx.executeState.attemptExpandedById.set(`${taskId}:${attempt}`, true);
            }
        }
        const dedupeKey = String(message.dedupeKey || '').trim();
        if (dedupeKey) {
            const exists = ctx.executeState.messages.some((m) => m.dedupeKey === dedupeKey);
            if (exists) return;
        }
        ctx.executeState.messages.push({
            id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            at: Date.now(),
            ...message,
            startedAt: Number(message?.startedAt) || Date.now(),
            attempt: taskId ? attempt : undefined,
        });
        if (ctx.executeState.messages.length > ctx.EXECUTE_TIMELINE_MAX_MESSAGES) {
            ctx.executeState.messages = ctx.executeState.messages.slice(-ctx.EXECUTE_TIMELINE_MAX_MESSAGES);
        }
    }

    function upsertExecuteThinkingMessage(ctx, taskId, operation, body, scheduleInfo, attemptHint) {
        const id = String(taskId || '').trim();
        if (!id) return;
        const op = String(operation || 'Execute').trim() || 'Execute';
        const text = String(body || '').trim();
        if (!text) return;
        const hintedAttempt = Number(attemptHint || scheduleInfo?.attempt) || 0;
        const currentAttempt = Math.max(_getCurrentAttempt(ctx, id), hintedAttempt, 1);

        const turn = Number(scheduleInfo?.turn);
        const maxTurns = Number(scheduleInfo?.max_turns);
        const toolName = String(scheduleInfo?.tool_name || '').trim();
        const tokenUsage = scheduleInfo?.token_usage || {};
        const totalTokens = Number(tokenUsage?.total);
        const deltaTokens = Number(tokenUsage?.deltaTotal);
        const inputTokens = Number(tokenUsage?.input);
        const outputTokens = Number(tokenUsage?.output);
        const contextTokens = Number(tokenUsage?.contextInputEst);

        let title = `${id} · ${op}`;
        if (toolName) title += ` · ${toolName}`;

        let tokenMetaText = '';
        if (Number.isFinite(inputTokens) && Number.isFinite(outputTokens) && (inputTokens > 0 || outputTokens > 0)) {
            const tokenBits = [`in ${inputTokens || 0}`, `out ${outputTokens || 0}`];
            if (Number.isFinite(deltaTokens) && deltaTokens > 0) tokenBits.push(`Δ ${deltaTokens}`);
            if (Number.isFinite(totalTokens) && totalTokens > 0) tokenBits.push(`total ${totalTokens}`);
            tokenMetaText = tokenBits.join(' · ');
        } else if (Number.isFinite(contextTokens) && contextTokens > 0) {
            tokenMetaText = `ctx ~${contextTokens}`;
        }

        const bodyText = Number.isFinite(turn) && Number.isFinite(maxTurns)
            ? `[${turn}/${maxTurns}] ${text}`
            : text;
        const dedupeKey = Number.isFinite(turn)
            ? `thinking:${id}:${currentAttempt}:${op}:${toolName}:${turn}:${bodyText.slice(0, 240)}`
            : '';

        const last = ctx.executeState.messages[ctx.executeState.messages.length - 1];
        if (
            last
            && last.taskId === id
            && Number(last.attempt || 1) === currentAttempt
            && last.kind === 'assistant'
            && String(last.title || '') === title
            && String(last.tokenMetaText || '') === tokenMetaText
        ) {
            const previous = String(last.body || '').trim();
            if (previous && previous !== bodyText) {
                const merged = `${previous}\n${bodyText}`;
                last.body = merged.length > 12000 ? merged.slice(-12000) : merged;
            } else if (!previous) {
                last.body = bodyText;
            } else {
                const nextRepeat = Number(last.repeatCount || 1) + 1;
                last.repeatCount = nextRepeat;
            }
            last.at = Date.now();
            return;
        }

        appendExecuteMessage(ctx, {
            taskId: id,
            kind: 'assistant',
            title,
            body: bodyText,
            tokenMetaText,
            status: ctx.executeState.statuses.get(id) || 'doing',
            attempt: currentAttempt,
            dedupeKey,
            repeatCount: 1,
            startedAt: Date.now(),
        });
    }

    function seedExecutionState(ctx, treeData, execution, outputs, options = {}) {
        ctx.executeState.order = [];
        ctx.executeState.statuses = new Map();
        ctx.executeState.latestStepBByTask = new Map();
        ctx.executeState.recentOutputsByTask = new Map();
        ctx.executeState.taskMetaById = new Map();
        ctx.executeState.messages = [];
        ctx.executeState.taskExpandedById = new Map();
        ctx.executeState.currentAttemptByTask = new Map();
        ctx.executeState.attemptExpandedById = new Map();

        const treeTasks = Array.isArray(treeData) ? treeData : [];
        const execTasks = Array.isArray(execution?.tasks) ? execution.tasks : [];
        treeTasks.forEach(ctx.upsertTaskMeta);
        execTasks.forEach((task) => {
            ctx.upsertTaskMeta(task);
            if (task?.status) ctx.executeState.statuses.set(task.task_id, String(task.status));
            _setCurrentAttempt(ctx, task.task_id, 1);
        });

        const skipOutputSeed = options?.skipOutputSeed === true;
        const outputMap = outputs && typeof outputs === 'object' ? outputs : {};
        if (!skipOutputSeed) {
            Object.entries(outputMap).forEach(([taskId, output]) => {
                const text = ctx.stringifyOutput(output).trim();
                if (!text) return;
                ctx.ensureTaskInOrder(taskId);
                ctx.pushRecentOutput(taskId, text);
            });
        }

        appendExecuteMessage(ctx, {
            kind: 'system',
            title: 'Execution timeline ready',
            body: execTasks.length ? `Loaded ${execTasks.length} execution steps.` : 'Waiting for execution to start.',
            dedupeKey: `seed:${ctx.getCurrentResearchId() || ''}`,
        });

        ctx.executeState.order.forEach((taskId) => {
            const meta = ctx.getTaskMetaById(taskId) || {};
            const status = ctx.executeState.statuses.get(taskId) || meta.status || 'undone';
            if (!skipOutputSeed) {
                const outputsForTask = ctx.executeState.recentOutputsByTask.get(taskId) || [];
                if (outputsForTask.length) {
                    appendExecuteMessage(ctx, {
                        taskId,
                        kind: status === 'execution-failed' || status === 'validation-failed' ? 'error' : 'output',
                        title: meta.title || taskId,
                        body: outputsForTask[outputsForTask.length - 1],
                        status,
                        dedupeKey: `seed-output:${taskId}`,
                    });
                }
            }
        });
    }

    function resetExecuteTimelineForNewRun(ctx) {
        ctx.executeState.messages = [];
        ctx.executeState.latestStepBByTask = new Map();
        ctx.executeState.recentOutputsByTask = new Map();
        ctx.executeState.currentAttemptByTask = new Map();
        ctx.executeState.attemptExpandedById = new Map();
        ctx.setExecuteAutoFollow(true);
        ctx.executeState.order.forEach((taskId) => {
            _setCurrentAttempt(ctx, taskId, 1);
        });
        _updateExecuteJumpLatestButton(ctx);
        _syncExecuteElapsedTicker(ctx);
    }

    function renderExecuteStream(ctx) {
        const render = window.MAARS?.researchExecuteRender?.renderExecuteStream;
        if (typeof render === 'function') {
            render(ctx);
        }
    }

    function initExecuteStreamControls(ctx) {
        const initControls = window.MAARS?.researchExecuteRender?.initExecuteStreamControls;
        if (typeof initControls === 'function') {
            initControls(ctx);
        }
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.researchExecuteState = {
        appendExecuteMessage,
        upsertExecuteThinkingMessage,
        seedExecutionState,
        resetExecuteTimelineForNewRun,
        renderExecuteStream,
        initExecuteStreamControls,
    };
})();
