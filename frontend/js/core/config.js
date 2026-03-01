/**
 * MAARS config - API URLs, storage keys, and config helpers.
 */
(function () {
    'use strict';
    window.MAARS = window.MAARS || {};

    const _base = (typeof window !== 'undefined' && window.location && /^https?:/.test(window.location.origin))
        ? '' : 'http://localhost:3001';
    const API_BASE_URL = _base + '/api';
    const WS_URL = (typeof window !== 'undefined' && window.location) ? window.location.origin : 'http://localhost:3001';
    const IDEA_ID_KEY = 'maars-idea-id';
    const PLAN_ID_KEY = 'maars-plan-id';
    const THEMES = ['light', 'dark', 'black'];

    function getCurrentIdeaId() {
        try {
            return localStorage.getItem(IDEA_ID_KEY) || 'test';
        } catch (_) { return 'test'; }
    }

    function getCurrentPlanId() {
        try {
            return localStorage.getItem(PLAN_ID_KEY) || 'test';
        } catch (_) { return 'test'; }
    }

    function setCurrentIdeaId(id) {
        try { localStorage.setItem(IDEA_ID_KEY, id); } catch (_) {}
    }

    function setCurrentPlanId(id) {
        try { localStorage.setItem(PLAN_ID_KEY, id); } catch (_) {}
    }

    async function resolvePlanId() {
        const storedIdea = getCurrentIdeaId();
        const storedPlan = getCurrentPlanId();
        if (storedPlan && storedPlan.startsWith('plan_')) return storedPlan;
        try {
            const res = await fetch(`${API_BASE_URL}/plans`);
            const data = await res.json();
            const items = data.items || [];
            if (items.length > 0) {
                const first = items[0];
                setCurrentIdeaId(first.ideaId || 'test');
                setCurrentPlanId(first.planId || 'test');
                return first.planId || 'test';
            }
        } catch (_) {}
        return storedPlan || 'test';
    }

    async function resolvePlanIds() {
        const storedIdea = getCurrentIdeaId();
        const storedPlan = getCurrentPlanId();
        if (storedPlan && storedPlan.startsWith('plan_')) return { ideaId: storedIdea, planId: storedPlan };
        try {
            const res = await fetch(`${API_BASE_URL}/plans`);
            const data = await res.json();
            const items = data.items || [];
            if (items.length > 0) {
                const first = items[0];
                const ideaId = first.ideaId || 'test';
                const planId = first.planId || 'test';
                setCurrentIdeaId(ideaId);
                setCurrentPlanId(planId);
                return { ideaId, planId };
            }
        } catch (_) {}
        return { ideaId: storedIdea, planId: storedPlan };
    }

    async function fetchSettings() {
        const res = await fetch(`${API_BASE_URL}/settings`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`Settings ${res.status}`);
        const data = await res.json();
        return data.settings != null ? data.settings : {};
    }

    async function saveSettings(settings) {
        const res = await fetch(`${API_BASE_URL}/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings || {})
        });
        if (!res.ok) throw new Error('Save failed');
        return await res.json();
    }

    window.MAARS.config = {
        API_BASE_URL,
        WS_URL,
        IDEA_ID_KEY,
        PLAN_ID_KEY,
        THEMES,
        getCurrentIdeaId,
        getCurrentPlanId,
        setCurrentIdeaId,
        setCurrentPlanId,
        resolvePlanId,
        resolvePlanIds,
        fetchSettings,
        saveSettings,
    };
})();
