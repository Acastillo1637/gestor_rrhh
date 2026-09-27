"""Plan reproducible de datos ficticios. No importa ORM ni escribe archivos."""
import calendar
import random
from datetime import date, timedelta


ESTRUCTURA = [
    ('Gerencia y Dirección', 3, [], 'Gerente general', ['Responsable de planificación', 'Asistente de dirección']),
    ('Recursos Humanos', 6, [], 'Gerente de Recursos Humanos', ['Analista de RRHH', 'Analista de selección', 'Especialista en remuneraciones', 'Encargado de asistencia', 'Asistente de capacitación']),
    ('Tecnología', 13, ['renuncio'], 'Gerente de Tecnología', ['Desarrollador', 'Analista QA', 'Especialista de infraestructura', 'Soporte técnico']),
    ('Finanzas y Administración', 7, ['renuncio'], 'Jefe de Finanzas', ['Contador', 'Analista financiero', 'Encargado de tesorería', 'Administrativo']),
    ('Operaciones', 21, ['renuncio', 'despedido', 'despedido'], 'Gerente de Operaciones', ['Supervisor de operaciones', 'Coordinador operativo', 'Ejecutivo operativo']),
    ('Comercial y Atención', 13, ['renuncio'], 'Gerente Comercial', ['Ejecutivo de ventas', 'Especialista de cuentas', 'Ejecutivo de atención']),
    ('Logística', 10, ['despedido'], 'Jefe de Logística', ['Coordinador logístico', 'Operador de bodega', 'Encargado de despacho']),
]
NOMBRES = ['Ana', 'María José', 'José Miguel', 'Daniela', 'Diego', 'Javiera', 'Tomás', 'Francisca', 'Nicolás', 'Camila', 'Valentina', 'Felipe', 'Catalina', 'Matías', 'Paula', 'Benjamín']
APELLIDOS = ['Soto', 'Muñoz', 'Rojas', 'Pérez', 'González', 'Contreras', 'Silva', 'Torres', 'Vargas', 'Fuentes', 'Sepúlveda', 'Espinoza', 'Araya', 'Morales', 'Reyes', 'Navarro', 'Vera', 'Figueroa', 'Salazar', 'Cortés']
SALARIOS_PUESTO = {'junior': 750000, 'semi_senior': 1100000, 'senior': 1650000,
                   'jefatura': 2200000, 'gerencia': 3400000}


def claves_puestos(plan):
    actuales = {(p['departamento'], p['cargo'], p['nivel']) for p in plan}
    anteriores = {(p['departamento'], 'Asistente ' + p['cargo'], 'junior') for p in plan if p['ascenso']}
    return actuales | anteriores


def ajustar_solicitudes(plan, seed, referencia, feriados):
    """Afina solicitudes sin cambiar la población y cronología de la semilla previa."""
    posiciones = {}
    for persona in plan:
        departamento = persona['departamento']
        posicion = posiciones.get(departamento, 0)
        posiciones[departamento] = posicion + 1
        indice = persona['indice']
        seleccion = []
        for permiso in persona['permisos']:
            if permiso['estado'] == 'aprobado':
                conservar = ((permiso['tipo'] == 'vacaciones' and (permiso['fecha_inicio'] - persona['ingreso']).days >= 180)
                             or (permiso['tipo'] == 'medico' and indice % 3 == 0)
                             or (permiso['tipo'] == 'administrativo' and indice % 2 == 0))
            elif permiso['estado'] == 'pendiente':
                # Un subordinado por departamento; tres en Tecnología y el propio Amaro.
                conservar = posicion == 1 or (departamento == 'Tecnología' and posicion in [0, 2, 3])
            else:
                conservar = indice % 6 == 0
            if conservar:
                seleccion.append(permiso)
        persona['permisos'] = seleccion
        asistencias = []
        rng = random.Random(f'{seed}:asistencia:{indice}')
        for dia, estado in persona['asistencias']:
            if dia in feriados:
                estado = 'feriado'
            elif dia.weekday() >= 5:
                estado = 'descanso'
            elif any(p['aprobado'] and p['fecha_inicio'] <= dia <= p['fecha_fin'] for p in seleccion):
                estado = 'permiso'
            elif estado == 'permiso':
                valor = rng.random()
                estado = 'presente' if valor < .96 else ('atraso' if valor < .99 else 'ausente')
            asistencias.append((dia, estado))
        persona['asistencias'] = asistencias
        comentarios = [
            'Cumple los objetivos del período. Mejorar la documentación y seguimiento de acuerdos.',
            'Buen trabajo en equipo y atención a los plazos. Reforzar la planificación semanal.',
            'Muestra autonomía y calidad consistente. Compartir conocimientos con el equipo.',
            'Evolución favorable. Priorizar la revisión de entregables y comunicación de avances.',
        ]
        for numero, evaluacion in enumerate(persona['evaluaciones']):
            evaluacion['feedback'] = comentarios[(indice + numero) % len(comentarios)]


def mes_anterior(fecha, meses):
    ordinal = fecha.year * 12 + fecha.month - 1 - meses
    anio, mes = divmod(ordinal, 12)
    return date(anio, mes + 1, 1)


def construir_plan(seed, referencia, feriados):
    rng = random.Random(seed)
    plan = []
    usados = set()
    for departamento, activos, historicos, jefe, cargos in ESTRUCTURA:
        for posicion, estado in enumerate(['activo'] * activos + historicos):
            indice = len(plan) + 1
            if departamento == 'Tecnología' and posicion == 0:
                nombre, paterno, materno = 'Amaro', 'Castillo', 'Ahumada'
            else:
                while True:
                    nombre, paterno, materno = rng.choice(NOMBRES), rng.choice(APELLIDOS), rng.choice(APELLIDOS)
                    if (nombre, paterno, materno) not in usados:
                        break
            usados.add((nombre, paterno, materno))
            nivel = 'gerencia' if posicion == 0 else ['junior', 'semi_senior', 'senior', 'jefatura'][posicion % 4]
            cargo = jefe if posicion == 0 else cargos[(posicion - 1) % len(cargos)]
            ingreso = referencia - timedelta(days=rng.randint(900, 2500) if posicion == 0 or estado != 'activo' else rng.randint(60, 2200))
            salida = referencia - timedelta(days=rng.randint(35, 160)) if estado != 'activo' else None
            limite = salida or referencia
            sueldo = {'junior': 750000, 'semi_senior': 1100000, 'senior': 1650000, 'jefatura': 2200000, 'gerencia': 3400000}[nivel] + rng.randrange(0, 20) * 25000
            ascenso = ingreso + (limite - ingreso) // 2 if indice % 4 == 0 and (limite - ingreso).days > 365 else None
            previo = sueldo * 9 // 10 if ascenso else sueldo
            rol = 'GERENTES' if posicion == 0 else ('RRHH' if departamento == 'Recursos Humanos' and posicion <= 4 else 'EMPLEADO')
            permisos = []
            for offset, tipo in [(45, 'vacaciones'), (22, 'medico'), (10, 'administrativo')]:
                inicio = limite - timedelta(days=offset)
                fin = inicio + timedelta(days=4 if tipo == 'vacaciones' else 0)
                if inicio >= ingreso:
                    permisos.append(dict(tipo=tipo, fecha_inicio=inicio, fecha_fin=fin, dias=(fin-inicio).days+1, estado='aprobado', aprobado=True))
            if estado == 'activo':
                for n, situacion in [(3, 'pendiente'), (9, 'rechazado')]:
                    inicio = referencia + timedelta(days=n)
                    permisos.append(dict(tipo='administrativo', fecha_inicio=inicio, fecha_fin=inicio, dias=1, estado=situacion, aprobado=False))
            asistencias = []
            dia = max(ingreso, referencia - timedelta(days=365))
            while dia <= min(limite, referencia - timedelta(days=1)):
                if dia in feriados:
                    asistencia = 'feriado'
                elif dia.weekday() >= 5:
                    asistencia = 'descanso'
                elif any(p['aprobado'] and p['fecha_inicio'] <= dia <= p['fecha_fin'] for p in permisos):
                    asistencia = 'permiso'
                else:
                    suerte = rng.random()
                    asistencia = 'presente' if suerte < .96 else ('atraso' if suerte < .99 else 'ausente')
                asistencias.append((dia, asistencia))
                dia += timedelta(days=1)
            nominas = []
            for n in range(11, -1, -1):
                mes = mes_anterior(referencia, n)
                cierre = date(mes.year, mes.month, calendar.monthrange(mes.year, mes.month)[1])
                if cierre < ingreso or mes > limite:
                    continue
                fecha = max(mes, ingreso)
                base = sueldo if not ascenso or fecha >= ascenso else previo
                bono = rng.choice([0, 25000, 50000])
                descuento = base * 18 // 100
                nominas.append(dict(mes_ano=fecha, salario_base=base, bonificacion=bono, descuentos=descuento,
                                    neto=base+bono-descuento, pagado=mes < referencia.replace(day=1) or estado != 'activo'))
            evaluaciones = []
            for anio in range(referencia.year - 1, referencia.year + 1):
                for semestre, fin in [('Primer', date(anio, 6, 30)), ('Segundo', date(anio, 12, 31))]:
                    if ingreso <= fin <= limite:
                        evaluaciones.append(dict(periodo=f'{anio} - {semestre} semestre', puntuacion=rng.choice([3, 4, 4, 5]),
                                                 feedback='Buen cumplimiento de objetivos. Próximo foco: documentación y coordinación del equipo.'))
            plan.append(dict(indice=indice, nombre=nombre, paterno=paterno, materno=materno, departamento=departamento,
                             cargo=cargo, nivel=nivel, estado=estado, ingreso=ingreso, salida=salida,
                             nacimiento=ingreso-timedelta(days=rng.randint(22*365, 40*365)),
                             sueldo=sueldo, previo=previo, ascenso=ascenso, rol=rol, jefe=posicion == 0,
                             permisos=permisos, asistencias=asistencias, nominas=nominas, evaluaciones=evaluaciones))
    ajustar_solicitudes(plan, seed, referencia, feriados)
    return plan
