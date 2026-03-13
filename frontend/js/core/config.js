/**
 * MAARS config - API URLs, storage keys, and config helpers.
 */
(function () {
    'use strict';
    window.MAARS = window.MAARS || {};

    const _isHttpOrigin = (typeof window !== 'undefined' && window.location && /^https?:/.test(window.location.origin));
    const _base = _isHttpOrigin ? '' : 'http://localhost:3001';
    const API_BASE_URL = _base + '/api';
    // When opened via file://, window.location.origin is "null" and cannot be used for Socket.IO.
    // Prefer backend base URL when we are not on an http(s) origin.
    const WS_URL = _base || ((typeof window !== 'undefined' && window.location) ? window.location.origin : 'http://localhost:3001');
    const IDEA_ID_KEY = 'maars-idea-id';
    const PLAN_ID_KEY = 'maars-plan-id';
    const RESEARCH_ID_KEY = 'maars-research-id';
    const SESSION_ID_KEY = 'maars-session-id';
    const SESSION_TOKEN_KEY = 'maars-session-token';
    const THEMES = ['light', 'dark', 'black'];
    let memorySessionId = null;
    let memorySessionToken = null;
    let sessionInitPromise = null;

    function getStoredSessionId() {
        try { return sessionStorage.getItem(SESSION_ID_KEY) || ''; } catch (_) { return memorySessionId || ''; }
    }

    function getStoredSessionToken() {
        try { return sessionStorage.getItem(SESSION_TOKEN_KEY) || ''; } catch (_) { return memorySessionToken || ''; }
    }

    function saveSessionCredentials(sessionId, sessionToken) {
        memorySessionId = sessionId || null;
        memorySessionToken = sessionToken || null;
        try {
            if (sessionId) sessionStorage.setItem(SESSION_ID_KEY, sessionId);
            if (sessionToken) sessionStorage.setItem(SESSION_TOKEN_KEY, sessionToken);
        } catch (_) { /* ignore */ }
    }

    function getSessionId() {
        return getStoredSessionId();
    }

    function getSessionToken() {
        return getStoredSessionToken();
    }

    async function ensureSession(forceRefresh = false) {
        if (!forceRefresh) {
            const existingId = getStoredSessionId();
            const existingToken = getStoredSessionToken();
            if (existingId && existingToken) {
                return { sessionId: existingId, sessionToken: existingToken };
            }
        }
        if (sessionInitPromise) return sessionInitPromise;

        sessionInitPromise = (async () => {
            const response = await fetch(`${API_BASE_URL}/session/init`, { method: 'POST' });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.sessionId || !data.sessionToken) {
                throw new Error(data.error || data.detail || 'Failed to initialize session');
            }
            saveSessionCredentials(data.sessionId, data.sessionToken);
            return { sessionId: data.sessionId, sessionToken: data.sessionToken };
        })();

        try {
            return await sessionInitPromise;
        } finally {
            sessionInitPromise = null;
        }
    }

    function withSessionHeaders(headers, credentials) {
        const merged = new Headers(headers || {});
        const sid = credentials?.sessionId || getSessionId();
        const token = credentials?.sessionToken || getSessionToken();
        if (sid) merged.set('X-MAARS-SESSION-ID', sid);
        if (token) merged.set('X-MAARS-SESSION-TOKEN', token);
        return merged;
    }

    async function fetchWithSession(input, init) {
        const creds = await ensureSession();
        const options = { ...(init || {}) };
        options.headers = withSessionHeaders(options.headers, creds);
        return fetch(input, options);
    }

    function getCurrentIdeaId() {
        try {
            return localStorage.getItem(IDEA_ID_KEY) || '';
        } catch (_) { return ''; }
    }

    function getCurrentPlanId() {
        try {
            return localStorage.getItem(PLAN_ID_KEY) || '';
        } catch (_) { return ''; }
    }

    function setCurrentIdeaId(id) {
        try {
            if (!id) localStorage.removeItem(IDEA_ID_KEY);
            else localStorage.setItem(IDEA_ID_KEY, id);
        } catch (_) {}
    }

    function setCurrentPlanId(id) {
        try {
            if (!id) localStorage.removeItem(PLAN_ID_KEY);
            else localStorage.setItem(PLAN_ID_KEY, id);
        } catch (_) {}
    }

    function getCurrentResearchId() {
        try {
            return localStorage.getItem(RESEARCH_ID_KEY) || '';
        } catch (_) { return ''; }
    }

    function setCurrentResearchId(id) {
        try {
            if (!id) localStorage.removeItem(RESEARCH_ID_KEY);
            else localStorage.setItem(RESEARCH_ID_KEY, id);
        } catch (_) {}
    }

    async function resolvePlanId() {
        const storedIdea = getCurrentIdeaId();
        const storedPlan = getCurrentPlanId();
        if (storedPlan && storedPlan.startsWith('plan_')) return storedPlan;
        if (getCurrentResearchId()) return storedPlan || '';
        try {
            const res = await fetchWithSession(`${API_BASE_URL}/plans`);
            const data = await res.json();
            const items = data.items || [];
            if (items.length > 0) {
                const first = items[0];
                setCurrentIdeaId(first.ideaId || '');
                setCurrentPlanId(first.planId || '');
                return first.planId || '';
            }
        } catch (_) {}
        return storedPlan || '';
    }

    async function resolvePlanIds() {
        const storedIdea = getCurrentIdeaId();
        const storedPlan = getCurrentPlanId();
        if (storedPlan && storedPlan.startsWith('plan_')) return { ideaId: storedIdea, planId: storedPlan };
        if (getCurrentResearchId()) return { ideaId: storedIdea, planId: storedPlan };
        try {
            const res = await fetchWithSession(`${API_BASE_URL}/plans`);
            const data = await res.json();
            const items = data.items || [];
            if (items.length > 0) {
                const first = items[0];
                const ideaId = first.ideaId || '';
                const planId = first.planId || '';
                setCurrentIdeaId(ideaId);
                setCurrentPlanId(planId);
                return { ideaId, planId };
            }
        } catch (_) {}
        return { ideaId: storedIdea, planId: storedPlan };
    }

    async function fetchSettings() {
        const res = await fetchWithSession(`${API_BASE_URL}/settings`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`Settings ${res.status}`);
        const data = await res.json();
        return data.settings != null ? data.settings : {};
    }

    async function saveSettings(settings) {
        const res = await fetchWithSession(`${API_BASE_URL}/settings`, {
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
        RESEARCH_ID_KEY,
        SESSION_ID_KEY,
        SESSION_TOKEN_KEY,
        THEMES,
        getCurrentIdeaId,
        getCurrentPlanId,
        getCurrentResearchId,
        getSessionId,
        getSessionToken,
        ensureSession,
        withSessionHeaders,
        fetchWithSession,
        setCurrentIdeaId,
        setCurrentPlanId,
        setCurrentResearchId,
        resolvePlanId,
        resolvePlanIds,
        fetchSettings,
        saveSettings,
    };
})();
