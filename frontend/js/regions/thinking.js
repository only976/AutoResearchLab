/**
 * MAARS Thinking 区域 - AI 推理过程展示（plan/task/idea thinking 流）。
 * 与 region-responsibilities 中 Thinking 区域对应。
 */
(function () {
    'use strict';

    const escapeHtml = window.MAARS?.utils?.escapeHtml || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));
    const truncateForDisplay = (s, maxLen) => {
        if (s == null || typeof s !== 'string') return '';
        const str = String(s).trim();
        if (str.length <= maxLen) return str;
        return str.slice(0, maxLen - 3) + '...';
    };
    function _isNoThinking(block) {
        const raw = (block.content || '').trim();
        if (!raw) return false;
        try {
            const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
            JSON.parse(m ? m[1].trim() : raw);
            return true;
        } catch (_) {
            return false;
        }
    }
    const RENDER_THROTTLE_MS = 120;
    const RENDER_THROTTLE_LARGE_MS = 250;
    const LARGE_CONTENT_CHARS = 6000;

    const PREFIX = 'thinking';
    const CONTENT_EL = 'planAgentThinkingContent';
    const AREA_EL = 'planAgentThinkingArea';
    const BLOCK_CLASS = 'plan-agent-thinking-block';

    const state = window.MAARS.state || {};
    state[`${PREFIX}ThinkingBlocks`] = state[`${PREFIX}ThinkingBlocks`] || [];
    state[`${PREFIX}ThinkingUserScrolled`] = state[`${PREFIX}ThinkingUserScrolled`] ?? false;
    state[`${PREFIX}ThinkingBlockUserScrolled`] = state[`${PREFIX}ThinkingBlockUserScrolled`] || {};
    state[`${PREFIX}LastUpdatedBlockKey`] = state[`${PREFIX}LastUpdatedBlockKey`] || '';
    state[`${PREFIX}ScheduleCounter`] = state[`${PREFIX}ScheduleCounter`] ?? 0;
    state[`${PREFIX}PlanCounter`] = state[`${PREFIX}PlanCounter`] ?? 0;
    state[`${PREFIX}PlanStreamingKey`] = state[`${PREFIX}PlanStreamingKey`] ?? '';
    state[`${PREFIX}IdeaCounter`] = state[`${PREFIX}IdeaCounter`] ?? 0;
    state[`${PREFIX}IdeaStreamingKey`] = state[`${PREFIX}IdeaStreamingKey`] ?? '';
    window.MAARS.state = state;

    let _renderScheduled = null;

    /** 构建 thinking 块 header 文案，调度信息与有内容块共用同一格式 */
    function _buildHeaderText(block) {
        const si = block.scheduleInfo || {};
        const agentLabel = (block.source || 'Thinking').charAt(0).toUpperCase() + (block.source || 'thinking').slice(1);
        const op = si.operation || block.operation || '—';
        const tid = si.task_id ?? block.taskId;
        const tidStr = tid != null ? String(tid) : '—';
        const parts = [agentLabel, op, tidStr];
        if (si.turn != null) parts.push(`Turn ${si.turn}${si.max_turns != null ? `/${si.max_turns}` : ''}`);
        if (si.tool_name) {
            const argsDisplay = si.tool_args_preview || (si.tool_args ? truncateForDisplay(si.tool_args, 50) : null);
            parts.push(si.tool_name + (argsDisplay ? `(${argsDisplay})` : ''));
        }
        return parts.join(' · ');
    }

    function renderThinking(skipHighlight) {
        const el = document.getElementById(CONTENT_EL);
        const area = document.getElementById(AREA_EL);
        if (!el) return;
        const blocks = state[`${PREFIX}ThinkingBlocks`];
        let html = '';
        let i = 0;
        while (i < blocks.length) {
            const block = blocks[i];
            const isHeaderOnly = block.blockType === 'schedule' || _isNoThinking(block);
            const headerText = _buildHeaderText(block);
            i++;
            if (isHeaderOnly) {
                /* 调度信息 / 纯 JSON：与 thinking 块相同结构，仅展示 header，body 隐藏 */
                html += `<div class="${BLOCK_CLASS} ${BLOCK_CLASS}--header-only" data-block-key="${(block.key || '').replace(/"/g, '&quot;')}"><div class="${BLOCK_CLASS}-header">${escapeHtml(headerText || '')}</div></div>`;
                continue;
            }
            const raw = block.content || '';
            let blockHtml = raw ? (typeof marked !== 'undefined' ? marked.parse(raw) : raw) : '';
            if (blockHtml && typeof DOMPurify !== 'undefined') blockHtml = DOMPurify.sanitize(blockHtml);
            html += `<div class="${BLOCK_CLASS}" data-block-key="${(block.key || '').replace(/"/g, '&quot;')}"><div class="${BLOCK_CLASS}-header">${escapeHtml(headerText || '')}</div><div class="${BLOCK_CLASS}-body">${blockHtml}</div></div>`;
        }
        const wasNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        const savedScrollTops = {};
        el.querySelectorAll(`.${BLOCK_CLASS}`).forEach((blockEl) => {
            const key = blockEl.getAttribute('data-block-key') || '';
            const body = blockEl.querySelector(`.${BLOCK_CLASS}-body`);
            if (body) savedScrollTops[key] = body.scrollTop;
        });
        try {
            el.innerHTML = html || '';
            if (!skipHighlight && typeof hljs !== 'undefined') {
                const codeBlocks = el.querySelectorAll('pre code');
                if (codeBlocks.length > 0 && codeBlocks.length <= 15) {
                    codeBlocks.forEach((node) => { try { hljs.highlightElement(node); } catch (_) {} });
                }
            }
        } catch (_) {
            el.textContent = blocks.map((b) => b.content || '').join('\n\n');
        }
        if (!state[`${PREFIX}ThinkingUserScrolled`] && wasNearBottom) {
            requestAnimationFrame(() => { requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; }); });
        }
        state[`${PREFIX}ThinkingBlockUserScrolled`] = state[`${PREFIX}ThinkingBlockUserScrolled`] || {};
        const lastKey = state[`${PREFIX}LastUpdatedBlockKey`] || '';
        el.querySelectorAll(`.${BLOCK_CLASS}`).forEach((blockEl) => {
            const key = blockEl.getAttribute('data-block-key') || '';
            const body = blockEl.querySelector(`.${BLOCK_CLASS}-body`);
            if (!body) return;
            const shouldAutoScroll = key === lastKey && !state[`${PREFIX}ThinkingBlockUserScrolled`][key];
            if (shouldAutoScroll) requestAnimationFrame(() => { body.scrollTop = body.scrollHeight; });
            else if (savedScrollTops[key] != null) body.scrollTop = savedScrollTops[key];
            body.addEventListener('scroll', function onBlockScroll() {
                const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
                state[`${PREFIX}ThinkingBlockUserScrolled`][key] = !nearBottom;
            }, { passive: true });
        });
        if (area && blocks.length) area.classList.add('has-content');
    }

    function scheduleRender() {
        if (_renderScheduled) return;
        const totalChars = state[`${PREFIX}ThinkingBlocks`].reduce((s, b) => s + (b.content || '').length, 0);
        const throttle = totalChars > LARGE_CONTENT_CHARS ? RENDER_THROTTLE_LARGE_MS : RENDER_THROTTLE_MS;
        _renderScheduled = setTimeout(() => {
            _renderScheduled = null;
            renderThinking(true);
        }, throttle);
    }

    function clear(opts) {
        state[`${PREFIX}ThinkingBlocks`] = [];
        state[`${PREFIX}ThinkingUserScrolled`] = false;
        state[`${PREFIX}ThinkingBlockUserScrolled`] = {};
        state[`${PREFIX}LastUpdatedBlockKey`] = '';
        state[`${PREFIX}ScheduleCounter`] = 0;
        state[`${PREFIX}PlanCounter`] = 0;
        state[`${PREFIX}PlanStreamingKey`] = '';
        state[`${PREFIX}IdeaCounter`] = 0;
        state[`${PREFIX}IdeaStreamingKey`] = '';
        const el = document.getElementById(CONTENT_EL);
        const area = document.getElementById(AREA_EL);
        if (el) el.innerHTML = '';
        if (area) area.classList.remove('has-content');
    }

    function appendChunk(chunk, taskId, operation, scheduleInfo, source) {
        const blocksKey = `${PREFIX}ThinkingBlocks`;
        const planStreamingKey = `${PREFIX}PlanStreamingKey`;
        const ideaStreamingKey = `${PREFIX}IdeaStreamingKey`;
        const scheduleCounterKey = `${PREFIX}ScheduleCounter`;
        const planCounterKey = `${PREFIX}PlanCounter`;
        const ideaCounterKey = `${PREFIX}IdeaCounter`;
        const lastUpdatedKey = `${PREFIX}LastUpdatedBlockKey`;
        const isIdea = source === 'idea' || operation === 'Refine';

        if (!chunk && scheduleInfo != null) {
            state[planStreamingKey] = '';
            state[ideaStreamingKey] = '';
            if (scheduleInfo.tool_name || scheduleInfo.operation) {
                state[scheduleCounterKey] = (state[scheduleCounterKey] || 0) + 1;
                const key = `schedule_${state[scheduleCounterKey]}`;
                state[blocksKey].push({
                    key,
                    blockType: 'schedule',
                    scheduleInfo,
                    taskId: taskId ?? scheduleInfo.task_id,
                    operation: operation ?? scheduleInfo.operation,
                    source: source || 'task',
                });
                state[lastUpdatedKey] = key;
                scheduleRender();
            }
            return;
        }
        if (taskId == null && isIdea && chunk) {
            let block = state[ideaStreamingKey] ? state[blocksKey].find((b) => b.key === state[ideaStreamingKey]) : null;
            state[planStreamingKey] = '';
            if (block && block.operation !== operation) {
                block = null;
                state[ideaStreamingKey] = '';
            }
            if (block) {
                block.content += chunk;
                if (scheduleInfo != null) block.scheduleInfo = scheduleInfo;
                state[lastUpdatedKey] = block.key;
            } else {
                state[ideaCounterKey] = (state[ideaCounterKey] || 0) + 1;
                const key = `idea_${state[ideaCounterKey]}`;
                block = { key, taskId: null, operation: operation || 'Refine', content: chunk, scheduleInfo: scheduleInfo || null, source: 'idea' };
                state[blocksKey].push(block);
                state[ideaStreamingKey] = key;
                state[lastUpdatedKey] = key;
            }
            scheduleRender();
            return;
        }
        if (taskId == null && chunk) {
            let block = state[planStreamingKey] ? state[blocksKey].find((b) => b.key === state[planStreamingKey]) : null;
            state[ideaStreamingKey] = '';
            if (block && block.operation !== operation) {
                block = null;
                state[planStreamingKey] = '';
            }
            if (block) {
                block.content += chunk;
                if (scheduleInfo != null) block.scheduleInfo = scheduleInfo;
                state[lastUpdatedKey] = block.key;
            } else {
                state[planCounterKey] = (state[planCounterKey] || 0) + 1;
                const key = `plan_${state[planCounterKey]}`;
                block = { key, taskId: null, operation: operation || 'Plan', content: chunk, scheduleInfo: scheduleInfo || null, source: 'plan' };
                state[blocksKey].push(block);
                state[planStreamingKey] = key;
                state[lastUpdatedKey] = key;
            }
            scheduleRender();
            return;
        }
        state[planStreamingKey] = '';
        state[ideaStreamingKey] = '';
        const key = (taskId != null && operation != null) ? `${String(taskId)}::${String(operation)}` : '_default';
        let block = state[blocksKey].find((b) => b.key === key);
        if (!block) {
            block = { key, taskId, operation, content: '', scheduleInfo: null, source: source || 'task' };
            state[blocksKey].push(block);
        }
        if (chunk) block.content += chunk;
        if (scheduleInfo != null) block.scheduleInfo = scheduleInfo;
        state[lastUpdatedKey] = key;
        scheduleRender();
    }

    function applyHighlight() {
        const el = document.getElementById(CONTENT_EL);
        if (!el || typeof hljs === 'undefined') return;
        requestIdleCallback(() => {
            el.querySelectorAll('pre code').forEach((node) => { try { hljs.highlightElement(node); } catch (_) {} });
        }, { timeout: 500 });
    }

    (function initThinkingArea() {
        const el = document.getElementById(CONTENT_EL);
        if (!el) return;
        el.addEventListener('scroll', () => {
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            state[`${PREFIX}ThinkingUserScrolled`] = !nearBottom;
        }, { passive: true });
        const area = document.getElementById(AREA_EL);
        if (!area) return;
        const headerOnlyModifier = `${BLOCK_CLASS}--header-only`;
        area.addEventListener('click', (e) => {
            const block = e.target.closest(`.${BLOCK_CLASS}`);
            if (!block || block.classList.contains(headerOnlyModifier)) return;
            const allBlocks = area.querySelectorAll(`.${BLOCK_CLASS}:not(.${headerOnlyModifier})`);
            const wasFocused = block.classList.contains('is-focused');
            allBlocks.forEach((b) => b.classList.remove('is-focused'));
            if (!wasFocused) block.classList.add('is-focused');
        });
    })();

    (function initFlowStartListeners() {
        const onFlowStart = () => clear();
        document.addEventListener('maars:idea-start', onFlowStart);
        document.addEventListener('maars:plan-start', onFlowStart);
        document.addEventListener('maars:task-start', onFlowStart);
        document.addEventListener('maars:restore-start', onFlowStart);
    })();

    (function initFlowCompleteListeners() {
        const onFlowComplete = () => applyHighlight();
        document.addEventListener('maars:idea-complete', onFlowComplete);
        document.addEventListener('maars:plan-complete', onFlowComplete);
        document.addEventListener('maars:task-complete', onFlowComplete);
    })();

    window.MAARS.thinking = { clear, appendChunk, applyHighlight };
})();
