/**
 * MAARS theme - theme switching and Settings modal.
 */
(function () {
    'use strict';
    const cfg = window.MAARS?.config;
    if (!cfg) return;

    async function initTheme() {
        try {
            const raw = await cfg.fetchSettings();
            const theme = raw.theme && cfg.THEMES.includes(raw.theme) ? raw.theme : 'black';
            applyTheme(theme);
        } catch (_) {
            applyTheme('black');
        }
    }

    function applyTheme(theme) {
        if (theme === 'light') {
            document.documentElement.removeAttribute('data-theme');
        } else {
            document.documentElement.setAttribute('data-theme', theme);
        }
    }

    const PHASES = [
        { key: 'atomicity', label: 'Atomicity Check' },
        { key: 'decompose', label: 'Decompose' },
        { key: 'format', label: 'Format' },
        { key: 'quality', label: 'Quality Assess' },
        { key: 'execute', label: 'Task Execute' },
        { key: 'validate', label: 'Task Validate' },
    ];

    let _configState = { aiMode: 'mock', current: '', presets: {} };
    let _activePresetKey = '';

    const MODE_DESCRIPTIONS = {
        mock: {
            title: 'Mock config',
            desc: 'Use mock data, no API key required. Plan and task execution return preset results for quick flow and UI testing.',
        },
        llm: {
            title: 'LLM config',
            desc: 'Plan and task execution both use LLM calls (single-turn). Plan decomposes tasks; task execution generates output once and validates. Select or create preset in Preset.',
            presetNote: true,
        },
        llmagent: {
            title: 'LLM+Agent config',
            desc: 'Plan uses LLM (single-turn atomicity/decompose/format). Task execution uses Agent mode (ReAct-style with tools): ReadArtifact, ReadFile, WriteFile, Finish, ListSkills, LoadSkill.',
            presetNote: true,
        },
        agent: {
            title: 'Agent config',
            desc: 'Plan and task execution both use Agent mode (ReAct-style with tools). Plan: CheckAtomicity, Decompose, FormatTask, AddTasks, etc. Task: ReadArtifact, ReadFile, WriteFile, Finish, ListSkills, LoadSkill.',
            presetNote: true,
        },
    };

    const MODE_PARAMS = {
        mock: [
            { key: 'executionPassProbability', label: 'Execution pass rate', type: 'number', min: 0, max: 1, step: 0.05, default: 0.95, section: 'Mock', tip: 'Random pass probability for mock execution' },
            { key: 'validationPassProbability', label: 'Validation pass rate', type: 'number', min: 0, max: 1, step: 0.05, default: 0.95, section: 'Mock', tip: 'Random pass probability for mock validation' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Mock', tip: 'Max retries after task failure' },
        ],
        llm: [
            { key: 'planLlmTemperature', label: 'Plan Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Plan', tip: 'Temperature for plan LLM calls (atomicity/decompose/format)' },
            { key: 'taskLlmTemperature', label: 'Task Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Task', tip: 'Temperature for task execution LLM output' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Task', tip: 'Max retries after execution/validation failure' },
        ],
        llmagent: [
            { key: 'planLlmTemperature', label: 'Plan Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Plan', tip: 'Temperature for plan LLM (atomicity/decompose/format)' },
            { key: 'taskLlmTemperature', label: 'Task Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Task Agent', tip: 'Temperature for task Agent LLM' },
            { key: 'taskAgentMaxTurns', label: 'Task max turns', type: 'number', min: 1, max: 30, default: 15, section: 'Task Agent', tip: 'Max turns for task Agent loop (incl. tool calls)' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Task Agent', tip: 'Max retries after execution/validation failure' },
        ],
        agent: [
            { key: 'planAgentMaxTurns', label: 'Plan max turns', type: 'number', min: 1, max: 50, default: 30, section: 'Plan Agent', tip: 'Max turns for plan Agent loop' },
            { key: 'planLlmTemperature', label: 'Plan Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Plan Agent', tip: 'Temperature for plan Agent LLM' },
            { key: 'taskLlmTemperature', label: 'Task Temperature', type: 'number', min: 0, max: 2, step: 0.1, default: 0.3, section: 'Task Agent', tip: 'Temperature for task Agent LLM' },
            { key: 'taskAgentMaxTurns', label: 'Task max turns', type: 'number', min: 1, max: 30, default: 15, section: 'Task Agent', tip: 'Max turns for task Agent loop (incl. tool calls)' },
            { key: 'maxFailures', label: 'Max retries', type: 'number', min: 1, max: 10, default: 3, section: 'Task Agent', tip: 'Max retries after execution/validation failure' },
        ],
    };

    function _generateKey(label) {
        const base = (label || 'preset').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'preset';
        let key = base;
        let i = 2;
        while (_configState.presets[key]) { key = base + '_' + i++; }
        return key;
    }

    function _truncate(str, len) {
        if (!str) return '';
        return str.length > len ? str.slice(0, len) + '…' : str;
    }

    const _escapeHtml = (() => {
        const u = window.MAARS?.utils;
        return (s) => (u?.escapeHtml ? u.escapeHtml(s) : (s ? String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : ''));
    })();
    const _escapeHtmlAttr = (() => {
        const u = window.MAARS?.utils;
        return (s) => (u?.escapeHtmlAttr ? u.escapeHtmlAttr(s) : (s ? String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : ''));
    })();

    function _renderPresetSelectItems() {
        const container = document.getElementById('settingsPresetList');
        if (!container) return;
        let html = '';
        Object.keys(_configState.presets).forEach(key => {
            const preset = _configState.presets[key];
            const label = _escapeHtml(preset.label || key);
            const isActive = _configState.current === key;
            const meta = _escapeHtml(preset.model || _truncate(preset.baseUrl || '', 18)) || '—';
            html += `<button type="button" class="settings-preset-item${isActive ? ' active' : ''}" data-item="preset:${key}">
                <span class="settings-preset-item-name">${label}</span>
                <span class="settings-preset-item-meta">${meta}</span>
            </button>`;
        });
        container.innerHTML = html;
    }

    function _syncModeActive() {
        document.querySelectorAll('#settingsModeOptions .settings-option').forEach(el => {
            el.classList.toggle('active', el.dataset.item === _configState.aiMode);
        });
    }

    function _getModeConfig(mode) {
        _configState.modeConfig = _configState.modeConfig || {};
        const defaults = {};
        (MODE_PARAMS[mode] || []).forEach(p => { defaults[p.key] = p.default; });
        const cfg = { ...defaults, ...(_configState.modeConfig[mode] || {}) };
        _configState.modeConfig[mode] = cfg;
        return cfg;
    }

    function _renderModePanel() {
        const container = document.getElementById('settingsModeContent');
        const titleEl = document.getElementById('settingsModeConfigTitle');
        if (!container) return;
        const mode = _configState.aiMode || 'mock';
        const meta = MODE_DESCRIPTIONS[mode] || MODE_DESCRIPTIONS.mock;
        if (titleEl) titleEl.textContent = meta.title;

        const params = MODE_PARAMS[mode] || [];
        const cfg = _getModeConfig(mode);

        let html = `<div class="settings-mode-desc">${_escapeHtml(meta.desc)}</div>`;
        if (params.length > 0) {
            const bySection = {};
            const sectionOrder = [];
            params.forEach(param => {
                const sec = param.section || '';
                if (!bySection[sec]) {
                    bySection[sec] = [];
                    if (sec) sectionOrder.push(sec);
                }
                bySection[sec].push(param);
            });
            sectionOrder.forEach(sec => {
                html += `<div class="settings-mode-section"><h4 class="settings-mode-section-title">${_escapeHtml(sec)}</h4><div class="settings-mode-params">`;
                bySection[sec].forEach(param => {
                    const val = cfg[param.key] !== undefined ? cfg[param.key] : param.default;
                    const attrs = `data-mode="${_escapeHtmlAttr(mode)}" data-key="${_escapeHtmlAttr(param.key)}"`;
                    const tipAttr = param.tip ? ` title="${_escapeHtmlAttr(param.tip)}"` : '';
                    if (param.type === 'checkbox') {
                        const checked = val === true || val === 'true' || val === 1;
                        html += `<div class="settings-field settings-field--checkbox"${tipAttr}>
                            <label for="mode-${param.key}">
                                <input type="checkbox" id="mode-${param.key}" ${attrs} ${checked ? 'checked' : ''} />
                                ${_escapeHtml(param.label)}
                            </label>
                            ${param.tip ? `<span class="settings-param-tip">${_escapeHtml(param.tip)}</span>` : ''}
                        </div>`;
                    } else {
                        const step = param.step !== undefined ? ` step="${param.step}"` : '';
                        const min = param.min !== undefined ? ` min="${param.min}"` : '';
                        const max = param.max !== undefined ? ` max="${param.max}"` : '';
                        html += `<div class="settings-field"${tipAttr}>
                            <label for="mode-${param.key}">${_escapeHtml(param.label)}</label>
                            <input type="${param.type}" id="mode-${param.key}" ${attrs}${min}${max}${step} value="${_escapeHtmlAttr(String(val))}" />
                            ${param.tip ? `<span class="settings-param-tip">${_escapeHtml(param.tip)}</span>` : ''}
                        </div>`;
                    }
                });
                html += '</div></div>';
            });
        }
        if (meta.presetNote) {
            const currentKey = _configState.current;
            const preset = currentKey ? _configState.presets[currentKey] : null;
            const presetLabel = preset ? (preset.label || currentKey) : '—';
            const presetModel = preset ? (preset.model || '') : '';
            html += `<div class="settings-preset-info">
                <span class="settings-preset-info-label">Current preset</span>
                <div class="settings-preset-info-value">
                    <strong>${_escapeHtml(presetLabel)}</strong>
                    ${presetModel ? `<span class="settings-preset-info-model">${_escapeHtml(presetModel)}</span>` : ''}
                </div>
                <p class="settings-preset-hint">Switch or edit preset in Preset</p>
                ${currentKey ? `<button type="button" class="btn-ghost settings-edit-preset-btn" data-preset="${_escapeHtmlAttr(currentKey)}">Edit this preset</button>` : ''}
            </div>`;
        }
        container.innerHTML = html;
    }

    function _readModeFormIntoState() {
        _configState.modeConfig = _configState.modeConfig || {};
        document.querySelectorAll('.settings-mode-content .settings-field input').forEach(inp => {
            const mode = inp.dataset.mode;
            const key = inp.dataset.key;
            if (!mode || !key) return;
            if (!_configState.modeConfig[mode]) _configState.modeConfig[mode] = {};
            const param = (MODE_PARAMS[mode] || []).find(x => x.key === key);
            const defaultVal = param ? param.default : 0;
            if (param?.type === 'checkbox') {
                _configState.modeConfig[mode][key] = inp.checked;
            } else {
                const raw = inp.value.trim();
                if (param?.type === 'number') {
                    const num = parseFloat(raw);
                    _configState.modeConfig[mode][key] = isNaN(num) ? defaultVal : num;
                } else {
                    _configState.modeConfig[mode][key] = raw || defaultVal;
                }
            }
        });
    }

    function _selectItem(itemId) {
        _readFormIntoState();
        const isPreset = itemId.startsWith('preset:');
        const presetKey = isPreset ? itemId.slice(7) : '';
        const isTheme = itemId === 'theme';
        const isDb = itemId === 'db';
        const isExecution = itemId === 'execution';
        const isMode = itemId === 'mode';
        const isPresetNav = itemId === 'preset';
        const isModeOption = ['mock', 'llm', 'llmagent', 'agent'].includes(itemId);

        const navItemId = isPreset ? 'preset' : (isModeOption ? 'mode' : itemId);
        document.querySelectorAll('.settings-nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.item === navItemId);
        });

        if (isTheme) {
            document.getElementById('settingsPanelTheme')?.classList.add('active');
            document.getElementById('settingsPanelDb')?.classList.remove('active');
            document.getElementById('settingsPanelMode')?.classList.remove('active');
            document.getElementById('settingsPanelPreset')?.classList.remove('active');
            _syncThemeOptionsActive();
            _renderPresetSelectItems();
            return;
        }
        if (isDb) {
            document.getElementById('settingsPanelTheme')?.classList.remove('active');
            document.getElementById('settingsPanelDb')?.classList.add('active');
            document.getElementById('settingsPanelExecution')?.classList.remove('active');
            document.getElementById('settingsPanelMode')?.classList.remove('active');
            document.getElementById('settingsPanelPreset')?.classList.remove('active');
            _renderPresetSelectItems();
            return;
        }
        if (isExecution) {
            document.getElementById('settingsPanelTheme')?.classList.remove('active');
            document.getElementById('settingsPanelDb')?.classList.remove('active');
            document.getElementById('settingsPanelExecution')?.classList.add('active');
            document.getElementById('settingsPanelMode')?.classList.remove('active');
            document.getElementById('settingsPanelPreset')?.classList.remove('active');
            const inp = document.getElementById('maxExecutionConcurrency');
            if (inp) inp.value = String(_configState.maxExecutionConcurrency ?? 7);
            return;
        }
        if (isMode) {
            document.getElementById('settingsPanelTheme')?.classList.remove('active');
            document.getElementById('settingsPanelDb')?.classList.remove('active');
            document.getElementById('settingsPanelExecution')?.classList.remove('active');
            document.getElementById('settingsPanelMode')?.classList.add('active');
            document.getElementById('settingsPanelPreset')?.classList.remove('active');
            _syncModeActive();
            _renderModePanel();
            _renderPresetSelectItems();
            return;
        }
        if (isPresetNav) {
            document.getElementById('settingsPanelTheme')?.classList.remove('active');
            document.getElementById('settingsPanelDb')?.classList.remove('active');
            document.getElementById('settingsPanelExecution')?.classList.remove('active');
            document.getElementById('settingsPanelMode')?.classList.remove('active');
            document.getElementById('settingsPanelPreset')?.classList.add('active');
            _populatePresetForm();
            _updateEditPanelVisibility();
            _renderPresetSelectItems();
            return;
        }
        if (isPreset) {
            _activePresetKey = presetKey;
            _configState.current = presetKey;
            _populatePresetForm();
            _updateEditPanelVisibility();
            _renderPresetSelectItems();
            return;
        }
        if (isModeOption) {
            _configState.aiMode = itemId;
            _syncModeActive();
            _renderModePanel();
            return;
        }
    }

    function _syncThemeOptionsActive() {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        document.querySelectorAll('.settings-option[data-theme]').forEach(el => {
            el.classList.toggle('active', el.dataset.theme === current);
        });
    }

    function _updateEditPanelVisibility() {
        const titleEl = document.getElementById('settingsPresetEditTitle');
        if (titleEl) {
            titleEl.textContent = _activePresetKey
                ? 'Edit: ' + (_configState.presets[_activePresetKey]?.label || _activePresetKey)
                : 'Select preset';
        }
    }

    function _renderPhaseCards() {
        const container = document.getElementById('settingsPhaseCards');
        if (!container) return;
        const preset = _configState.presets[_activePresetKey] || {};
        const phases = preset.phases || {};
        let html = '';
        PHASES.forEach(({ key, label }) => {
            const phaseCfg = phases[key] || {};
            html += `<div class="settings-phase-card" data-phase="${key}">
                <span class="settings-phase-label">${_escapeHtml(label)}</span>
                <div class="settings-phase-field">
                    <label>URL</label>
                    <input type="text" class="phase-input" data-phase="${key}" data-field="baseUrl" placeholder="Inherit" value="${_escapeHtmlAttr(phaseCfg.baseUrl || '')}" />
                </div>
                <div class="settings-phase-field">
                    <label>Key</label>
                    <input type="password" class="phase-input" data-phase="${key}" data-field="apiKey" placeholder="Inherit" value="${_escapeHtmlAttr(phaseCfg.apiKey || '')}" autocomplete="off" />
                </div>
                <div class="settings-phase-field">
                    <label>Model</label>
                    <input type="text" class="phase-input" data-phase="${key}" data-field="model" placeholder="Inherit" value="${_escapeHtmlAttr(phaseCfg.model || '')}" />
                </div>
            </div>`;
        });
        container.innerHTML = html;
    }

    function _populatePresetForm() {
        const preset = _configState.presets[_activePresetKey] || {};
        document.getElementById('presetLabel').value = preset.label || '';
        document.getElementById('presetBaseUrl').value = preset.baseUrl || '';
        document.getElementById('presetApiKey').value = preset.apiKey || '';
        document.getElementById('presetModel').value = preset.model || '';
        _renderPhaseCards();
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
        preset.phases = preset.phases || {};
        document.querySelectorAll('.phase-input').forEach(inp => {
            const phase = inp.dataset.phase;
            const field = inp.dataset.field;
            const val = inp.value.trim();
            if (!preset.phases[phase]) preset.phases[phase] = {};
            if (val) preset.phases[phase][field] = val;
            else delete preset.phases[phase][field];
        });
        Object.keys(preset.phases).forEach(k => {
            if (Object.keys(preset.phases[k]).length === 0) delete preset.phases[k];
        });
    }

    function _loadConfig(raw) {
        raw = raw || {};
        const aiMode = raw.aiMode || 'mock';
        const theme = raw.theme && cfg.THEMES.includes(raw.theme) ? raw.theme : 'black';
        const maxExecutionConcurrency = typeof raw.maxExecutionConcurrency === 'number'
            ? raw.maxExecutionConcurrency
            : (parseInt(raw.maxExecutionConcurrency, 10) || 7);

        let presets = {};
        let current = '';
        if (raw.presets && typeof raw.presets === 'object' && Object.keys(raw.presets).length > 0) {
            presets = JSON.parse(JSON.stringify(raw.presets));
            current = raw.current && raw.presets[raw.current] ? raw.current : Object.keys(presets)[0];
        } else {
            current = 'default';
            presets = { default: { label: 'Default', baseUrl: '', apiKey: '', model: '' } };
        }
        const modeConfig = raw.modeConfig && typeof raw.modeConfig === 'object'
            ? JSON.parse(JSON.stringify(raw.modeConfig))
            : {};
        _configState = { theme, aiMode, current, presets, modeConfig, maxExecutionConcurrency };
        _activePresetKey = current || Object.keys(presets)[0];
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
            _renderPresetSelectItems();
            _syncModeActive();
            const keys = Object.keys(_configState.presets);
            const current = _configState.current && keys.includes(_configState.current)
                ? _configState.current
                : keys[0];
            if (current) {
                _activePresetKey = current;
                _configState.current = current;
                _populatePresetForm();
                _updateEditPanelVisibility();
            }
            document.getElementById('settingsPanelTheme')?.classList.add('active');
            document.getElementById('settingsPanelDb')?.classList.remove('active');
            document.getElementById('settingsPanelExecution')?.classList.remove('active');
            document.getElementById('settingsPanelPreset')?.classList.remove('active');
            document.getElementById('settingsPanelMode')?.classList.remove('active');
            _selectItem('theme');
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        }

        document.addEventListener('keydown', (e) => {
            if (e.altKey && e.shiftKey && e.key === 'S') {
                e.preventDefault();
                openSettingsModal();
            }
        });

        nav?.addEventListener('click', (e) => {
            const item = e.target.closest('.settings-nav-item');
            if (item?.dataset?.item) {
                e.preventDefault();
                _selectItem(item.dataset.item);
            }
        });

        document.getElementById('settingsMain')?.addEventListener('click', (e) => {
            const modeOpt = e.target.closest('#settingsModeOptions .settings-option');
            const presetItem = e.target.closest('#settingsPresetList .settings-preset-item');
            const editPresetBtn = e.target.closest('.settings-edit-preset-btn');
            if (modeOpt?.dataset?.item) {
                e.preventDefault();
                _selectItem(modeOpt.dataset.item);
            } else if (presetItem?.dataset?.item) {
                e.preventDefault();
                _selectItem(presetItem.dataset.item);
            } else if (editPresetBtn?.dataset?.preset) {
                e.preventDefault();
                _selectItem('preset');
                _selectItem('preset:' + editPresetBtn.dataset.preset);
            }
        });

        document.querySelectorAll('.settings-option[data-theme]').forEach(btn => {
            btn.addEventListener('click', () => {
                const theme = btn.dataset.theme;
                if (!theme || !cfg.THEMES.includes(theme)) return;
                applyTheme(theme);
                _configState.theme = theme;
                _syncThemeOptionsActive();
            });
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
            if (!confirm('Clear DB? This will delete all plans.')) return;
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

        document.getElementById('settingsPresetAddBtn')?.addEventListener('click', (e) => {
            e.preventDefault();
            _readFormIntoState();
            const key = _generateKey('new');
            _configState.presets[key] = { label: 'New Preset', baseUrl: '', apiKey: '', model: '' };
            _configState.current = key;
            _selectItem('preset:' + key);
        });

        function closeModal() {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }
        window.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.style.display === 'flex') closeModal(); });

        document.getElementById('settingsSaveBtn')?.addEventListener('click', async () => {
            _readFormIntoState();
            _readModeFormIntoState();
            const concInp = document.getElementById('maxExecutionConcurrency');
            const conc = concInp ? parseInt(concInp.value, 10) : 7;
            _configState.maxExecutionConcurrency = (conc >= 1 && conc <= 32) ? conc : 7;
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
            _selectItem('preset:' + remaining[0]);
        });
    }

    window.MAARS.theme = { initTheme, applyTheme, initSettingsModal };
})();
