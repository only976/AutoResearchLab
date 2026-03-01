/**
 * MAARS Toast - 轻量通知系统
 * API: toast.success(msg), toast.error(msg), toast.warning(msg), toast.info(msg)
 * 可选: toast.show(msg, { type, duration, dismissible })
 */
(function () {
    'use strict';

    window.MAARS = window.MAARS || {};
    const escapeHtml = window.MAARS?.utils?.escapeHtml || ((s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')));

    const DEFAULT_DURATION = 4000;
    const TYPES = ['success', 'error', 'warning', 'info'];

    let container = null;

    function getContainer() {
        if (!container) {
            container = document.getElementById('toastContainer');
            if (!container) {
                container = document.createElement('div');
                container.id = 'toastContainer';
                container.className = 'toast-container';
                container.setAttribute('aria-live', 'polite');
                container.setAttribute('aria-atomic', 'false');
                document.body.appendChild(container);
            }
        }
        return container;
    }

    function createToast(message, options = {}) {
        const {
            type = 'info',
            duration = DEFAULT_DURATION,
            dismissible = true,
        } = options;

        const safeType = TYPES.includes(type) ? type : 'info';
        const el = document.createElement('div');
        el.className = `toast toast--${safeType}`;
        el.setAttribute('role', 'alert');

        const body = document.createElement('div');
        body.className = 'toast-body';
        body.textContent = message;

        el.appendChild(body);

        if (dismissible) {
            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.className = 'toast-close';
            closeBtn.setAttribute('aria-label', 'Close');
            closeBtn.textContent = '×';
            closeBtn.addEventListener('click', () => dismiss(el));
            el.appendChild(closeBtn);
        }

        return el;
    }

    function dismiss(el) {
        if (!el || !el.parentNode) return;
        el.classList.add('is-exiting');
        el.addEventListener('animationend', () => {
            el.remove();
        }, { once: true });
    }

    function show(message, options = {}) {
        if (message == null || String(message).trim() === '') return;

        const el = createToast(String(message).trim(), options);
        getContainer().appendChild(el);

        const { duration = DEFAULT_DURATION } = options;
        if (duration > 0) {
            const t = setTimeout(() => dismiss(el), duration);
            el._toastTimer = t;
        }

        return {
            dismiss: () => {
                if (el._toastTimer) clearTimeout(el._toastTimer);
                dismiss(el);
            },
        };
    }

    const api = {
        show,
        success: (msg, opts) => show(msg, { ...opts, type: 'success' }),
        error: (msg, opts) => show(msg, { ...opts, type: 'error' }),
        warning: (msg, opts) => show(msg, { ...opts, type: 'warning' }),
        info: (msg, opts) => show(msg, { ...opts, type: 'info' }),
    };

    window.MAARS.toast = api;
})();
