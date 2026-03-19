/**
 * MAARS Settings - Settings 弹窗主逻辑（Theme、AI Config、Data）。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    if (!cfg) return;
    const toast = window.MAARS.toast;
    const presetHelpers = window.MAARS?.settingsPresetHelpers || {};
    const syncHelpers = window.MAARS?.settingsSyncHelpers || {};

    const DEFAULT_AGENT_MODE = { ideaAgent: 'mock', planAgent: 'mock', taskAgent: 'mock', paperAgent: 'mock', ideaRAG: false, literatureSource: 'openalex' };
    const DEFAULT_REFLECTION = { enabled: false, maxIterations: 2, qualityThreshold: 70 };
    const PANELS = ['settingsPanelTheme', 'settingsPanelAi', 'settingsPanelDb'];
    let _configState = { agentMode: { ...DEFAULT_AGENT_MODE }, reflection: { ...DEFAULT_REFLECTION }, current: '', presets: {} };
    let _activePresetKey = '';
    let _openSettingsModal = null;

    const _escapeHtml = (() => {
        const u = window.MAARS?.utils;
        return (s) => (u?.escapeHtml ? u.escapeHtml(s) : (s ? String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : ''));
    })();
    function _generateKey(label) {
        if (typeof presetHelpers.generatePresetKey === 'function') {
            return presetHelpers.generatePresetKey(label, _configState.presets);
        }
        return 'preset';
    }

    function _applyTheme(theme) {
        window.MAARS?.theme?.applyTheme?.(theme);
    }

    function _syncThemeCardsActive() {
        syncHelpers.syncThemeCardsActive?.();
    }

    function _syncMatrixActive() {
        syncHelpers.syncMatrixActive?.(_configState.agentMode || {});
    }

    function _syncReflectionUI() {
        syncHelpers.syncReflectionUI?.(_configState.reflection || DEFAULT_REFLECTION);
    }

    function _syncIdeaRAGUI() {
        syncHelpers.syncIdeaRAGUI?.(_configState.agentMode || {});
    }

    function _syncLiteratureSourceUI() {
        syncHelpers.syncLiteratureSourceUI?.(_configState.agentMode || {});
    }

    function _readIdeaRAGFromUI() {
        _configState.agentMode = syncHelpers.readIdeaRAGFromUI?.(_configState.agentMode, DEFAULT_AGENT_MODE)
            || { ...DEFAULT_AGENT_MODE, ...(_configState.agentMode || {}) };
    }

    function _readLiteratureSourceFromUI() {
        _configState.agentMode = syncHelpers.readLiteratureSourceFromUI?.(_configState.agentMode, DEFAULT_AGENT_MODE)
            || { ...DEFAULT_AGENT_MODE, ...(_configState.agentMode || {}) };
    }

    function _readReflectionFromUI() {
        _configState.reflection = syncHelpers.readReflectionFromUI?.(DEFAULT_REFLECTION)
            || { ...DEFAULT_REFLECTION };
    }

    function _renderPresetSelectItems() {
        presetHelpers.renderPresetSelectItems?.(_configState, _escapeHtml);
    }

    function _updateEditPanelVisibility() {
        presetHelpers.updateEditPanelVisibility?.(_activePresetKey, _configState);
    }

    function _populatePresetForm() {
        presetHelpers.populatePresetForm?.(_activePresetKey, _configState);
    }

    function _readFormIntoState() {
        presetHelpers.readFormIntoState?.(_activePresetKey, _configState);
    }

    function _loadConfig(raw) {
        raw = raw || {};
        const agentMode = raw.agentMode && typeof raw.agentMode === 'object'
            ? { ...DEFAULT_AGENT_MODE, ...raw.agentMode }
            : { ...DEFAULT_AGENT_MODE };
        const theme = raw.theme && cfg.THEMES.includes(raw.theme) ? raw.theme : 'black';

        let presets = {};
        let current = '';
        if (raw.presets && typeof raw.presets === 'object' && Object.keys(raw.presets).length > 0) {
            presets = JSON.parse(JSON.stringify(raw.presets));
            current = raw.current && raw.presets[raw.current] ? raw.current : Object.keys(presets)[0];
        } else {
            current = 'default';
            presets = { default: { label: 'Default', baseUrl: '', apiKey: '', model: '' } };
        }
        const reflection = raw.reflection && typeof raw.reflection === 'object'
            ? { ...DEFAULT_REFLECTION, ...raw.reflection }
            : { ...DEFAULT_REFLECTION };
        if (agentMode.ideaRAG === undefined) agentMode.ideaRAG = false;
        if (agentMode.literatureSource === undefined) {
            agentMode.literatureSource = 'openalex';
        } else {
            const source = String(agentMode.literatureSource || '').trim().toLowerCase();
            agentMode.literatureSource = (source === 'arxiv') ? 'arxiv' : 'openalex';
        }
        _configState = { theme, agentMode, reflection, current, presets };
        _activePresetKey = current || Object.keys(presets)[0];
    }

    function _showPanel(panelId) {
        PANELS.forEach(id => {
            document.getElementById(id)?.classList.toggle('active', id === panelId);
        });
        const navKey = panelId.replace('settingsPanel', '').toLowerCase();
        document.querySelectorAll('.settings-nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.item === navKey);
        });
    }

    function _selectPreset(key) {
        _activePresetKey = presetHelpers.selectPreset?.(key, _activePresetKey, _configState, _escapeHtml) || key;
    }

    function initSettingsModal() {
        const modal = document.getElementById('settingsModal');
        const deleteBtn = document.getElementById('settingsPresetDeleteBtn');
        const nav = document.querySelector('.settings-nav');

        async function openSettingsModal() {
            let raw;
            try {
                raw = await cfg.fetchSettings();
            } catch (e) {
                console.error('Failed to load config:', e);
                toast.error('Failed to load settings: ensure backend is running (e.g. uvicorn main:asgi_app) and refresh the page.', { duration: 8000 });
                return;
            }
            _loadConfig(raw);
            _showPanel('settingsPanelTheme');
            _syncThemeCardsActive();
            _syncMatrixActive();
            _syncReflectionUI();
            _syncIdeaRAGUI();
            _syncLiteratureSourceUI();
            _renderPresetSelectItems();
            const keys = Object.keys(_configState.presets);
            const current = _configState.current && keys.includes(_configState.current) ? _configState.current : keys[0];
            if (current) {
                _activePresetKey = current;
                _configState.current = current;
                _populatePresetForm();
                _updateEditPanelVisibility();
            }
            modal.classList.add('is-open');
            document.body.style.overflow = 'hidden';
        }
        _openSettingsModal = openSettingsModal;

        document.addEventListener('keydown', (e) => {
            // Alt+Shift+S (Win/Linux) or Cmd+Shift+S (Mac)
            const mod = e.altKey || e.metaKey;
            if (mod && e.shiftKey && e.key === 'S') {
                e.preventDefault();
                openSettingsModal();
            }
        });

        nav?.addEventListener('click', (e) => {
            const item = e.target.closest('.settings-nav-item');
            if (!item?.dataset?.item) return;
            e.preventDefault();
            _readFormIntoState();
            const id = item.dataset.item;
            if (id === 'theme') {
                _showPanel('settingsPanelTheme');
                _syncThemeCardsActive();
            } else if (id === 'ai') {
                _showPanel('settingsPanelAi');
                _syncMatrixActive();
                _syncIdeaRAGUI();
                _syncLiteratureSourceUI();
                _renderPresetSelectItems();
            } else if (id === 'db') {
                _showPanel('settingsPanelDb');
            }
        });

        document.getElementById('settingsMain')?.addEventListener('click', (e) => {
            const themeCard = e.target.closest('.settings-theme-card');
            const modeCell = e.target.closest('#settingsModeMatrix .settings-mode-cell');
            const presetItem = e.target.closest('.settings-preset-item');
            const addBtn = e.target.closest('#settingsPresetAddBtn');

            if (themeCard?.dataset?.pick) {
                e.preventDefault();
                const theme = themeCard.dataset.pick;
                if (!cfg.THEMES.includes(theme)) return;
                _applyTheme(theme);
                _configState.theme = theme;
                _syncThemeCardsActive();
            } else if (modeCell?.dataset?.row && modeCell?.dataset?.col) {
                e.preventDefault();
                _configState.agentMode = _configState.agentMode || { ...DEFAULT_AGENT_MODE };
                _configState.agentMode[modeCell.dataset.row] = modeCell.dataset.col;
                _syncMatrixActive();
            } else if (presetItem?.dataset?.presetKey) {
                e.preventDefault();
                _selectPreset(presetItem.dataset.presetKey);
            } else if (addBtn) {
                e.preventDefault();
                _readFormIntoState();
                const key = _generateKey('new');
                _configState.presets[key] = { label: 'New Preset', baseUrl: '', apiKey: '', model: '' };
                _selectPreset(key);
            }
        });

        document.getElementById('settingsRestoreBtn')?.addEventListener('click', async () => {
            const api = window.MAARS?.api;
            if (!api?.restoreRecentPlan) return;
            const btn = document.getElementById('settingsRestoreBtn');
            const origText = btn?.textContent;
            if (btn) { btn.disabled = true; btn.textContent = 'Restoring...'; }
            try {
                await api.restoreRecentPlan();
                if (btn) { btn.textContent = 'Restored'; }
                setTimeout(() => {
                    if (btn) { btn.disabled = false; btn.textContent = origText || 'Restore'; }
                }, 1500);
            } catch (e) {
                console.error('Restore failed:', e);
                toast.error('Restore failed: ' + (e.message || e));
                if (btn) { btn.disabled = false; btn.textContent = origText || 'Restore'; }
            }
        });

        document.getElementById('settingsClearDbBtn')?.addEventListener('click', async () => {
            if (!confirm('This will delete all ideas, plans, and execution data. Continue?')) return;
            try {
                const api = window.MAARS?.api;
                if (!api?.clearDb) return;
                await api.clearDb();
                try { localStorage.removeItem(cfg?.PLAN_ID_KEY || 'maars-plan-id'); } catch (_) {}
                location.reload();
            } catch (e) {
                console.error('Clear DB failed:', e);
                toast.error('Clear failed: ' + (e.message || e));
            }
        });

        function closeModal() {
            modal.classList.remove('is-open');
            document.body.style.overflow = '';
        }
        window.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.classList.contains('is-open')) closeModal(); });

        document.getElementById('settingsSaveBtn')?.addEventListener('click', async () => {
            _readFormIntoState();
            _readReflectionFromUI();
            _readIdeaRAGFromUI();
            _readLiteratureSourceFromUI();
            _configState.theme = document.documentElement.getAttribute('data-theme') || 'light';
            try {
                await cfg.saveSettings(_configState);
                closeModal();
            } catch (err) {
                console.error('Save config:', err);
                toast.error('Save failed: ' + (err.message || 'Unknown error'));
            }
        });

        deleteBtn?.addEventListener('click', () => {
            const keys = Object.keys(_configState.presets);
            if (keys.length <= 1) return;
            delete _configState.presets[_activePresetKey];
            const remaining = Object.keys(_configState.presets);
            _configState.current = remaining[0];
            _selectPreset(remaining[0]);
        });
    }

    function openSettingsModal() {
        return _openSettingsModal?.();
    }

    window.MAARS.settings = { initSettingsModal, openSettingsModal };
})();
