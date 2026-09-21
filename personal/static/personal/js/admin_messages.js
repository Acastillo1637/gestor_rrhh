// Django consume los mensajes normalmente; aquí solo cambia su presentación.
document.addEventListener('DOMContentLoaded', () => {
  const content = document.querySelector('[data-admin-messages]');
  if (!content || typeof HTMLDialogElement === 'undefined') return;
  const dialog = document.createElement('dialog');
  if (typeof dialog.showModal !== 'function') return;
  const previousFocus = document.activeElement;
  dialog.className = 'rrhh-admin-message-dialog';
  dialog.setAttribute('aria-labelledby', 'rrhh-admin-message-title');
  dialog.setAttribute('aria-describedby', 'rrhh-admin-message-list');
  document.body.append(dialog);
  dialog.append(content);
  const accept = content.querySelector('[data-accept-admin-messages]');
  accept.hidden = false;
  accept.addEventListener('click', () => dialog.close());
  // showModal mantiene el foco dentro del aviso y bloquea el fondo, incluso con teclado.
  // Escape cierra el diálogo; al cerrar se elimina para no repetir avisos ya consumidos.
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (previousFocus instanceof HTMLElement && previousFocus !== document.body) {
      previousFocus.focus();
    } else {
      document.getElementById('content-start')?.focus();
    }
  });
  dialog.showModal();
  accept.focus();
});
