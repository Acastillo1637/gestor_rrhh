// Complementa la validación del servidor sin intervenir en cargos, salario ni guardado.
document.addEventListener('DOMContentLoaded', () => {
    const inputs = [...document.querySelectorAll('[data-name-part]')];
    if (!inputs.length) return;
    inputs.forEach(input => {
        const id = `${input.dataset.namePart}-errors`;
        const error = document.createElement('div');
        error.id = id;
        error.className = 'errornote';
        error.hidden = true;
        error.setAttribute('aria-live', 'polite');
        input.insertAdjacentElement('afterend', error);
        const describedBy = input.getAttribute('aria-describedby') || '';
        input.setAttribute('aria-describedby', [...new Set(`${describedBy} ${id}`.trim().split(/\s+/))].join(' '));
    });
    function validate() {
        const full = inputs.map(input => input.value.trim()).join(' ').trim().replace(/\s+/g, ' ');
        inputs.forEach(input => {
            const part = input.dataset.namePart;
            let message = input.value.trim() ? '' : `Ingresa ${input.dataset.nameLabel}.`;
            if (!message && part === 'apellido_materno' && full.length > 150) {
                message = 'El nombre completo no puede superar 150 caracteres.';
            }
            input.setCustomValidity(message);
            input.setAttribute('aria-invalid', message ? 'true' : 'false');
            const error = document.getElementById(`${part}-errors`);
            error.textContent = message;
            error.hidden = !message;
        });
    }
    inputs.forEach(input => {
        input.addEventListener('input', validate);
        input.addEventListener('invalid', validate);
    });
});
