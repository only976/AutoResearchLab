/**
 * MAARS Output 区域 - Agent 最终产出展示（idea 文献、task artifact）。
 * 与 region-responsibilities 中 Output 区域对应。
 */
(function () {
    'use strict';

    const escapeHtml = window.MAARS?.utils?.escapeHtml || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));
    const escapeHtmlAttr = window.MAARS?.utils?.escapeHtmlAttr || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));
    const outputUtils = window.MAARS?.outputUtils || {};

    const state = window.MAARS.state || {};
    state.taskOutputs = state.taskOutputs || {};
    state.outputUserScrolled = state.outputUserScrolled ?? false;
    state.outputBlockUserScrolled = state.outputBlockUserScrolled || {};
    state.outputLastUpdatedKey = state.outputLastUpdatedKey || '';
    window.MAARS.state = state;

    /** Refine 结果格式化（由 output 负责展示逻辑） */
    function formatRefineResult(data) {
        if (typeof outputUtils.formatRefineResult === 'function') {
            return outputUtils.formatRefineResult(data);
        }
        return '';
    }

    function _sortOutputKeys(outputs) {
        if (typeof outputUtils.sortOutputKeys === 'function') return outputUtils.sortOutputKeys(outputs);
        return Object.keys(outputs || {}).sort();
    }

    function _renderOutputContent(raw) {
        if (typeof outputUtils.renderContent === 'function') {
            return outputUtils.renderContent(raw, (typeof marked !== 'undefined' ? marked : undefined));
        }
        return { displayLabel: '', html: String(raw || '') };
    }

    function _normalizeOutputLabel(taskId, renderedLabel) {
        if (typeof outputUtils.normalizeLabel === 'function') {
            return outputUtils.normalizeLabel(taskId, renderedLabel);
        }
        return renderedLabel || String(taskId || '');
    }
    function renderOutput() {
        const el = document.getElementById('taskAgentOutputContent');
        const area = document.getElementById('taskAgentOutputArea');
        if (!el || !area) return;
        const outputs = state.taskOutputs;
        const keys = _sortOutputKeys(outputs);
        const wasNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        const savedScrollTops = {};
        el.querySelectorAll('.task-agent-output-block').forEach((blockEl) => {
            const key = blockEl.getAttribute('data-task-id') || '';
            const body = blockEl.querySelector('.task-agent-output-block-body');
            if (body) savedScrollTops[key] = body.scrollTop;
        });
        if (keys.length === 0) {
            el.innerHTML = '';
            return;
        }
        let html = '';
        for (const taskId of keys) {
            const raw = outputs[taskId];
            const rendered = _renderOutputContent(raw);
            let content = rendered.html || '';
            const displayLabel = _normalizeOutputLabel(taskId, rendered.displayLabel);
            if (content && typeof DOMPurify !== 'undefined') content = DOMPurify.sanitize(content);
            html += `<div class="task-agent-output-block" data-task-id="${escapeHtml(taskId || '')}" data-label="${escapeHtmlAttr(displayLabel || '')}"><div class="task-agent-output-block-header">${escapeHtml(displayLabel)}<button type="button" class="task-agent-output-block-expand" aria-label="Expand" title="Expand">⤢</button></div><div class="task-agent-output-block-body">${content}</div></div>`;
        }
        try {
            el.innerHTML = html || '';
            if (typeof hljs !== 'undefined') {
                requestIdleCallback(() => {
                    el.querySelectorAll('pre code').forEach((node) => { try { hljs.highlightElement(node); } catch (_) {} });
                }, { timeout: 100 });
            }
        } catch (_) {
            el.textContent = keys.map((k) => `Task ${k}: ${outputs[k]}`).join('\n\n');
        }
        if (!state.outputUserScrolled && wasNearBottom) {
            requestAnimationFrame(() => { requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; }); });
        }
        state.outputBlockUserScrolled = state.outputBlockUserScrolled || {};
        const lastKey = state.outputLastUpdatedKey || '';
        el.querySelectorAll('.task-agent-output-block').forEach((blockEl) => {
            const key = blockEl.getAttribute('data-task-id') || '';
            const body = blockEl.querySelector('.task-agent-output-block-body');
            if (!body) return;
            const shouldAutoScroll = key === lastKey && !state.outputBlockUserScrolled[key];
            if (shouldAutoScroll) requestAnimationFrame(() => { body.scrollTop = body.scrollHeight; });
            else if (savedScrollTops[key] != null) body.scrollTop = savedScrollTops[key];
            body.addEventListener('scroll', function onBlockScroll() {
                const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
                state.outputBlockUserScrolled[key] = !nearBottom;
            }, { passive: true });
        });
    }

    function clear() {
        state.taskOutputs = {};
        state.outputUserScrolled = false;
        state.outputBlockUserScrolled = {};
        state.outputLastUpdatedKey = '';
        renderOutput();
    }

    function setTaskOutput(taskId, output) {
        if (!taskId) return;
        state.taskOutputs[taskId] = output;
        state.outputLastUpdatedKey = String(taskId);
        renderOutput();
    }

    let _outputModalOpen = false;
    function openOutputModal(taskId, contentHtml, scrollTop, titleLabel) {
        const modal = document.getElementById('taskAgentOutputModal');
        const titleEl = document.getElementById('taskAgentOutputModalTitle');
        const bodyEl = document.getElementById('taskAgentOutputModalBody');
        const closeBtn = document.getElementById('taskAgentOutputModalClose');
        const backdrop = modal?.querySelector('.task-agent-output-modal-backdrop');
        if (!modal || !bodyEl) return;
        if (_outputModalOpen) return;
        _outputModalOpen = true;
        modal.setAttribute('data-current-task-id', taskId || '');
        titleEl.textContent = titleLabel || (taskId ? 'Task ' + taskId : 'Task Output');
        bodyEl.innerHTML = contentHtml || '';
        bodyEl.scrollTop = scrollTop || 0;
        if (typeof hljs !== 'undefined') {
            requestAnimationFrame(() => {
                bodyEl.querySelectorAll('pre code').forEach((node) => { try { hljs.highlightElement(node); } catch (_) {} });
            });
        }
        modal.classList.add('is-open');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        function closeModal() {
            _outputModalOpen = false;
            modal.classList.remove('is-open');
            modal.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
            document.removeEventListener('keydown', keydownHandler);
        }
        const keydownHandler = (ev) => { if (ev.key === 'Escape') closeModal(); };
        closeBtn?.addEventListener('click', closeModal, { once: true });
        backdrop?.addEventListener('click', closeModal, { once: true });
        document.addEventListener('keydown', keydownHandler);
    }

    function applyOutputHighlight() {
        const el = document.getElementById('taskAgentOutputContent');
        if (!el || typeof hljs === 'undefined') return;
        requestIdleCallback(() => {
            el.querySelectorAll('pre code').forEach((node) => { try { hljs.highlightElement(node); } catch (_) {} });
        }, { timeout: 500 });
    }

    function downloadTaskOutput(taskId) {
        const raw = state.taskOutputs[taskId];
        const payload = typeof outputUtils.toDownloadPayload === 'function'
            ? outputUtils.toDownloadPayload(raw, taskId)
            : { text: '', filename: `task-${taskId || 'output'}.txt`, mime: 'text/plain' };
        const blob = new Blob([payload.text], { type: payload.mime });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = payload.filename;
        a.click();
        URL.revokeObjectURL(a.href);
    }

    function initOutputScrollTracking() {
        const el = document.getElementById('taskAgentOutputContent');
        if (!el) return;
        el.addEventListener('scroll', () => {
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            state.outputUserScrolled = !nearBottom;
        }, { passive: true });
    }

    function initOutputAreaClick() {
        const area = document.getElementById('taskAgentOutputArea');
        if (!area) return;
        area.addEventListener('click', (e) => {
            const expandBtn = e.target.closest('.task-agent-output-block-expand');
            if (expandBtn) {
                e.stopPropagation();
                const block = expandBtn.closest('.task-agent-output-block');
                if (block) {
                    const bodyEl = block.querySelector('.task-agent-output-block-body');
                    const label = block.getAttribute('data-label') || '';
                    const taskId = block.getAttribute('data-task-id') || '';
                    openOutputModal(taskId, bodyEl?.innerHTML || '', bodyEl?.scrollTop || 0, label || (taskId ? 'Task ' + taskId : 'Task Output'));
                }
                return;
            }
            const block = e.target.closest('.task-agent-output-block');
            if (!block) return;
            const allBlocks = area.querySelectorAll('.task-agent-output-block');
            const wasFocused = block.classList.contains('is-focused');
            allBlocks.forEach((b) => b.classList.remove('is-focused'));
            if (!wasFocused) block.classList.add('is-focused');
        });
    }

    function initOutputModalDownload() {
        const downloadBtn = document.getElementById('taskAgentOutputModalDownload');
        const modal = document.getElementById('taskAgentOutputModal');
        if (!downloadBtn || !modal) return;
        downloadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            downloadTaskOutput(modal.getAttribute('data-current-task-id') || '');
        });
    }

    initOutputScrollTracking();
    initOutputAreaClick();
    initOutputModalDownload();

    (function initFlowStartListeners() {
        const onFlowStart = () => clear();
        document.addEventListener('maars:idea-start', onFlowStart);
        document.addEventListener('maars:plan-start', onFlowStart);
        document.addEventListener('maars:task-start', onFlowStart);
        document.addEventListener('maars:restore-start', onFlowStart);
    })();

    document.addEventListener('maars:idea-complete', (e) => {
        const data = e.detail || {};
        const hasRefined = typeof data.refined_idea === 'string' && data.refined_idea.trim();
        if (data.keywords != null || (data.papers && data.papers.length > 0) || hasRefined) {
            const formatted = formatRefineResult(data);
            setTaskOutput('idea', { content: formatted, label: 'Refine' });
            applyOutputHighlight();
            document.dispatchEvent(new CustomEvent('maars:switch-to-output-tab'));
        }
    });

    document.addEventListener('maars:restore-complete', (e) => {
        const { outputs } = e.detail || {};
        if (outputs && Object.keys(outputs).length) {
            Object.entries(outputs).forEach(([taskId, out]) => {
                const val = out && typeof out === 'object' && 'content' in out ? out.content : out;
                const key = taskId === 'idea' ? 'idea' : 'task_' + taskId;
                setTaskOutput(key, val);
            });
            applyOutputHighlight();
        }
    });

    document.addEventListener('maars:task-complete', () => applyOutputHighlight());

    document.addEventListener('maars:task-output', (e) => {
        const data = e.detail;
        if (data?.taskId) setTaskOutput('task_' + data.taskId, data.output);
    });

    window.MAARS.output = { setTaskOutput, renderOutput, applyOutputHighlight, clear };
})();
