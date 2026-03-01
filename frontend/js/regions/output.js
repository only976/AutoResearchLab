/**
 * MAARS Output 区域 - Agent 最终产出展示（idea 文献、task artifact）。
 * 与 region-responsibilities 中 Output 区域对应。
 */
(function () {
    'use strict';

    const escapeHtml = window.MAARS?.utils?.escapeHtml || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));
    const escapeHtmlAttr = window.MAARS?.utils?.escapeHtmlAttr || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));

    const state = window.MAARS.state || {};
    state.taskOutputs = state.taskOutputs || {};
    state.outputUserScrolled = state.outputUserScrolled ?? false;
    state.outputBlockUserScrolled = state.outputBlockUserScrolled || {};
    state.outputLastUpdatedKey = state.outputLastUpdatedKey || '';
    window.MAARS.state = state;

    /** Refine 结果格式化（由 output 负责展示逻辑） */
    function formatRefineResult(data) {
        const keywords = data.keywords || [];
        const papers = data.papers || [];
        const refined = data.refined_idea || {};
        const desc = refined.description || '';
        const rqs = refined.research_questions || [];
        const gap = refined.research_gap || '';
        const method = refined.method_approach || '';

        let md = '## Refine Results\n\n';
        if (desc) {
            md += '### Refined Idea\n\n' + desc + '\n\n';
        }
        if (rqs.length) {
            md += '**Research Questions:**\n';
            rqs.forEach((q) => { md += '- ' + q + '\n'; });
            md += '\n';
        }
        if (gap) {
            md += '**Research Gap:** ' + gap + '\n\n';
        }
        if (method) {
            md += '**Method Approach:** ' + method + '\n\n';
        }
        md += '**Keywords:** ' + (keywords.length ? keywords.join(', ') : '—') + '\n\n';
        md += '**Papers (' + papers.length + '):**\n\n';
        papers.forEach((p, i) => {
            const title = (p.title || '').replace(/[[\]]/g, '\\$&');
            const url = p.url || '#';
            const authors = Array.isArray(p.authors) ? p.authors.join(', ') : '';
            const published = p.published || '';
            const abstract = (p.abstract || '').replace(/\s+/g, ' ').slice(0, 300) + (p.abstract && p.abstract.length > 300 ? '...' : '');
            md += (i + 1) + '. **[' + title + '](' + url + ')**';
            if (published) md += ' (' + published + ')';
            md += '\n';
            if (authors) md += '   *Authors:* ' + authors + '\n';
            if (abstract) md += '   ' + abstract + '\n';
            md += '\n';
        });
        return md;
    }
    function renderOutput() {
        const el = document.getElementById('taskAgentOutputContent');
        const area = document.getElementById('taskAgentOutputArea');
        if (!el || !area) return;
        const outputs = state.taskOutputs;
        if (outputs.refine !== undefined) {
            outputs.idea = outputs.refine;
            delete outputs.refine;
        }
        const keys = Object.keys(outputs).sort((a, b) => {
            if (a === 'idea') return -1;
            if (b === 'idea') return 1;
            if (a.startsWith('task_') && b.startsWith('task_')) {
                const na = parseInt(a.slice(6), 10);
                const nb = parseInt(b.slice(6), 10);
                if (!isNaN(na) && !isNaN(nb)) return na - nb;
            }
            return String(a).localeCompare(b);
        });
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
            let content = '';
            let displayLabel = taskId === 'idea' ? 'Refine' : (taskId.startsWith('task_') ? 'Task ' + taskId.slice(6) : 'Task ' + (taskId || ''));
            if (typeof raw === 'object' && raw !== null && raw.label) {
                displayLabel = raw.label;
                if ('content' in raw && typeof raw.content === 'string') {
                    const text = raw.content || '';
                    content = text ? (typeof marked !== 'undefined' ? marked.parse(text) : text) : '';
                } else {
                    const str = JSON.stringify(raw, null, 2);
                    content = typeof marked !== 'undefined' ? marked.parse('```json\n' + str + '\n```') : '<pre>' + str + '</pre>';
                }
            } else {
                content = (raw || '') ? (typeof marked !== 'undefined' ? marked.parse(String(raw)) : String(raw)) : '';
            }
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
        let text = '', ext = 'txt';
        if (raw != null) {
            if (typeof raw === 'string') { text = raw; ext = 'md'; }
            else if (typeof raw === 'object' && raw !== null && 'content' in raw && typeof raw.content === 'string') { text = raw.content; ext = 'md'; }
            else { text = JSON.stringify(raw, null, 2); ext = 'json'; }
        }
        const filename = `task-${(taskId || 'output').replace(/[^a-zA-Z0-9_-]/g, '_')}.${ext}`;
        const blob = new Blob([text], { type: ext === 'json' ? 'application/json' : 'text/markdown' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
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
        if (data.keywords != null || (data.papers && data.papers.length > 0) || (data.refined_idea && data.refined_idea.description)) {
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
