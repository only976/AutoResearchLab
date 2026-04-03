/**
 * Event bridge initialization extracted from research-large-helpers.
 */
(function () {
    'use strict';

    function initEventBridges(ctx) {
        if (!ctx) return;
        window.MAARS = window.MAARS || {};
        if (window.MAARS.__researchEventBridgesBound) return;
        window.MAARS.__researchEventBridgesBound = true;

        document.addEventListener('maars:idea-start', () => ctx.setStageStarted('refine', true));
        document.addEventListener('maars:plan-start', () => ctx.setStageStarted('plan', true));
        document.addEventListener('maars:task-start', () => {
            ctx.setStageStarted('execute', true);
            if (ctx.getActiveStage() === 'execute') {
                ctx.scheduleExecutionGraphRender({ force: true, delays: [0, 100, 320, 700] });
                ctx.renderExecuteStream();
            }
            ctx.refreshExecutionRuntimeStatus();
        });
        document.addEventListener('maars:paper-start', () => ctx.setStageStarted('paper', true));

        document.addEventListener('maars:research-stage', (e) => {
            const d = e?.detail || {};
            if (d.researchId && ctx.currentResearchId && d.researchId !== ctx.currentResearchId) return;
            const stage = String(d.stage || '').trim();
            const status = String(d.status || '').trim() || 'idle';
            const error = String(d.error || '').trim();
            if (!stage) return;

            const details = ctx.getStageStatusDetails();
            if (details?.[stage] != null) {
                if (status === 'running' || status === 'completed' || status === 'stopped' || status === 'failed') {
                    ctx.setStageStarted(stage, true);
                }
                ctx.setStageStatusDetails({
                    ...details,
                    [stage]: { status, message: error || status },
                });
                ctx.renderStageButtons(stage);
                if (status === 'running' || status === 'completed') {
                    ctx.setActiveStage(stage);
                }
            }
            document.dispatchEvent(new CustomEvent('maars:research-list-refresh'));
        });

        document.addEventListener('maars:research-list-refresh', () => {
            window.MAARS?.sidebar?.refreshResearchList?.();
        });

        document.addEventListener('maars:idea-complete', (e) => {
            const d = e?.detail || {};
            if (d.idea) ctx.stageData.originalIdea = String(d.idea || '').trim() || ctx.stageData.originalIdea;
            if (Array.isArray(d.papers)) ctx.stageData.papers = d.papers;
            if (typeof d.refined_idea === 'string') ctx.stageData.refined = d.refined_idea;
            ctx.stageData.refineThinking = '';
            ctx.renderRefinePanel();
        });

        document.addEventListener('maars:idea-thinking', (e) => {
            const d = e?.detail || {};
            const chunk = String(d.chunk || '').trim();
            const toolName = String(d?.scheduleInfo?.tool_name || '').trim();
            const turn = d?.scheduleInfo?.turn;
            const maxTurns = d?.scheduleInfo?.max_turns;
            const parts = [];
            if (toolName) parts.push(`Running tool: **${toolName}**`);
            if (Number.isFinite(turn) && Number.isFinite(maxTurns)) parts.push(`Turn ${turn}/${maxTurns}`);
            if (chunk) parts.push(chunk);
            if (!parts.length) return;
            ctx.stageData.refineThinking = parts.join('\n\n');
            if (!String(ctx.stageData.refined || '').trim()) ctx.renderRefinePanel();
        });

        document.addEventListener('maars:paper-complete', (e) => {
            const d = e?.detail || {};
            if (typeof d.content === 'string') ctx.stageData.paper = d.content;
            if (typeof d.format === 'string') ctx.stageData.paperFormat = d.format;
            if (typeof d.pdfUrl === 'string') ctx.stageData.pdfUrl = d.pdfUrl;
            ctx.renderPaperPanel();
        });

        document.addEventListener('maars:task-states-update', (e) => {
            const d = e?.detail || {};
            const tasks = Array.isArray(d.tasks) ? d.tasks : [];
            if (!tasks.length) return;
            tasks.forEach((t) => {
                if (!t?.task_id) return;
                const id = ctx.ensureTaskInOrder(t.task_id);
                ctx.upsertTaskMeta(t);
                if (!id) return;
                ctx.executeState.statuses.set(id, String(t.status || ''));
            });
            if (ctx.getActiveStage() === 'execute') {
                ctx.scheduleExecutionGraphRender();
                ctx.renderExecuteStream();
            }
        });

        document.addEventListener('maars:task-thinking', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            const chunk = String(d.chunk || '').trim();
            if (!taskId || !chunk) return;
            const attempt = Number(d.attempt || d?.scheduleInfo?.attempt) || ctx.getCurrentAttempt(taskId);
            const operation = String(d.operation || 'Execute').trim() || 'Execute';
            if (/^validate$/i.test(operation) || /^step-b$/i.test(operation)) return;

            ctx.ensureTaskInOrder(taskId);
            ctx.setCurrentAttempt(taskId, attempt);
            ctx.appendExecuteMessage({
                taskId,
                kind: 'assistant',
                title: `${taskId} · ${operation}`,
                body: chunk,
                attempt,
                status: ctx.executeState.statuses.get(taskId) || 'doing',
                dedupeKey: `thinking:${taskId}:${attempt}:${operation}:${chunk.slice(0, 120)}`,
            });
            if (ctx.getActiveStage() === 'execute') ctx.renderExecuteStream();
        });

        document.addEventListener('maars:task-started', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            if (!taskId) return;
            const attempt = Number(d.attempt) || ctx.getCurrentAttempt(taskId);
            ctx.ensureTaskInOrder(taskId);
            ctx.setCurrentAttempt(taskId, attempt);
            ctx.upsertTaskMeta({
                task_id: taskId,
                title: String(d.title || d.description || taskId).trim() || taskId,
                description: String(d.description || '').trim(),
                status: 'doing',
            });
            ctx.executeState.statuses.set(taskId, 'doing');
            const meta = ctx.getTaskMetaById(taskId) || {};
            ctx.appendExecuteMessage({
                taskId,
                kind: 'system',
                title: `${taskId} started · Attempt ${ctx.getCurrentAttempt(taskId)}`,
                body: meta.description || 'Task execution started',
                attempt: ctx.getCurrentAttempt(taskId),
                status: 'doing',
            });
            if (ctx.getActiveStage() === 'execute') {
                ctx.scheduleExecutionGraphRender();
                ctx.renderExecuteStream();
            }
        });

        document.addEventListener('maars:task-output', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            if (!taskId) return;
            const attempt = Number(d.attempt) || ctx.getCurrentAttempt(taskId);
            const outputText = ctx.stringifyOutput(d.output).trim();
            if (!outputText) return;
            ctx.ensureTaskInOrder(taskId);
            ctx.setCurrentAttempt(taskId, attempt);
            ctx.pushRecentOutput(taskId, outputText);
            const meta = ctx.getTaskMetaById(taskId) || {};
            ctx.appendExecuteMessage({
                taskId,
                kind: 'output',
                title: meta.title || taskId,
                body: outputText,
                attempt: ctx.getCurrentAttempt(taskId),
                status: ctx.executeState.statuses.get(taskId) || meta.status || '',
                dedupeKey: `output:${taskId}:${ctx.getCurrentAttempt(taskId)}:${outputText.slice(0, 120)}`,
            });
            if (ctx.getActiveStage() === 'execute') ctx.renderExecuteStream();
        });

        document.addEventListener('maars:task-completed', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            if (!taskId) return;
            const attempt = Number(d.attempt) || ctx.getCurrentAttempt(taskId);
            ctx.setCurrentAttempt(taskId, attempt);
            ctx.executeState.statuses.set(taskId, 'done');
            const meta = ctx.getTaskMetaById(taskId) || {};
            const validated = !d.validated;
            const body = validated
                ? ctx.buildValidationSummaryBody(taskId, d, meta, { statusLabel: 'PASS' })
                : 'Task completed successfully.';
            ctx.appendExecuteMessage({
                taskId,
                kind: 'system',
                title: `${taskId} ${validated ? 'validation summary' : 'completed'} · Attempt ${ctx.getCurrentAttempt(taskId)}`,
                body,
                attempt: ctx.getCurrentAttempt(taskId),
                status: 'done',
                dedupeKey: validated ? `validation-pass:${taskId}:${ctx.getCurrentAttempt(taskId)}` : '',
            });
            if (ctx.getActiveStage() === 'execute') {
                ctx.scheduleExecutionGraphRender();
                ctx.renderExecuteStream();
            }
        });

        document.addEventListener('maars:task-error', (e) => {
            const d = e?.detail || {};
            if (d.fatal === true) return;
            const taskId = String(d.taskId || d.task_id || '').trim();
            const errorText = String(d.error || '').trim();
            if (!taskId && !errorText) return;
            const phase = String(d.phase || '').trim();
            const attempt = Number(d.attempt) || ctx.getCurrentAttempt(taskId);
            const willRetry = d.willRetry === true;
            const messageAttempt = Number.isFinite(attempt) ? attempt : 1;
            if (taskId) ctx.setCurrentAttempt(taskId, messageAttempt);

            const meta = ctx.getTaskMetaById(taskId) || {};
            const terminalStatus = phase === 'validation' ? 'validation-failed' : 'execution-failed';
            const currentStatus = taskId ? (ctx.executeState.statuses.get(taskId) || '') : '';
            const nextStatus = willRetry ? (currentStatus || 'doing') : terminalStatus;
            const isValidationPhase = phase === 'validation';
            const body = isValidationPhase
                ? ctx.buildValidationSummaryBody(taskId, d, meta, { statusLabel: 'FAIL' })
                : (errorText || 'Unknown execution error.');

            ctx.appendExecuteMessage({
                taskId: taskId || '',
                kind: isValidationPhase ? 'error' : (willRetry ? 'system' : 'error'),
                title: isValidationPhase
                    ? `${meta.title || taskId || 'Task'} · Validation failed · Attempt ${messageAttempt}`
                    : `${meta.title || taskId || (willRetry ? 'Retrying Task' : 'Execution Error')} · Attempt ${messageAttempt}`,
                body,
                attempt: messageAttempt,
                status: taskId ? nextStatus : terminalStatus,
                dedupeKey: isValidationPhase ? `validation-fail:${taskId}:${messageAttempt}` : '',
            });
            if (taskId) ctx.executeState.statuses.set(taskId, nextStatus);
            if (ctx.getActiveStage() === 'execute') ctx.renderExecuteStream();
            ctx.refreshExecutionRuntimeStatus();
        });

        document.addEventListener('maars:attempt-retry', (e) => {
            const d = e?.detail || {};
            const taskId = String(d.taskId || d.task_id || '').trim();
            if (!taskId) return;
            const phase = String(d.phase || '').trim() || 'execution';
            const reason = String(d.reason || '').trim() || 'Retry requested';
            const attempt = Number(d.attempt);
            const nextAttempt = Number(d.nextAttempt);
            const failedAttempt = Number.isFinite(attempt) ? attempt : ctx.getCurrentAttempt(taskId);
            const upcomingAttempt = Number.isFinite(nextAttempt) ? nextAttempt : failedAttempt + 1;
            const validationSummary = d?.decision?.validationSummary || {};
            const directReasonRaw = String(validationSummary?.directReason || '').trim();
            const directReason = directReasonRaw || ctx.extractValidationDirectReason(reason);
            const body = phase === 'validation'
                ? `Direct reason: ${directReason}\n${reason}`
                : reason;

            ctx.appendExecuteMessage({
                taskId,
                kind: 'system',
                title: `${taskId} retrying · Attempt ${failedAttempt}`,
                body,
                attempt: failedAttempt,
                status: ctx.executeState.statuses.get(taskId) || 'execution-failed',
                dedupeKey: `retry:${taskId}:${phase}:${failedAttempt}:${upcomingAttempt}`,
            });
            ctx.setCurrentAttempt(taskId, upcomingAttempt);
            if (ctx.getActiveStage() === 'execute') ctx.renderExecuteStream();
        });

        document.addEventListener('maars:execution-sync', (e) => {
            const d = e?.detail || {};
            const tasks = Array.isArray(d.tasks) ? d.tasks : [];
            if (!tasks.length) return;
            tasks.forEach((task) => {
                ctx.upsertTaskMeta(task);
                const id = ctx.ensureTaskInOrder(task.task_id);
                if (!id) return;
                const nextStatus = String(task.status || '');
                if (nextStatus) ctx.executeState.statuses.set(id, nextStatus);
            });
            if (ctx.getActiveStage() === 'execute') {
                ctx.scheduleExecutionGraphRender();
                ctx.renderExecuteStream();
            }
            ctx.refreshExecutionRuntimeStatus();
        });

        document.addEventListener('maars:execution-layout', (e) => {
            const d = e?.detail || {};
            const treeData = Array.isArray(d?.layout?.treeData) ? d.layout.treeData : [];
            const graphLayout = d?.layout?.layout || null;
            if (!treeData.length || !graphLayout) return;
            ctx.setExecutionGraphPayload({ treeData, layout: graphLayout });
            ctx.invalidateExecutionGraphRender();
            treeData.forEach(ctx.upsertTaskMeta);
            if (ctx.getActiveStage() === 'execute') {
                ctx.scheduleExecutionGraphRender({ force: true, delays: [0, 100, 320, 700] });
                ctx.renderExecuteStream();
            }
        });

        document.addEventListener('maars:execution-runtime-status', (e) => {
            ctx.renderExecutionRuntimeStatus(e?.detail || {});
        });

        window.addEventListener('pageshow', () => {
            ctx.scheduleExecutionGraphRender({ force: true, allowInactive: true, delays: [0, 120, 360, 900] });
        });
        window.addEventListener('resize', () => {
            if (ctx.getActiveStage() !== 'execute') return;
            ctx.scheduleExecutionGraphRender({ force: true, delays: [0, 120] });
        });
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState !== 'visible') return;
            ctx.scheduleExecutionGraphRender({
                force: true,
                allowInactive: ctx.getActiveStage() !== 'execute',
                delays: [0, 120, 360],
            });
        });
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.researchEventBridges = { initEventBridges };
})();
