/**
 * MAARS Settings preset helpers.
 * Extracted from settings.js to keep modal controller focused.
 */
(function () {
    'use strict';

    function generatePresetKey(label, presets) {
        const base = (label || 'preset').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'preset';
        let key = base;
        let i = 2;
        while ((presets || {})[key]) {
            key = `${base}_${i++}`;
        }
        return key;
    }

    function renderPresetSelectItems(state, escapeHtml) {
        const container = document.getElementById('settingsPresetList');
        if (!container) return;
        const presets = state?.presets || {};
        let html = '';
        Object.keys(presets).forEach((key) => {
            const preset = presets[key] || {};
            const label = escapeHtml(preset.label || key);
            const isActive = state?.current === key;
            const meta = escapeHtml(preset.model || '') || '—';
            html += `<button type="button" class="settings-preset-item${isActive ? ' active' : ''}" data-preset-key="${key}">
                <span class="settings-preset-item-name">${label}</span>
                <span class="settings-preset-item-meta">${meta}</span>
            </button>`;
        });
        container.innerHTML = html;
    }

    function updateEditPanelVisibility(activePresetKey, state) {
        const titleEl = document.getElementById('settingsPresetEditTitle');
        if (!titleEl) return;
        titleEl.textContent = activePresetKey
            ? (state?.presets?.[activePresetKey]?.label || activePresetKey)
            : 'Select preset';
    }

    function populatePresetForm(activePresetKey, state) {
        const preset = state?.presets?.[activePresetKey] || {};
        document.getElementById('presetLabel').value = preset.label || '';
        document.getElementById('presetBaseUrl').value = preset.baseUrl || '';
        document.getElementById('presetApiKey').value = preset.apiKey || '';
        document.getElementById('presetModel').value = preset.model || '';
        const deleteBtn = document.getElementById('settingsPresetDeleteBtn');
        if (deleteBtn) deleteBtn.hidden = Object.keys(state?.presets || {}).length <= 1;
    }

    function readFormIntoState(activePresetKey, state) {
        if (!activePresetKey || !state?.presets?.[activePresetKey]) return;
        const preset = state.presets[activePresetKey];
        preset.label = document.getElementById('presetLabel').value.trim() || preset.label || activePresetKey;
        preset.baseUrl = document.getElementById('presetBaseUrl').value.trim();
        preset.apiKey = document.getElementById('presetApiKey').value.trim();
        preset.model = document.getElementById('presetModel').value.trim();
        delete preset.phases;
    }

    function selectPreset(nextKey, currentActiveKey, state, escapeHtml) {
        readFormIntoState(currentActiveKey, state);
        state.current = nextKey;
        populatePresetForm(nextKey, state);
        updateEditPanelVisibility(nextKey, state);
        renderPresetSelectItems(state, escapeHtml);
        return nextKey;
    }

    window.MAARS = window.MAARS || {};
    window.MAARS.settingsPresetHelpers = {
        generatePresetKey,
        renderPresetSelectItems,
        updateEditPanelVisibility,
        populatePresetForm,
        readFormIntoState,
        selectPreset,
    };
})();
