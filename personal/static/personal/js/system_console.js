document.addEventListener('DOMContentLoaded', () => {
  const configs = [
    {buttonId:'notificationButton', wrapId:'notificationsWrap', panelId:'notificationsDropdown'},
    {buttonId:'accountButton', wrapId:'accountWrap', panelId:'accountDropdown'},
  ];
  let active = null;

  function positionPanel(button, panel) {
    const rect = button.getBoundingClientRect();
    const gap = 8;
    panel.style.position = 'fixed';
    panel.style.top = `${rect.bottom + gap}px`;
    panel.style.right = `${Math.max(12, window.innerWidth - rect.right)}px`;
    panel.style.left = 'auto';
    panel.style.zIndex = '2147483647';
  }

  function closeActive() {
    if (!active) return;
    active.panel.classList.remove('portal-open');
    active.button.setAttribute('aria-expanded','false');
    active = null;
  }

  configs.forEach(cfg => {
    const button = document.getElementById(cfg.buttonId);
    const panel = document.getElementById(cfg.panelId);
    if (!button || !panel) return;

    // El panel vive directamente bajo body para que ningún overflow del admin lo recorte.
    document.body.appendChild(panel);

    button.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      const same = active && active.panel === panel;
      closeActive();
      if (same) return;
      positionPanel(button, panel);
      panel.classList.add('portal-open');
      button.setAttribute('aria-expanded','true');
      active = {button, panel};
    });
    panel.addEventListener('click', e => e.stopPropagation());
  });

  document.addEventListener('click', closeActive);
  window.addEventListener('resize', closeActive);
  window.addEventListener('scroll', closeActive, true);

  if (window.location.hash === '#notificaciones') {
    document.getElementById('notificationButton')?.click();
  }
});

// V4: en Usuarios y Roles las acciones masivas van debajo de la tabla.
document.addEventListener('DOMContentLoaded', () => {
  if (!document.body.classList.contains('console-changelist')) return;
  const form = document.getElementById('changelist-form');
  const results = form?.querySelector('.results');
  const actions = form?.querySelector('.actions');
  if (form && results && actions) {
    results.insertAdjacentElement('afterend', actions);
  }

  // Textos más claros sin modificar la lógica nativa de Django.
  const actionSelect = actions?.querySelector('select[name="action"]');
  if (actionSelect && actionSelect.options.length) {
    actionSelect.options[0].textContent = 'Seleccionar acción...';
  }
  const actionButton = actions?.querySelector('button[type="submit"]');
  if (actionButton) actionButton.textContent = 'Aplicar';

  const search = document.getElementById('searchbar');
  if (search) {
    search.placeholder = document.body.classList.contains('console-users')
      ? 'Buscar por usuario, nombre, apellido o correo...'
      : 'Buscar por nombre de grupo...';
  }
});
