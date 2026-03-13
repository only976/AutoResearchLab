/**
 * MAARS Sidebar - 左侧抽屉（延迟渲染内容，关闭时先隐藏内容）。
 */
(function () {
    'use strict';

    const TRANSITION_MS = 260;
    let _refreshResearchList = null;

    function initSidebar() {
        const sidebar = document.getElementById('appSidebar');
        const toggleBtn = document.getElementById('appSidebarToggle');
        const contentHost = document.getElementById('appSidebarContent');
        if (!sidebar || !toggleBtn || !contentHost) return;

        let isOpen = false;
        let isAnimating = false;
        let transitionToken = 0;

        function openSettingsPage() {
            window.MAARS?.settings?.openSettingsModal?.();
        }

        function syncExpandedState(expanded) {
            toggleBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            sidebar.setAttribute('aria-hidden', expanded ? 'false' : 'true');
            document.body.classList.toggle('app-sidebar-open', expanded);
        }

        async function refreshResearchList() {
            const listEl = document.getElementById('appSidebarResearchList');
            if (!listEl) return;
            listEl.innerHTML = '<div class="app-sidebar-list-empty">Loading…</div>';
            try {
                const api = window.MAARS?.api;
                if (!api?.listResearches) {
                    listEl.innerHTML = '<div class="app-sidebar-list-empty">—</div>';
                    return;
                }
                const data = await api.listResearches();
                const items = data.items || [];
                if (!items.length) {
                    listEl.innerHTML = '<div class="app-sidebar-list-empty">No research yet</div>';
                    return;
                }
                const currentId = window.MAARS?.config?.getCurrentResearchId?.() || '';
                listEl.innerHTML = items.map((it) => {
                    const rid = it.researchId || '';
                    const title = (it.title || rid || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    const stage = it.stage || 'refine';
                    const status = it.stageStatus || 'idle';
                    const badge = `${stage}${status ? ' · ' + status : ''}`;
                    const activeClass = rid && currentId && rid === currentId ? ' is-active' : '';
                    return `<div class="app-sidebar-list-item${activeClass}" data-research-id="${rid}">
                        <div class="app-sidebar-list-item-title">${title || 'Research'}</div>
                        <div class="app-sidebar-list-item-footer">
                            <span class="app-sidebar-badge">${badge}</span>
                            <button type="button" class="app-sidebar-delete-btn" data-research-id="${rid}" data-action="delete" aria-label="Delete research" title="Delete">×</button>
                        </div>
                    </div>`;
                }).join('');
            } catch (e) {
                console.warn('Failed to load research list', e);
                listEl.innerHTML = '<div class="app-sidebar-list-empty">Failed to load</div>';
            }
        }

        async function handleDeleteResearch(researchId) {
            if (!confirm('确定要删除这个研究吗？所有相关数据（包括代码和执行结果）都将被永久删除。')) {
                return;
            }
            
            try {
                const api = window.MAARS?.api;
                if (!api?.deleteResearch) {
                    console.error('deleteResearch API not available');
                    return;
                }
                
                await api.deleteResearch(researchId);
                
                // Refresh the list
                await refreshResearchList();
                
                // If we're currently viewing this research, navigate to home
                const currentId = window.MAARS?.config?.getCurrentResearchId?.() || '';
                if (currentId === researchId) {
                    window.MAARS?.research?.navigateToCreateResearch?.();
                }
            } catch (e) {
                console.error('Failed to delete research:', e);
                alert('删除失败：' + e.message);
            }
        }

        _refreshResearchList = refreshResearchList;

        function renderSidebarContent() {
            if (contentHost.dataset.rendered === 'true') return;
            contentHost.innerHTML = `
                <div class="app-sidebar-inner">
                    <div class="app-sidebar-body" aria-hidden="true">
                        <div class="app-sidebar-section">
                            <div class="app-sidebar-section-title">Research</div>
                            <button type="button" class="app-sidebar-settings-item" id="appSidebarNewResearchBtn">
                                <span class="app-sidebar-settings-glyph" aria-hidden="true">＋</span>
                                <span>新建 research</span>
                            </button>
                            <div id="appSidebarResearchList" class="app-sidebar-list"></div>
                        </div>
                    </div>
                    <button type="button" class="app-sidebar-settings-item" id="appSidebarSettingsBtn">
                        <span class="app-sidebar-settings-glyph" aria-hidden="true">⚙</span>
                        <span>Settings</span>
                    </button>
                </div>
            `;
            contentHost.hidden = false;
            contentHost.dataset.rendered = 'true';

            const newResearchBtn = document.getElementById('appSidebarNewResearchBtn');
            newResearchBtn?.addEventListener('click', () => {
                window.MAARS?.research?.navigateToCreateResearch?.();
                closeSidebar();
            });

            const settingsBtn = document.getElementById('appSidebarSettingsBtn');
            settingsBtn?.addEventListener('click', () => {
                openSettingsPage();
                closeSidebar();
            });

            const listEl = document.getElementById('appSidebarResearchList');
            listEl?.addEventListener('click', (e) => {
                // Handle delete button click
                const deleteBtn = e.target.closest('.app-sidebar-delete-btn');
                if (deleteBtn) {
                    e.stopPropagation();
                    const rid = deleteBtn.getAttribute('data-research-id') || '';
                    if (!rid) return;
                    handleDeleteResearch(rid);
                    return;
                }
                
                // Handle item click
                const item = e.target.closest('.app-sidebar-list-item');
                const rid = item?.getAttribute('data-research-id') || '';
                if (!rid) return;
                window.MAARS?.research?.navigateToResearch?.(rid);
                closeSidebar();
            });

            refreshResearchList();
        }

        function hideSidebarContentNow() {
            contentHost.classList.remove('is-visible');
            contentHost.hidden = true;
            contentHost.dataset.rendered = 'false';
            contentHost.innerHTML = '';
        }

        function waitForTransformEnd(onDone) {
            const token = ++transitionToken;
            const done = () => {
                if (token !== transitionToken) return;
                onDone();
            };
            const handler = (event) => {
                if (event.target !== sidebar || event.propertyName !== 'transform') return;
                sidebar.removeEventListener('transitionend', handler);
                clearTimeout(fallbackId);
                done();
            };
            const fallbackId = window.setTimeout(() => {
                sidebar.removeEventListener('transitionend', handler);
                done();
            }, TRANSITION_MS + 90);
            sidebar.addEventListener('transitionend', handler);
        }

        function openSidebar() {
            if (isOpen) return;
            isOpen = true;
            isAnimating = true;
            syncExpandedState(true);
            sidebar.classList.add('is-open');
            waitForTransformEnd(() => {
                if (!isOpen) {
                    isAnimating = false;
                    return;
                }
                renderSidebarContent();
                contentHost.classList.add('is-visible');
                isAnimating = false;
            });
        }

        function closeSidebar() {
            if (!isOpen && !isAnimating) return;
            isOpen = false;
            hideSidebarContentNow();
            syncExpandedState(false);
            sidebar.classList.remove('is-open');
            isAnimating = true;
            waitForTransformEnd(() => {
                isAnimating = false;
            });
        }

        toggleBtn.addEventListener('click', () => {
            if (isOpen || sidebar.classList.contains('is-open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && (isOpen || sidebar.classList.contains('is-open'))) {
                closeSidebar();
            }
        });
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.sidebar = {
        initSidebar,
        refreshResearchList: () => (_refreshResearchList ? _refreshResearchList().catch(() => {}) : undefined),
    };
})();
