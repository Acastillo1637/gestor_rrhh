document.addEventListener('DOMContentLoaded', () => {
    const wrap = document.getElementById('portalAccount');
    const button = document.getElementById('portalAccountButton');
    const panel = document.getElementById('portalAccountPanel');
    if (!wrap || !button || !panel) return;

    function close(returnFocus = false) {
        panel.hidden = true;
        button.setAttribute('aria-expanded', 'false');
        if (returnFocus) button.focus();
    }

    button.addEventListener('click', () => {
        const open = panel.hidden;
        panel.hidden = !open;
        button.setAttribute('aria-expanded', String(open));
        if (open) {
            document.getElementById('notificationsWrap')?.classList.remove('open');
            document.getElementById('notificationButton')?.setAttribute('aria-expanded', 'false');
        }
    });
    button.addEventListener('keydown', event => {
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            if (panel.hidden) button.click();
            panel.querySelector('a')?.focus();
        }
    });
    document.addEventListener('click', event => {
        if (!wrap.contains(event.target)) close();
    }, true);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !panel.hidden) {
            event.preventDefault();
            close(true);
        }
    });
    document.addEventListener('focusin', event => {
        if (!wrap.contains(event.target)) close();
    });
});
