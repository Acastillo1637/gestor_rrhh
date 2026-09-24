from django.urls import path

from . import views


urlpatterns = [

    # -------------------------------------------------------------------------
    # Autenticación
    # -------------------------------------------------------------------------

    path(
        '',
        views.inicio,
        name='inicio'
    ),

    path(
        'login/',
        views.iniciar_sesion,
        name='login'
    ),
    path(
    'cambiar-contrasena/',
    views.CambiarContrasenaView.as_view(),
    name='cambiar_contrasena'
),

    path(
        'logout/',
        views.cerrar_sesion,
        name='logout'
    ),

    # -------------------------------------------------------------------------
    # Dashboards
    # -------------------------------------------------------------------------

    path(
        'inicio/gestion/',
        views.dashboard_gestion,
        name='dashboard_gestion'
    ),

        path(
        'inicio/gerente/',
        views.dashboard_gerente,
        name='dashboard_gerente'
    ),

    path(
        'inicio/empleado/',
        views.dashboard_empleado,
        name='dashboard_empleado'
    ),

    # -------------------------------------------------------------------------
    # Empleados
    # -------------------------------------------------------------------------

    path(
        'empleados/',
        views.listar_empleados,
        name='listar_empleados'
    ),

    path(
        'empleados/nuevo/',
        views.crear_empleado,
        name='crear_empleado'
    ),

    path(
        'empleados/<int:empleado_id>/editar/',
        views.editar_empleado,
        name='editar_empleado'
    ),

    path(
        'historial-salarial/',
        views.historial_salarial,
        name='historial_salarial'
    ),

    path(
        'empleados/<int:empleado_id>/historial-salarial/',
        views.historial_salarial,
        name='historial_salarial_empleado'
    ),

    # -------------------------------------------------------------------------
    # Gestión de permisos
    # -------------------------------------------------------------------------

    path(
        'permisos/',
        views.gestion_permisos,
        name='gestion_permisos'
    ),

    path(
        'permisos/<int:permiso_id>/aprobar/',
        views.aprobar_permiso,
        name='aprobar_permiso'
    ),

    path(
        'permisos/<int:permiso_id>/rechazar/',
        views.rechazar_permiso,
        name='rechazar_permiso'
    ),

    # -------------------------------------------------------------------------
    # Permisos de empleado
    # -------------------------------------------------------------------------

    path(
        'permisos/solicitar/',
        views.solicitar_permiso,
        name='solicitar_permiso'
    ),

    path(
        'permisos/mis-permisos/',
        views.mis_permisos,
        name='mis_permisos'
    ),

    # -------------------------------------------------------------------------
    # Gestión de nómina
    # -------------------------------------------------------------------------

    path(
        'nomina/',
        views.gestion_nomina,
        name='gestion_nomina'
    ),

    # Endpoint de descarga; el nombre permite enlazarlo desde la plantilla.
    # Descarga PDF con los mismos permisos y filtros que Excel.
    path(
        'nomina/exportar-pdf/',
        views.exportar_nomina_pdf,
        name='exportar_nomina_pdf'
    ),

    path(
        'nomina/exportar-excel/',
        views.exportar_nomina_excel,
        name='exportar_nomina_excel'
    ),

    path(
        'nomina/nueva/',
        views.crear_liquidacion,
        name='crear_liquidacion'
    ),

    path(
        'nomina/<int:liquidacion_id>/pagar/',
        views.marcar_liquidacion_pagada,
        name='marcar_liquidacion_pagada'
    ),


    # -------------------------------------------------------------------------
    # Gestión de asistencia
    # -------------------------------------------------------------------------

    path(
        'asistencia/',
        views.gestion_asistencia,
        name='gestion_asistencia'
    ),


    path(
    'mi-asistencia/',
    views.mi_asistencia,
    name='mi_asistencia'
    ),

    # -------------------------------------------------------------------------
    # Liquidaciones del empleado
    # -------------------------------------------------------------------------

    path(
        'liquidaciones/',
        views.mis_liquidaciones,
        name='mis_liquidaciones'
    ),


    # -------------------------------------------------------------------------
    # Notificaciones
    # -------------------------------------------------------------------------

    path(
        'notificaciones/<int:notificacion_id>/ver/',
        views.ver_notificacion,
        name='ver_notificacion'
    ),

    # Acciones individuales: las vistas exigen POST, sesión y propiedad del aviso.
    path(
        'notificaciones/<int:notificacion_id>/eliminar/',
        views.eliminar_notificacion,
        name='eliminar_notificacion'
    ),

    path(
        'notificaciones/<int:notificacion_id>/marcar-leida/',
        views.marcar_notificacion_leida,
        name='marcar_notificacion_leida'
    ),

    path(
        'notificaciones/marcar-leidas/',
        views.marcar_notificaciones_leidas,
        name='marcar_notificaciones_leidas'
    ),

    # -------------------------------------------------------------------------
    # AJAX
    # -------------------------------------------------------------------------

    path(
        'ajax/puestos/',
        views.obtener_puestos_por_departamento,
        name='obtener_puestos_por_departamento'
    ),
]