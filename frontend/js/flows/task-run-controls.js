/**
 * MAARS Task run-control helpers.
 * Handles start/stop/retry/resume interactions for execution flow.
 */
(function () {
    'use strict';
    const toast = window.MAARS.toast;

    function createTaskRunControlHelpers(deps) {
        const cfg = deps?.cfg;
        const api = deps?.api;
        const state = deps?.state;
        const executionBtn = deps?.executionBtn;
        const stopExecutionBtn = deps?.stopExecutionBtn;
        const clear = deps?.clear;

        function startExecutionUI() {
            if (executionBtn) {
                executionBtn.disabled = true;
                executionBtn.textContent = 'Executing...';
            }
            if (stopExecutionBtn) stopExecutionBtn.hidden = false;
        }

        function resetExecutionButtons() {
            if (executionBtn) {
                executionBtn.disabled = false;
                executionBtn.textContent = 'Execution';
            }
            if (stopExecutionBtn) stopExecutionBtn.hidden = true;
        }

        async function runExecution() {
            if (!executionBtn || !cfg || !api) return;
            const { ideaId, planId } = await cfg.resolvePlanIds();
            if (!ideaId || !planId) {
                toast.warning('Current research has no valid plan yet. Please finish Refine/Plan first.');
                return;
            }

            const btn = executionBtn;
            const originalText = btn.textContent;
            document.dispatchEvent(new CustomEvent('maars:task-start'));
            document.dispatchEvent(new CustomEvent('maars:switch-view', { detail: { view: 'execution' } }));
            startExecutionUI();

            try {
                let stream = window.MAARS?.state?.es;
                if (!stream || stream.readyState !== 1) {
                    stream = await window.MAARS.ws?.requireConnected?.();
                    if (!stream || stream.readyState !== 1) {
                        resetExecutionButtons();
                        return;
                    }
                }
                const response = await cfg.fetchWithSession(`${cfg.API_BASE_URL}/execution/run`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ideaId, planId }),
                });
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to start execution');
                }
                if (stopExecutionBtn) stopExecutionBtn.hidden = false;
            } catch (error) {
                console.error('Error in execution:', error);
                toast.error('Error: ' + error.message);
                btn.textContent = originalText;
                btn.disabled = false;
                if (stopExecutionBtn) stopExecutionBtn.hidden = true;
            }
        }

        function stopExecution() {
            resetExecutionButtons();
            api?.stopAgent?.('task').catch(() => {});
        }

        function onTaskError(e) {
            const data = e?.detail || {};
            if (data.__replayed === true) {
                return;
            }
            const isStoppedByUser = String(data.error || '').includes('stopped by user');
            const isRetryable = !!data.willRetry;
            const phase = String(data.phase || '').trim().toLowerCase();
            const taskId = String(data.taskId || '').trim();
            const phaseLabel = phase === 'validation' ? 'Validation failed' : 'Execution error';
            const prefix = taskId ? `[${taskId}] ${phaseLabel}` : phaseLabel;

            if (!isStoppedByUser) {
                if (isRetryable) {
                    console.warn(prefix + ' (auto-retrying):', data.error);
                } else {
                    console.error(prefix + ':', data.error);
                    toast.error(prefix + ': ' + (data.error || 'Unknown error'));
                }
            }
            if (!isRetryable) resetExecutionButtons();
        }

        function onTaskRetry(e) {
            const taskId = e?.detail?.taskId;
            if (!taskId || !api) return;
            api.retryTask(taskId).then(() => startExecutionUI()).catch((err) => {
                console.error('Retry failed:', err);
                toast.error('Failed: ' + (err.message || err));
            });
        }

        function onTaskResume(e) {
            const taskId = e?.detail?.taskId;
            if (!taskId || !api) return;
            api.resumeFromTask(taskId).then(() => startExecutionUI()).catch((err) => {
                console.error('Resume failed:', err);
                toast.error('Failed: ' + (err.message || err));
            });
        }

        function onExecutionStartClear() {
            clear?.();
        }

        function onExecutionSyncRunning(data) {
            state.executionRunning = !!data?.running;
        }

        return {
            runExecution,
            stopExecution,
            startExecutionUI,
            resetExecutionButtons,
            onTaskError,
            onTaskRetry,
            onTaskResume,
            onExecutionStartClear,
            onExecutionSyncRunning,
        };
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.createTaskRunControlHelpers = createTaskRunControlHelpers;
})();
