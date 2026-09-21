// Complementa la validación del servidor sin intervenir en cargos, salario ni guardado.
document.addEventListener('DOMContentLoaded', () => {
    const inputs = [...document.querySelectorAll('[data-name-part]')];
    if (inputs.length !== 2) return;
    inputs.forEach(input => {
        const id = `${input.dataset.namePart}-errors`;
        const error = document.createElement('div');
        error.id = id;
        error.className = 'errornote';
        error.hidden = true;
        error.setAttribute('aria-live', 'polite');
        input.insertAdjacentElement('afterend', error);
    });
    function validate() {
        const full = inputs.map(input => input.value.trim()).join(' ').trim().replace(/\s+/g, ' ');
        inputs.forEach(input => {
            const part = input.dataset.namePart;
            let message = input.value.trim() ? '' : `Ingresa los ${part} del empleado.`;
            if (!message && part === 'apellidos' && full.length > 150) {
                message = 'Los nombres y apellidos juntos no pueden superar 150 caracteres.';
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
