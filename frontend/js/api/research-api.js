/**
 * MAARS Research API helpers.
 * Isolates CRUD/stage endpoints for research workflow.
 */
(function () {
    'use strict';

    const cfg = window.MAARS?.config;
    if (!cfg) return;

    async function _readJson(res) {
        return res.json().catch(() => ({}));
    }

    async function _request(path, options, fallbackMessage) {
        const res = await cfg.fetchWithSession(`${cfg.API_BASE_URL}${path}`, options || {});
        const data = await _readJson(res);
        if (!res.ok) throw new Error(data.error || data.detail || fallbackMessage || 'Request failed');
        return data;
    }

    async function _post(path, body, fallbackMessage) {
        return _request(
            path,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body || {}),
            },
            fallbackMessage,
        );
    }

    async function createResearch(prompt) {
        return _post('/research', { prompt: prompt || '' }, 'Failed to create research');
    }

    async function listResearches() {
        return _request('/research', {}, 'Failed to list researches');
    }

    async function getResearch(researchId) {
        return _request(`/research/${encodeURIComponent(researchId)}`, {}, 'Failed to load research');
    }

    async function runResearch(researchId) {
        return _post(`/research/${encodeURIComponent(researchId)}/run`, { format: 'latex' }, 'Failed to run research');
    }

    async function stopResearch(researchId) {
        return _request(
            `/research/${encodeURIComponent(researchId)}/stop`,
            { method: 'POST' },
            'Failed to stop research',
        );
    }

    async function retryResearch(researchId) {
        return _post(`/research/${encodeURIComponent(researchId)}/retry`, { format: 'latex' }, 'Failed to retry research');
    }

    async function runResearchStage(researchId, stage) {
        return _post(
            `/research/${encodeURIComponent(researchId)}/stage/${encodeURIComponent(stage)}/run`,
            { format: 'latex' },
            'Failed to run research stage',
        );
    }

    async function resumeResearchStage(researchId, stage) {
        return _post(
            `/research/${encodeURIComponent(researchId)}/stage/${encodeURIComponent(stage)}/resume`,
            { format: 'latex' },
            'Failed to resume research stage',
        );
    }

    async function retryResearchStage(researchId, stage) {
        return _post(
            `/research/${encodeURIComponent(researchId)}/stage/${encodeURIComponent(stage)}/retry`,
            { format: 'latex' },
            'Failed to retry research stage',
        );
    }

    async function stopResearchStage(researchId, stage) {
        return _request(
            `/research/${encodeURIComponent(researchId)}/stage/${encodeURIComponent(stage)}/stop`,
            { method: 'POST' },
            'Failed to stop research stage',
        );
    }

    async function deleteResearch(researchId) {
        return _request(
            `/research/${encodeURIComponent(researchId)}`,
            { method: 'DELETE' },
            'Failed to delete research',
        );
    }

    window.MAARS.researchApi = {
        createResearch,
        listResearches,
        getResearch,
        runResearch,
        stopResearch,
        retryResearch,
        runResearchStage,
        resumeResearchStage,
        retryResearchStage,
        stopResearchStage,
        deleteResearch,
    };
})();
