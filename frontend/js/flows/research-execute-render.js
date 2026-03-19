/**
 * Execute timeline rendering helpers extracted from research-large-helpers.
 */
(function () {
    function _isExecuteStreamNearBottom(ctx) {
        const bodyEl = ctx.executeStreamBodyEl;
        if (!bodyEl) return true;
        return (bodyEl.scrollHeight - bodyEl.scrollTop - bodyEl.clientHeight) < 48;
    }

    function _scrollExecuteStreamToLatest(ctx) {
        const bodyEl = ctx.executeStreamBodyEl;
        if (!bodyEl) return;
        bodyEl.scrollTop = bodyEl.scrollHeight;
    }

    function _updateExecuteJumpLatestButton(ctx) {
        const jumpBtnEl = ctx.executeJumpLatestBtnEl;
        if (!jumpBtnEl || !ctx.executeStreamBodyEl) return;
        const hasMessages = (ctx.executeState.messages || []).length > 0;
        const shouldShow = hasMessages && !ctx.getExecuteAutoFollow() && !_isExecuteStreamNearBottom(ctx);
        jumpBtnEl.hidden = !shouldShow;
    }

    function _formatElapsedDuration(ctx, ms) {
        if (typeof ctx.executeUtils.formatElapsedDuration === 'function') {
            return ctx.executeUtils.formatElapsedDuration(ms);
        }
        return '0s';
    }

    function _hasActiveExecuteBubble(ctx) {
        return ctx.executeState.messages.some((msg) => {
            if (msg.kind !== 'assistant') return false;
            const taskId = String(msg.taskId || '').trim();
            if (!taskId) return false;
            const status = String(ctx.executeState.statuses.get(taskId) || '').trim();
            return status === 'doing' || status === 'validating';
        });
    }

    function _syncExecuteElapsedTicker(ctx) {
        const shouldRun = ctx.getActiveStage() === 'execute' && _hasActiveExecuteBubble(ctx);
        if (!shouldRun) {
            if (ctx.getExecuteElapsedTimerId()) {
                window.clearInterval(ctx.getExecuteElapsedTimerId());
                ctx.setExecuteElapsedTimerId(0);
            }
            return;
        }
        if (ctx.getExecuteElapsedTimerId()) return;
        const timerId = window.setInterval(() => {
            if (ctx.getActiveStage() !== 'execute' || !_hasActiveExecuteBubble(ctx)) {
                _syncExecuteElapsedTicker(ctx);
                return;
            }
            ctx.renderExecuteStream();
        }, 1000);
        ctx.setExecuteElapsedTimerId(timerId);
    }

    function _getAttemptKey(ctx, taskId, attempt) {
        if (typeof ctx.executeUtils.getAttemptKey === 'function') {
            return ctx.executeUtils.getAttemptKey(taskId, attempt);
        }
        return `${String(taskId || '').trim()}:${Number(attempt) || 1}`;
    }

    function _getCurrentAttempt(ctx, taskId) {
        const id = String(taskId || '').trim();
        if (!id) return 1;
        const current = Number(ctx.executeState.currentAttemptByTask.get(id));
        return Number.isFinite(current) && current > 0 ? current : 1;
    }

    function _getAttemptStatus(ctx, taskId, attempt, msgs, fallbackStatus) {
        if (typeof ctx.executeUtils.getAttemptStatus === 'function') {
            return ctx.executeUtils.getAttemptStatus({
                taskId,
                attempt,
                msgs,
                fallbackStatus,
                currentAttempt: _getCurrentAttempt(ctx, taskId),
            });
        }
        return String(fallbackStatus || 'doing').trim() || 'doing';
    }

    function _getAttemptSummary(ctx, msgs) {
        if (typeof ctx.executeUtils.getAttemptSummary === 'function') {
            return ctx.executeUtils.getAttemptSummary(msgs);
        }
        return '';
    }

    function renderExecuteStream(ctx) {
        const executeStreamBodyEl = ctx.executeStreamBodyEl;
        if (!executeStreamBodyEl) return;
        const wasNearBottom = _isExecuteStreamNearBottom(ctx);
        const messages = Array.isArray(ctx.executeState.messages) ? ctx.executeState.messages : [];

        executeStreamBodyEl.textContent = '';

        if (!messages.length) {
            const empty = document.createElement('div');
            empty.className = 'research-execute-empty';
            empty.textContent = '执行开始后，这里会像对话流一样持续展示每一步的状态与产出。';
            executeStreamBodyEl.appendChild(empty);
            return;
        }

        const taskMessages = new Map();
        messages.forEach((msg) => {
            const taskId = msg.taskId || 'system';
            if (!taskMessages.has(taskId)) {
                taskMessages.set(taskId, []);
            }
            taskMessages.get(taskId).push(msg);
        });

        const renderBlocks = [];
        ctx.executeState.order.forEach((taskId) => {
            if (!taskMessages.has(taskId)) return;
            const msgs = taskMessages.get(taskId);
            if (!msgs.length) return;
            renderBlocks.push({ type: 'task', taskId, msgs, firstIndex: messages.indexOf(msgs[0]) });
        });

        const systemMsgs = messages.filter((m) => !m.taskId);
        systemMsgs.forEach((msg) => {
            renderBlocks.push({ type: 'system', msg, firstIndex: messages.indexOf(msg) });
        });

        renderBlocks.sort((a, b) => a.firstIndex - b.firstIndex);

        renderBlocks.forEach((block) => {
            if (block.type === 'task') {
                const taskId = block.taskId;
                const msgs = block.msgs;
                const meta = ctx.getTaskMetaById(taskId) || {};
                const status = ctx.executeState.statuses.get(taskId) || meta.status || 'undone';
                const statusTone = ctx.statusTone(status);
                const attemptGroups = new Map();
                msgs.forEach((msg) => {
                    const attempt = Number(msg.attempt) || 1;
                    if (!attemptGroups.has(attempt)) attemptGroups.set(attempt, []);
                    attemptGroups.get(attempt).push(msg);
                });
                const attemptNumbers = Array.from(attemptGroups.keys()).sort((a, b) => a - b);
                const latestAttempt = attemptNumbers.length ? attemptNumbers[attemptNumbers.length - 1] : _getCurrentAttempt(ctx, taskId);

                const cardEl = document.createElement('div');
                cardEl.className = `research-execute-task-card research-execute-task-card--${statusTone}`;
                cardEl.setAttribute('data-task-id', taskId);

                const headerEl = document.createElement('div');
                headerEl.className = 'research-execute-task-header';

                const toggleEl = document.createElement('button');
                toggleEl.className = 'research-execute-task-toggle';
                toggleEl.innerHTML = '▶';
                toggleEl.setAttribute('aria-label', 'Toggle task details');
                toggleEl.type = 'button';
                headerEl.appendChild(toggleEl);

                const dotEl = document.createElement('span');
                dotEl.className = `research-execute-status-dot is-${statusTone}`;
                headerEl.appendChild(dotEl);

                const titleWrapEl = document.createElement('div');
                titleWrapEl.style.flex = '1 1 auto';
                titleWrapEl.style.minWidth = '0';
                titleWrapEl.hidden = false;
                titleWrapEl.style.flexDirection = 'column';
                titleWrapEl.style.gap = '4px';

                const titleEl = document.createElement('div');
                titleEl.className = 'research-execute-task-title';
                titleEl.textContent = `${meta.title || taskId} · Attempt ${latestAttempt}`;
                titleWrapEl.appendChild(titleEl);

                const thinkingMsg = [...msgs].reverse().find((m) => Number(m.attempt) === latestAttempt && m.kind === 'assistant');
                if (thinkingMsg) {
                    const opEl = document.createElement('div');
                    opEl.className = 'research-execute-task-operation';
                    const opText = String(thinkingMsg.title || '').split('·').slice(1).join('·').trim();
                    opEl.textContent = opText ? `— ${opText}` : '';
                    titleWrapEl.appendChild(opEl);
                }

                headerEl.appendChild(titleWrapEl);

                const labelEl = document.createElement('span');
                labelEl.className = 'research-execute-task-status-label';
                labelEl.textContent = ctx.statusLabel(status);
                headerEl.appendChild(labelEl);

                cardEl.appendChild(headerEl);

                const detailsEl = document.createElement('div');
                detailsEl.className = 'research-execute-task-details';
                let isExpanded = ctx.executeState.taskExpandedById.get(taskId);
                if (typeof isExpanded !== 'boolean') isExpanded = true;
                ctx.executeState.taskExpandedById.set(taskId, isExpanded);

                const contentEl = document.createElement('div');
                contentEl.className = 'research-execute-task-content';

                attemptNumbers.forEach((attemptNumber) => {
                    const attemptMsgs = attemptGroups.get(attemptNumber) || [];
                    const attemptKey = _getAttemptKey(ctx, taskId, attemptNumber);
                    let attemptExpanded = ctx.executeState.attemptExpandedById.get(attemptKey);
                    if (typeof attemptExpanded !== 'boolean') {
                        attemptExpanded = attemptNumber >= latestAttempt;
                        ctx.executeState.attemptExpandedById.set(attemptKey, attemptExpanded);
                    }
                    const attemptStatus = _getAttemptStatus(ctx, taskId, attemptNumber, attemptMsgs, status);
                    const attemptTone = ctx.statusTone(attemptStatus);

                    const attemptEl = document.createElement('div');
                    attemptEl.className = `research-execute-attempt research-execute-attempt--${attemptTone}`;

                    const attemptHeaderEl = document.createElement('div');
                    attemptHeaderEl.className = 'research-execute-attempt-header';

                    const attemptToggleEl = document.createElement('button');
                    attemptToggleEl.className = 'research-execute-attempt-toggle';
                    attemptToggleEl.innerHTML = '▶';
                    attemptToggleEl.setAttribute('aria-label', 'Toggle attempt details');
                    attemptToggleEl.type = 'button';
                    attemptHeaderEl.appendChild(attemptToggleEl);

                    const attemptTitleEl = document.createElement('div');
                    attemptTitleEl.className = 'research-execute-attempt-title';
                    attemptTitleEl.textContent = `Attempt ${attemptNumber}${attemptNumber === latestAttempt ? ' · Current' : ''}`;
                    attemptHeaderEl.appendChild(attemptTitleEl);

                    const attemptLabelEl = document.createElement('span');
                    attemptLabelEl.className = 'research-execute-attempt-status-label';
                    attemptLabelEl.textContent = ctx.statusLabel(attemptStatus);
                    attemptHeaderEl.appendChild(attemptLabelEl);

                    const attemptSummary = _getAttemptSummary(ctx, attemptMsgs);
                    if (attemptSummary) {
                        const attemptSummaryEl = document.createElement('div');
                        attemptSummaryEl.className = 'research-execute-attempt-summary';
                        attemptSummaryEl.textContent = attemptSummary;
                        attemptHeaderEl.appendChild(attemptSummaryEl);
                    }

                    const attemptBodyEl = document.createElement('div');
                    attemptBodyEl.className = 'research-execute-attempt-body';
                    const activeAssistantMsg = (attemptNumber === latestAttempt && (attemptStatus === 'doing' || attemptStatus === 'validating'))
                        ? [...attemptMsgs].reverse().find((m) => m.kind === 'assistant') || null
                        : null;

                    attemptMsgs.forEach((msg) => {
                        const msgEl = document.createElement('div');
                        msgEl.className = `research-execute-message research-execute-message--${msg.kind || 'assistant'}`;

                        const metaEl = document.createElement('div');
                        metaEl.className = 'research-execute-message-meta';
                        if (msg.kind && msg.kind !== 'system') {
                            const kindEl = document.createElement('span');
                            kindEl.className = 'research-execute-message-kind';
                            kindEl.textContent = msg.kind === 'output' ? 'Output' : msg.kind === 'error' ? 'Error' : msg.kind === 'system' ? 'System' : 'Think';
                            metaEl.appendChild(kindEl);
                        }
                        msgEl.appendChild(metaEl);

                        const bubbleEl = document.createElement('div');
                        bubbleEl.className = 'research-execute-message-bubble';

                        if (msg.title) {
                            const messageTitleEl = document.createElement('div');
                            messageTitleEl.className = 'research-execute-message-title';
                            const repeatCount = Number(msg.repeatCount || 1);
                            messageTitleEl.textContent = repeatCount > 1 ? `${msg.title} ×${repeatCount}` : msg.title;
                            bubbleEl.appendChild(messageTitleEl);
                            if (msg.tokenMetaText) {
                                const tokenMetaEl = document.createElement('div');
                                tokenMetaEl.className = 'research-execute-message-token-meta';
                                const tokenMetaBits = [String(msg.tokenMetaText || '').trim()].filter(Boolean);
                                if (msg === activeAssistantMsg) {
                                    tokenMetaBits.push(`elapsed ${_formatElapsedDuration(ctx, Date.now() - Number(msg.startedAt || msg.at || Date.now()))}`);
                                }
                                tokenMetaEl.textContent = tokenMetaBits.join(' · ');
                                bubbleEl.appendChild(tokenMetaEl);
                            } else if (msg === activeAssistantMsg) {
                                const tokenMetaEl = document.createElement('div');
                                tokenMetaEl.className = 'research-execute-message-token-meta';
                                tokenMetaEl.textContent = `elapsed ${_formatElapsedDuration(ctx, Date.now() - Number(msg.startedAt || msg.at || Date.now()))}`;
                                bubbleEl.appendChild(tokenMetaEl);
                            }
                        }

                        const bodyEl = document.createElement('div');
                        bodyEl.className = 'research-execute-message-body';
                        const bodyText = String(msg.body || '').trim() || '—';
                        bodyEl.textContent = bodyText.length > 6000 ? bodyText.slice(-6000) : bodyText;
                        bubbleEl.appendChild(bodyEl);

                        msgEl.appendChild(bubbleEl);
                        attemptBodyEl.appendChild(msgEl);
                    });

                    attemptEl.appendChild(attemptHeaderEl);
                    attemptEl.appendChild(attemptBodyEl);
                    attemptBodyEl.hidden = !attemptExpanded;
                    attemptToggleEl.style.transform = attemptExpanded ? 'rotate(90deg)' : 'rotate(0deg)';

                    const toggleAttempt = () => {
                        attemptExpanded = !attemptExpanded;
                        ctx.executeState.attemptExpandedById.set(attemptKey, attemptExpanded);
                        attemptBodyEl.hidden = !attemptExpanded;
                        attemptToggleEl.style.transform = attemptExpanded ? 'rotate(90deg)' : 'rotate(0deg)';
                    };

                    attemptToggleEl.addEventListener('click', (e) => {
                        e.stopPropagation();
                        toggleAttempt();
                    });
                    attemptHeaderEl.addEventListener('click', toggleAttempt);

                    contentEl.appendChild(attemptEl);
                });

                detailsEl.appendChild(contentEl);
                cardEl.appendChild(detailsEl);

                toggleEl.addEventListener('click', (e) => {
                    e.stopPropagation();
                    isExpanded = !isExpanded;
                    ctx.executeState.taskExpandedById.set(taskId, isExpanded);
                    toggleEl.style.transform = isExpanded ? 'rotate(90deg)' : 'rotate(0deg)';
                    detailsEl.hidden = !isExpanded;
                    ctx.updateExecuteToggleAllButton();
                });

                detailsEl.hidden = !isExpanded;
                toggleEl.style.transform = isExpanded ? 'rotate(90deg)' : 'rotate(0deg)';
                headerEl.addEventListener('click', () => {
                    isExpanded = !isExpanded;
                    ctx.executeState.taskExpandedById.set(taskId, isExpanded);
                    toggleEl.style.transform = isExpanded ? 'rotate(90deg)' : 'rotate(0deg)';
                    detailsEl.hidden = !isExpanded;
                    ctx.updateExecuteToggleAllButton();
                });

                executeStreamBodyEl.appendChild(cardEl);
            } else if (block.type === 'system') {
                const msg = block.msg;
                const wrap = document.createElement('div');
                wrap.className = 'research-execute-message research-execute-message--system';

                const bubble = document.createElement('div');
                bubble.className = 'research-execute-message-bubble';

                if (msg.title) {
                    const titleEl = document.createElement('div');
                    titleEl.className = 'research-execute-message-title';
                    titleEl.textContent = msg.title;
                    bubble.appendChild(titleEl);
                }

                const bodyEl = document.createElement('div');
                bodyEl.className = 'research-execute-message-body';
                const bodyText = String(msg.body || '').trim() || '—';
                bodyEl.textContent = bodyText.length > 6000 ? bodyText.slice(-6000) : bodyText;
                bubble.appendChild(bodyEl);

                wrap.appendChild(bubble);
                executeStreamBodyEl.appendChild(wrap);
            }
        });

        if (ctx.getExecuteAutoFollow() || (wasNearBottom && executeStreamBodyEl.childElementCount <= 2)) {
            _scrollExecuteStreamToLatest(ctx);
        }
        ctx.updateExecuteToggleAllButton();
        _updateExecuteJumpLatestButton(ctx);
        _syncExecuteElapsedTicker(ctx);
    }

    function initExecuteStreamControls(ctx) {
        if (ctx.executeToggleAllBtnEl) {
            ctx.executeToggleAllBtnEl.addEventListener('click', () => {
                const taskIds = ctx.executeState.order || [];
                if (!taskIds.length) return;
                const allCollapsed = taskIds.every((taskId) => ctx.executeState.taskExpandedById.get(taskId) === false);
                ctx.setAllExecuteTaskExpanded(allCollapsed);
            });
        }
        if (ctx.executeJumpLatestBtnEl) {
            ctx.executeJumpLatestBtnEl.addEventListener('click', () => {
                ctx.setExecuteAutoFollow(true);
                _scrollExecuteStreamToLatest(ctx);
                _updateExecuteJumpLatestButton(ctx);
            });
        }
        if (ctx.executeStreamBodyEl) {
            ctx.executeStreamBodyEl.addEventListener('scroll', () => {
                const nearBottom = _isExecuteStreamNearBottom(ctx);
                ctx.setExecuteAutoFollow(nearBottom);
                _updateExecuteJumpLatestButton(ctx);
            }, { passive: true });
        }
        ctx.updateExecuteToggleAllButton();
        _updateExecuteJumpLatestButton(ctx);
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.researchExecuteRender = {
        renderExecuteStream,
        initExecuteStreamControls,
        _helpers: {
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
        },
    };
})();
