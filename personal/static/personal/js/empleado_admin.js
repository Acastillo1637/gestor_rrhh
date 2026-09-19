document.addEventListener('DOMContentLoaded', function () {

    const departamento = document.getElementById('id_departamento_selector');
    const cargo = document.getElementById('id_cargo_selector');
    const salario = document.getElementById('id_salario_mensual');

    if (!departamento || !cargo) {
        return;
    }

    function cargarPuestos(departamentoId) {

        cargo.innerHTML = '';

        if (!departamentoId) {

            const opcion = document.createElement('option');
            opcion.value = '';
            opcion.textContent = 'Seleccione primero un departamento';

            cargo.appendChild(opcion);
            cargo.disabled = true;

            return;
        }

        cargo.disabled = true;

        const cargando = document.createElement('option');
        cargando.value = '';
        cargando.textContent = 'Cargando cargos...';

        cargo.appendChild(cargando);

        fetch(
            '/ajax/puestos/?departamento_id=' +
            encodeURIComponent(departamentoId)
        )
            .then(response => {

                if (!response.ok) {
                    throw new Error('Error al obtener los cargos');
                }

                return response.json();
            })

            .then(puestos => {

                cargo.innerHTML = '';

                const opcionInicial = document.createElement('option');
                opcionInicial.value = '';
                opcionInicial.textContent = 'Seleccione un cargo';

                cargo.appendChild(opcionInicial);

                puestos.forEach(puesto => {

                    const opcion = document.createElement('option');

                    opcion.value = puesto.nombre;
                    opcion.textContent = puesto.nombre;

                    opcion.dataset.salario = puesto.salario_base;

                    cargo.appendChild(opcion);
                });

                cargo.disabled = false;
            })

            .catch(error => {

                console.error(error);

                cargo.innerHTML = '';

                const opcionError = document.createElement('option');

                opcionError.value = '';
                opcionError.textContent = 'Error al cargar cargos';

                cargo.appendChild(opcionError);
            });
    }


    departamento.addEventListener('change', function () {

        cargarPuestos(this.value);

        if (salario) {
            salario.value = '';
        }
    });


    cargo.addEventListener('change', function () {

        if (!salario) {
            return;
        }

        const opcionSeleccionada =
            cargo.options[cargo.selectedIndex];

        if (
            opcionSeleccionada &&
            opcionSeleccionada.dataset.salario
        ) {
            salario.value =
                opcionSeleccionada.dataset.salario;
        }
    });


    // Al crear un empleado, el cargo comienza bloqueado.
    // Si estamos editando uno existente, se mantiene disponible.
    if (!departamento.value) {
        cargo.disabled = true;
    }
});