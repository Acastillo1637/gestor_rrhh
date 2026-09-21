// El servidor devuelve el mismo fragmento que usa el layout: no se duplican contadores.
(() => {
    const panel = document.getElementById('notificationsDropdown');
    const bell = document.getElementById('notificationButton');
    const wrap = document.getElementById('notificationsWrap');
    const dialog = document.getElementById('deleteNotificationDialog');
    if (!panel || !dialog) return;
    const status = document.getElementById('notificationActionStatus');
    const error = document.getElementById('notificationDeleteError');
    const cancel = dialog.querySelector('[data-cancel-delete]');
    const remove = dialog.querySelector('[data-confirm-delete]');
    // Formulario elegido para borrar: abrir el modal todavía no envía ninguna petición.
    let pending = null;
    // Bloquea dobles clics y acciones simultáneas que podrían desordenar las respuestas.
    let busy = false;

    // Cancelar o pulsar Escape conserva los datos y vuelve al desplegable.
    function openPanel() {
        if (panel.hasAttribute('data-admin-notifications')) {
            // El admin mueve el panel al body; su controlador mantiene posición y estado.
            document.dispatchEvent(new Event('notifications:open'));
        } else {
            wrap.classList.add('open');
            bell.setAttribute('aria-expanded', 'true');
        }
    }
    function closeDialog() {
        if (busy) return;
        dialog.close();
        pending = null;
        openPanel();
    }
    cancel.addEventListener('click', closeDialog);
    dialog.addEventListener('cancel', event => {
        event.preventDefault();
        closeDialog();
    });

    // Envía la acción, aplica el estado confirmado por Django y recupera los controles.
    async function send(form) {
        if (busy) return;
        busy = true;
        status.textContent = '';
        error.textContent = '';
        panel.setAttribute('aria-busy', 'true');
        panel.querySelectorAll('button').forEach(button => button.disabled = true);
        remove.disabled = cancel.disabled = true;
        try {
            // FormData incluye csrfmiddlewaretoken; same-origin envía la sesión del usuario.
            const response = await fetch(form.action, {
                method: 'POST', body: new FormData(form), credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }
            });
            // Una sesión expirada puede redirigir al login: no tratar su HTML como éxito.
            if (!response.ok || response.redirected) throw new Error('request');
            const data = await response.json();
            if (typeof data.html !== 'string' || !Number.isInteger(data.unread)) throw new Error('response');
            // Solo se reemplaza el panel después de confirmar el éxito del POST.
            panel.innerHTML = data.html;
            // Usar el total del servidor evita restar dos veces al borrar un aviso ya leído.
            let badge = bell.querySelector('.notification-badge');
            if (data.unread > 0) {
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'notification-badge';
                    bell.append(badge);
                }
                badge.textContent = data.unread;
            } else if (badge) badge.remove();
            if (dialog.open) dialog.close();
            pending = null;
            openPanel();
            bell.focus();
            status.textContent = 'Notificaciones actualizadas.';
        } catch (_) {
            // Conservar la lista ante errores; el mensaje permite recargar y comprobar el estado.
            const message = 'No se pudo completar la acción. Revisa tu conexión o recarga la página e inténtalo de nuevo.';
            (dialog.open ? error : status).textContent = message;
        } finally {
            busy = false;
            panel.removeAttribute('aria-busy');
            panel.querySelectorAll('button').forEach(button => button.disabled = false);
            remove.disabled = cancel.disabled = false;
        }
    }
    // Delegación: las acciones siguen funcionando al renovar el fragmento HTML.
    panel.addEventListener('submit', event => {
        const form = event.target.closest('[data-notification-form]');
        if (!form) return;
        event.preventDefault();
        if (busy) return;
        if (form.hasAttribute('data-delete-notification')) {
            pending = form;
            error.textContent = '';
            dialog.showModal();
            // El diálogo nativo HTML retiene el foco; Cancelar es la opción inicial segura.
            cancel.focus();
        } else send(form);
    });
    remove.addEventListener('click', () => { if (pending) send(pending); });
})();
