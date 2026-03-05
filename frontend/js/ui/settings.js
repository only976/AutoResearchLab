/**
 * MAARS Settings - Settings 弹窗主逻辑（Theme、AI Config、Data）。
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    if (!cfg) return;

    const DEFAULT_AGENT_MODE = { ideaAgent: 'mock', planAgent: 'mock', taskAgent: 'mock', paperAgent: 'mock', ideaRAG: false };
    const DEFAULT_REFLECTION = { enabled: false, maxIterations: 2, qualityThreshold: 70 };
    const PANELS = ['settingsPanelTheme', 'settingsPanelAi', 'settingsPanelDb'];
    let _configState = { agentMode: { ...DEFAULT_AGENT_MODE }, reflection: { ...DEFAULT_REFLECTION }, current: '', presets: {} };
    let _activePresetKey = '';
    let _openSettingsModal = null;

    const _escapeHtml = (() => {
        const u = window.MAARS?.utils;
        return (s) => (u?.escapeHtml ? u.escapeHtml(s) : (s ? String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : ''));
    })();
    const _escapeHtmlAttr = (() => {
        const u = window.MAARS?.utils;
        return (s) => (u?.escapeHtmlAttr ? u.escapeHtmlAttr(s) : (s ? String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : ''));
    })();

    function _generateKey(label) {
        const base = (label || 'preset').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'preset';
        let key = base;
        let i = 2;
        while (_configState.presets[key]) { key = base + '_' + i++; }
        return key;
    }

    function _applyTheme(theme) {
        window.MAARS?.theme?.applyTheme?.(theme);
    }

    function _syncThemeCardsActive() {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        document.querySelectorAll('.settings-theme-card').forEach(el => {
            el.classList.toggle('active', el.dataset.pick === current);
        });
    }

    function _syncMatrixActive() {
        const am = _configState.agentMode || {};
        document.querySelectorAll('#settingsModeMatrix .settings-mode-cell').forEach(el => {
            el.classList.toggle('active', am[el.dataset.row] === el.dataset.col);
        });
    }

    function _syncReflectionUI() {
        const r = _configState.reflection || DEFAULT_REFLECTION;
        const cb = document.getElementById('reflectionEnabled');
        const mi = document.getElementById('reflectionMaxIterations');
        const qt = document.getElementById('reflectionQualityThreshold');
        if (cb) cb.checked = !!r.enabled;
        if (mi) mi.value = r.maxIterations ?? 2;
        if (qt) qt.value = r.qualityThreshold ?? 70;
    }

    function _syncIdeaRAGUI() {
        const am = _configState.agentMode || {};
        const cb = document.getElementById('ideaRAGEnabled');
        if (cb) cb.checked = !!am.ideaRAG;
    }

    function _readIdeaRAGFromUI() {
        const cb = document.getElementById('ideaRAGEnabled');
        _configState.agentMode = _configState.agentMode || { ...DEFAULT_AGENT_MODE };
        _configState.agentMode.ideaRAG = cb ? cb.checked : false;
    }

    function _readReflectionFromUI() {
        const cb = document.getElementById('reflectionEnabled');
        const mi = document.getElementById('reflectionMaxIterations');
        const qt = document.getElementById('reflectionQualityThreshold');
        _configState.reflection = {
            enabled: cb ? cb.checked : false,
            maxIterations: mi ? Math.max(1, Math.min(5, parseInt(mi.value, 10) || 2)) : 2,
            qualityThreshold: qt ? Math.max(0, Math.min(100, parseInt(qt.value, 10) || 70)) : 70,
        };
    }

    function _renderPresetSelectItems() {
        const container = document.getElementById('settingsPresetList');
        if (!container) return;
        let html = '';
        Object.keys(_configState.presets).forEach(key => {
            const preset = _configState.presets[key];
            const label = _escapeHtml(preset.label || key);
            const isActive = _configState.current === key;
            const meta = _escapeHtml(preset.model || '') || '—';
            html += `<button type="button" class="settings-preset-item${isActive ? ' active' : ''}" data-preset-key="${key}">
                <span class="settings-preset-item-name">${label}</span>
                <span class="settings-preset-item-meta">${meta}</span>
            </button>`;
        });
        container.innerHTML = html;
    }

    function _updateEditPanelVisibility() {
        const titleEl = document.getElementById('settingsPresetEditTitle');
        if (titleEl) {
            titleEl.textContent = _activePresetKey
                ? (_configState.presets[_activePresetKey]?.label || _activePresetKey)
                : 'Select preset';
        }
    }

    function _populatePresetForm() {
        const preset = _configState.presets[_activePresetKey] || {};
        document.getElementById('presetLabel').value = preset.label || '';
        document.getElementById('presetBaseUrl').value = preset.baseUrl || '';
        document.getElementById('presetApiKey').value = preset.apiKey || '';
        document.getElementById('presetModel').value = preset.model || '';
        const deleteBtn = document.getElementById('settingsPresetDeleteBtn');
        if (deleteBtn) deleteBtn.style.display = Object.keys(_configState.presets).length > 1 ? '' : 'none';
    }

    function _readFormIntoState() {
        if (!_activePresetKey || !_configState.presets[_activePresetKey]) return;
        const preset = _configState.presets[_activePresetKey];
        preset.label = document.getElementById('presetLabel').value.trim() || preset.label || _activePresetKey;
        preset.baseUrl = document.getElementById('presetBaseUrl').value.trim();
        preset.apiKey = document.getElementById('presetApiKey').value.trim();
        preset.model = document.getElementById('presetModel').value.trim();
        delete preset.phases;
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
        _readFormIntoState();
        _activePresetKey = key;
        _configState.current = key;
        _populatePresetForm();
        _updateEditPanelVisibility();
        _renderPresetSelectItems();
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
                alert('Failed to load settings: ensure backend is running (e.g. uvicorn main:asgi_app) and refresh the page.');
                return;
            }
            _loadConfig(raw);
            _showPanel('settingsPanelTheme');
            _syncThemeCardsActive();
            _syncMatrixActive();
            _syncReflectionUI();
            _syncIdeaRAGUI();
            _renderPresetSelectItems();
            const keys = Object.keys(_configState.presets);
            const current = _configState.current && keys.includes(_configState.current) ? _configState.current : keys[0];
            if (current) {
                _activePresetKey = current;
                _configState.current = current;
                _populatePresetForm();
                _updateEditPanelVisibility();
            }
            modal.style.display = 'flex';
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
                alert('Restore failed: ' + (e.message || e));
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
                alert('Clear failed: ' + (e.message || e));
            }
        });

        function closeModal() {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }
        window.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.style.display === 'flex') closeModal(); });

        document.getElementById('settingsSaveBtn')?.addEventListener('click', async () => {
            _readFormIntoState();
            _readReflectionFromUI();
            _readIdeaRAGFromUI();
            _configState.theme = document.documentElement.getAttribute('data-theme') || 'light';
            try {
                await cfg.saveSettings(_configState);
                closeModal();
            } catch (err) {
                console.error('Save config:', err);
                alert('Save failed: ' + (err.message || 'Unknown error'));
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
