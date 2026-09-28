(() => {
    const form = document.getElementById('formulario-nomina');
    if (!form) return;
    const empleado = form.elements.empleado;
    const periodo = form.elements.mes_ano;
    const guardar = document.getElementById('guardar-liquidacion');
    const estado = document.getElementById('estado-liquidacion');
    const salario = form.elements.salario_base;
    const simbolo = document.getElementById('salario-simbolo');
    const ayuda = document.getElementById('salario-ayuda');
    function mostrarModo(modo) {
        const esActual = modo === 'actual';
        salario.disabled = false;
        salario.readOnly = esActual;
        salario.type = esActual ? 'text' : 'number';
        simbolo.hidden = esActual;
        salario.required = !esActual;
        salario.placeholder = esActual ? 'Selecciona un empleado' : 'Ingresa el salario base';
        ayuda.textContent = esActual
            ? 'Salario actual del empleado. El servidor lo verificará al guardar.'
            : modo === 'historico'
                ? 'Período histórico: verifica e ingresa el salario base correspondiente a ese mes.'
                : 'Período futuro: verifica e ingresa manualmente el salario base correspondiente.';
    }
    let consulta;
    let version = 0;
    let consultando = false;
    let existe = false;
    function actualizarGuardar() {
        const importe = salario.readOnly ? (salario.dataset.importe || '').replace(',', '.') : salario.value;
        const importeValido = importe !== '' && Number.isFinite(Number(importe)) && Number(importe) >= 0;
        guardar.disabled = consultando || existe || !empleado.value || !periodo.value
            || !importeValido || !form.checkValidity();
    }

    async function comprobar(event) {
        const actual = ++version;
        if (consulta) consulta.abort();
        consultando = false;
        existe = false;
        const mes = periodo.value.slice(0, 7);
        mostrarModo(mes === ayuda.dataset.mesActual ? 'actual' : mes < ayuda.dataset.mesActual ? 'historico' : 'futuro');
        if (event) {
            salario.value = '';
            salario.dataset.importe = '';
            if (salario.readOnly) salario.placeholder = 'Consultando salario…';
        }
        if (!empleado.value || !periodo.value) {
            salario.placeholder = 'Selecciona empleado y período';
            actualizarGuardar();
            estado.textContent = 'Selecciona empleado y período para comprobar si ya existe una liquidación.';
            return;
        }
        consulta = new AbortController();
        consultando = true;
        if (salario.readOnly) salario.placeholder = 'Consultando salario…';
        actualizarGuardar();
        estado.textContent = 'Comprobando liquidación del período…';
        const params = new URLSearchParams({empleado: empleado.value, mes_ano: periodo.value});
        try {
            const response = await fetch(`${form.dataset.estadoUrl}?${params}`, {
                signal: consulta.signal, credentials: 'same-origin',
                headers: {'Accept': 'application/json'},
            });
            if (!response.ok) throw new Error('No disponible');
            const data = await response.json();
            if (actual !== version) return;
            mostrarModo(data.modo_salario);
            if (data.modo_salario === 'actual') {
                salario.value = data.salario_formateado;
                salario.dataset.importe = data.salario_base;
            }
            existe = data.existe;
            consultando = false;
            actualizarGuardar();
            estado.textContent = data.existe
                ? `Liquidación de ${data.periodo} ya generada. Estado: ${data.estado}. No se puede crear otra para este período.`
                : `✓ Sin liquidación generada para ${data.periodo}.`;
        } catch (error) {
            if (actual !== version || error.name === 'AbortError') return;
            if (salario.readOnly) salario.placeholder = 'El salario actual se obtendrá al guardar.';
            consultando = false;
            actualizarGuardar();
            estado.textContent = 'No se pudo consultar el estado. Al guardar, el servidor verificará que no exista una liquidación duplicada.';
        }
    }
    empleado.addEventListener('change', comprobar);
    periodo.addEventListener('change', comprobar);
    form.addEventListener('input', actualizarGuardar);
    form.addEventListener('submit', event => {
        actualizarGuardar();
        if (guardar.disabled) event.preventDefault();
    });
    comprobar();
})();
