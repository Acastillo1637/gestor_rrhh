# -----------------------------------------------------------------------------
# Configuración del panel de administración del sistema de RRHH.
# -----------------------------------------------------------------------------

from django.contrib import admin, messages
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.contrib.admin.models import LogEntry
import json
from django import forms
from .forms import EvaluacionForm
from django.utils import timezone
from django.utils.html import format_html
from django.urls import path
from django.template.response import TemplateResponse
from django.core.paginator import Paginator
from django.db.models import Q

from .models import (
    Empleado,
    HistorialSalario,
    Departamento,
    Puesto,
    EmpleadoPuesto,
    Salario,
    Asistencia,
    Permiso,
    Evaluacion,
    Notificacion,
)


# -----------------------------------------------------------------------------
# Personalización general del panel admin
# -----------------------------------------------------------------------------

admin.site.site_header = "Gestor RRHH"
admin.site.site_title = "Gestor RRHH"
admin.site.index_title = "Administración del Sistema"
admin.site.site_url = "/inicio/gestion/"


_original_admin_index = admin.site.index


def system_admin_index(request, extra_context=None):

    extra_context = extra_context or {}

    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    total_groups = Group.objects.count()
    audit_events = LogEntry.objects.count()

    role_stats = []

    for group in Group.objects.all().order_by("name"):
        role_stats.append({
            "name": group.name,
            "total": group.user_set.count(),
        })

    superusers = User.objects.filter(
        is_superuser=True
    ).count()

    if superusers:
        role_stats.append({
            "name": "Superusuarios",
            "total": superusers,
        })

    extra_context.update({
        "system_stats": {
            "users": total_users,
            "active_users": active_users,
            "groups": total_groups,
            "audit_events": audit_events,
        },

        "role_stats": role_stats,

        "recent_actions": (
            LogEntry.objects
            .select_related(
                "user",
                "content_type"
            )
            .order_by("-action_time")[:6]
        ),
    })

    return _original_admin_index(
        request,
        extra_context=extra_context
    )


admin.site.index = system_admin_index

# =============================================================================
# AUDITORÍA DEL SISTEMA
# =============================================================================

def detalle_auditoria(registro):
    """
    Convierte el change_message interno de Django
    en un texto entendible para la auditoría.
    """

    if registro.action_flag == 1:
        return "Registro creado"

    if registro.action_flag == 3:
        return "Registro eliminado"

    if not registro.change_message:
        return "Registro modificado"

    try:
        cambios = json.loads(registro.change_message)
        detalles = []

        for cambio in cambios:

            if "changed" in cambio:
                campos = cambio["changed"].get("fields", [])

                if campos:
                    detalles.append(
                        "Se modificó: " + ", ".join(campos)
                    )

            elif "added" in cambio:
                detalles.append("Registro relacionado agregado")

            elif "deleted" in cambio:
                detalles.append("Registro relacionado eliminado")

        if detalles:
            return " · ".join(detalles)

    except (json.JSONDecodeError, TypeError):
        pass

    return registro.change_message


def system_audit_view(request):
    """
    Vista de auditoría de la consola administrativa.

    Utiliza el registro interno de Django (LogEntry) para mostrar
    las acciones realizadas desde el panel de administración.
    """

    if not request.user.is_staff:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    registros = (
        LogEntry.objects
        .select_related(
            "user",
            "content_type",
        )
        .order_by("-action_time")
    )

    # -------------------------------------------------------------------------
    # FILTROS
    # -------------------------------------------------------------------------

    busqueda = request.GET.get(
        "q",
        ""
    ).strip()

    accion = request.GET.get(
        "accion",
        ""
    ).strip()

    usuario_id = request.GET.get(
        "usuario",
        ""
    ).strip()

    modulo = request.GET.get(
        "modulo",
        ""
    ).strip()

    # -------------------------------------------------------------------------
    # BÚSQUEDA GENERAL
    # -------------------------------------------------------------------------

    if busqueda:

        registros = registros.filter(
            Q(user__username__icontains=busqueda)
            |
            Q(user__first_name__icontains=busqueda)
            |
            Q(user__last_name__icontains=busqueda)
            |
            Q(object_repr__icontains=busqueda)
            |
            Q(change_message__icontains=busqueda)
            |
            Q(content_type__model__icontains=busqueda)
        )

    # -------------------------------------------------------------------------
    # FILTRO POR ACCIÓN
    #
    # Django:
    # 1 = creación
    # 2 = modificación
    # 3 = eliminación
    # -------------------------------------------------------------------------

    if accion in {"1", "2", "3"}:

        registros = registros.filter(
            action_flag=int(accion)
        )

    # -------------------------------------------------------------------------
    # FILTRO POR USUARIO
    # -------------------------------------------------------------------------

    if usuario_id.isdigit():

        registros = registros.filter(
            user_id=int(usuario_id)
        )

    # -------------------------------------------------------------------------
    # FILTRO POR MÓDULO
    # -------------------------------------------------------------------------

    if modulo:

        registros = registros.filter(
            content_type__app_label=modulo
        )

    # -------------------------------------------------------------------------
    # DATOS PARA LOS FILTROS
    # -------------------------------------------------------------------------

    usuarios_admin = (
        User.objects
        .filter(
            logentry__isnull=False
        )
        .distinct()
        .order_by("username")
    )

    modulos = (
        LogEntry.objects
        .select_related("content_type")
        .values_list(
            "content_type__app_label",
            flat=True
        )
        .distinct()
        .order_by("content_type__app_label")
    )

    # -------------------------------------------------------------------------
    # MÉTRICAS
    # -------------------------------------------------------------------------

    total_eventos = registros.count()

    total_creaciones = registros.filter(
        action_flag=1
    ).count()

    total_modificaciones = registros.filter(
        action_flag=2
    ).count()

    total_eliminaciones = registros.filter(
        action_flag=3
    ).count()

    # -------------------------------------------------------------------------
    # PAGINACIÓN
    # -------------------------------------------------------------------------

    paginador = Paginator(
        registros,
        20
    )

    numero_pagina = request.GET.get(
        "page"
    )

    pagina = paginador.get_page(
        numero_pagina
    )

    # -------------------------------------------------------------------------
    # DETALLE LEGIBLE PARA AUDITORÍA
    # -------------------------------------------------------------------------

    for registro in pagina.object_list:
        registro.detalle_legible = detalle_auditoria(registro)

    # -------------------------------------------------------------------------
    # CONTEXTO
    # -------------------------------------------------------------------------

    contexto = {
        **admin.site.each_context(request),

        "title": "Auditoría del sistema",

        "pagina": pagina,

        "usuarios_admin": usuarios_admin,

        "modulos": modulos,

        "busqueda": busqueda,

        "accion_seleccionada": accion,

        "usuario_seleccionado": usuario_id,

        "modulo_seleccionado": modulo,

        "total_eventos": total_eventos,

        "total_creaciones": total_creaciones,

        "total_modificaciones": total_modificaciones,

        "total_eliminaciones": total_eliminaciones,
    }

    return TemplateResponse(
        request,
        "admin/auditoria.html",
        contexto,
    )


# =============================================================================
# URL PERSONALIZADA DEL ADMIN
# =============================================================================

_original_get_urls = admin.site.get_urls


def system_admin_get_urls():

    urls_personalizadas = [
        path(
            "auditoria/",
            admin.site.admin_view(
                system_audit_view
            ),
            name="system_audit",
        ),
    ]

    return (
        urls_personalizadas
        + _original_get_urls()
    )


admin.site.get_urls = system_admin_get_urls

# =============================================================================
# FORMULARIO ADMIN DE EMPLEADO
# =============================================================================

class EmpleadoAdminForm(forms.ModelForm):

    departamento_selector = forms.ModelChoiceField(
        queryset=Departamento.objects.all().order_by('nombre'),
        label='Departamento',
        required=True,
        empty_label='Seleccione un departamento'
    )

    cargo_selector = forms.ChoiceField(
        label='Cargo',
        required=True,
        choices=[
            ('', 'Seleccione primero un departamento')
        ]
    )

    class Meta:
        model = Empleado
        exclude = (
            'cargo',
            'departamento',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # -------------------------------------------------------------
        # Edición de empleado existente
        # -------------------------------------------------------------
        if self.instance and self.instance.pk:

            try:
                departamento = Departamento.objects.get(
                    nombre=self.instance.departamento
                )

                self.fields[
                    'departamento_selector'
                ].initial = departamento

                puestos = Puesto.objects.filter(
                    departamento=departamento
                ).order_by('nombre')

                self.fields['cargo_selector'].choices = [
                    ('', 'Seleccione un cargo')
                ] + [
                    (puesto.nombre, puesto.nombre)
                    for puesto in puestos
                ]

                self.fields[
                    'cargo_selector'
                ].initial = self.instance.cargo

            except Departamento.DoesNotExist:
                pass

        # -------------------------------------------------------------
        # Mantener cargos después de un POST con error
        # -------------------------------------------------------------
        if self.is_bound:

            departamento_id = self.data.get(
                'departamento_selector'
            )

            if departamento_id:

                try:
                    departamento = Departamento.objects.get(
                        pk=departamento_id
                    )

                    puestos = Puesto.objects.filter(
                        departamento=departamento
                    ).order_by('nombre')

                    self.fields['cargo_selector'].choices = [
                        ('', 'Seleccione un cargo')
                    ] + [
                        (puesto.nombre, puesto.nombre)
                        for puesto in puestos
                    ]

                except Departamento.DoesNotExist:
                    pass

    def save(self, commit=True):

        empleado = super().save(commit=False)

        departamento = self.cleaned_data[
            'departamento_selector'
        ]

        empleado.departamento = departamento.nombre

        empleado.cargo = self.cleaned_data[
            'cargo_selector'
        ]

        if commit:
            empleado.save()

        return empleado


# =============================================================================
# EMPLEADO
# =============================================================================

@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):

    form = EmpleadoAdminForm

    fields = (
        'usuario',
        'nombre_completo',
        'email',
        'dni',
        'fecha_nacimiento',
        'genero',
        'telefono',
        'direccion',
        'fecha_contratacion',
        'estado_laboral',
        'departamento_selector',
        'cargo_selector',
        'salario_mensual',
    )

    class Media:
        js = (
            'personal/js/empleado_admin.js',
        )

    list_display = (
        'nombre_completo',
        'dni',
        'cargo',
        'departamento',
        'salario_mensual',
        'estado_laboral',
        'fecha_contratacion',
        'ultimo_salario',
    )

    list_filter = (
        'estado_laboral',
        'departamento',
        'cargo',
        'genero',
        'fecha_contratacion',
    )

    search_fields = (
        'nombre_completo',
        'email',
        'dni',
        'cargo',
        'departamento',
        'telefono',
    )

    ordering = (
        'nombre_completo',
    )

    # -------------------------------------------------------------------------
    # Último salario
    # -------------------------------------------------------------------------

    def ultimo_salario(self, obj):

        salario = obj.salarios.order_by(
            '-mes_ano'
        ).first()

        if salario:
            return salario.neto

        return obj.salario_mensual

    ultimo_salario.short_description = 'Último salario'

    # -------------------------------------------------------------------------
    # Permisos
    # -------------------------------------------------------------------------

    def has_view_permission(self, request, obj=None):

        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
            or request.user.groups.filter(
                name='GERENTES'
            ).exists()
        )

    def has_add_permission(self, request):

        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
        )

    def has_change_permission(self, request, obj=None):

        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
        )

    def has_delete_permission(self, request, obj=None):

        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
        )

    # -------------------------------------------------------------------------
    # Auditoría salarial + historial automático de puestos
    # -------------------------------------------------------------------------

    def save_model(self, request, obj, form, change):

        salario_anterior = None
        cargo_anterior = None
        departamento_anterior = None

        if change:

            empleado_anterior = Empleado.objects.get(
                pk=obj.pk
            )

            salario_anterior = (
                empleado_anterior.salario_mensual
            )

            cargo_anterior = (
                empleado_anterior.cargo
            )

            departamento_anterior = (
                empleado_anterior.departamento
            )

        super().save_model(
            request,
            obj,
            form,
            change
        )

        # ---------------------------------------------------------------------
        # Historial salarial
        # ---------------------------------------------------------------------

        if (
            change
            and salario_anterior != obj.salario_mensual
        ):

            HistorialSalario.objects.create(
                empleado=obj,
                salario_anterior=salario_anterior,
                salario_nuevo=obj.salario_mensual,
                modificado_por=request.user.username
            )

        # ---------------------------------------------------------------------
        # Buscar puesto correspondiente
        # ---------------------------------------------------------------------

        puesto_nuevo = Puesto.objects.filter(
            nombre=obj.cargo,
            departamento__nombre=obj.departamento
        ).first()

        if not puesto_nuevo:
            return

        # ---------------------------------------------------------------------
        # Empleado nuevo
        # ---------------------------------------------------------------------

        if not change:

            EmpleadoPuesto.objects.create(
                empleado=obj,
                puesto=puesto_nuevo,
                fecha_inicio=(
                    obj.fecha_contratacion
                    or timezone.localdate()
                ),
                es_actual=True
            )

            return

        # ---------------------------------------------------------------------
        # Cambio de cargo o departamento
        # ---------------------------------------------------------------------

        if (
            cargo_anterior != obj.cargo
            or departamento_anterior != obj.departamento
        ):

            puesto_actual = (
                EmpleadoPuesto.objects
                .filter(
                    empleado=obj,
                    es_actual=True
                )
                .first()
            )

            if puesto_actual:

                puesto_actual.es_actual = False
                puesto_actual.fecha_fin = (
                    timezone.localdate()
                )

                puesto_actual.save()

            EmpleadoPuesto.objects.create(
                empleado=obj,
                puesto=puesto_nuevo,
                fecha_inicio=timezone.localdate(),
                es_actual=True
            )


# =============================================================================
# HISTORIAL SALARIAL
# =============================================================================

@admin.register(HistorialSalario)
class HistorialSalarioAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'salario_anterior',
        'salario_nuevo',
        'modificado_por',
        'fecha_modificacion',
    )

    search_fields = (
        'empleado__nombre_completo',
        'modificado_por',
    )

    list_filter = (
        'fecha_modificacion',
    )

    readonly_fields = (
        'empleado',
        'salario_anterior',
        'salario_nuevo',
        'modificado_por',
        'fecha_modificacion',
    )

    ordering = (
        '-fecha_modificacion',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None
    ):
        return False


# =============================================================================
# DEPARTAMENTO
# =============================================================================

@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):

    list_display = (
        'nombre',
        'jefe',
        'presupuesto',
    )

    search_fields = (
        'nombre',
        'descripcion',
        'jefe__nombre_completo',
    )

    list_filter = (
        'nombre',
    )


# =============================================================================
# PUESTO
# =============================================================================

@admin.register(Puesto)
class PuestoAdmin(admin.ModelAdmin):

    list_display = (
        'nombre',
        'departamento',
        'nivel',
        'salario_base',
    )

    search_fields = (
        'nombre',
        'departamento__nombre',
    )

    list_filter = (
        'departamento',
        'nivel',
    )


# =============================================================================
# HISTORIAL DE PUESTOS
# =============================================================================

@admin.register(EmpleadoPuesto)
class EmpleadoPuestoAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'puesto',
        'fecha_inicio',
        'fecha_fin',
        'es_actual',
    )

    search_fields = (
        'empleado__nombre_completo',
        'puesto__nombre',
    )

    list_filter = (
        'es_actual',
        'puesto__departamento',
        'fecha_inicio',
    )


# =============================================================================
# SALARIO / NÓMINA
# =============================================================================

@admin.register(Salario)
class SalarioAdmin(admin.ModelAdmin):

    fields = (
        'empleado',
        'mes_ano',
        'salario_base',
        'bonificacion',
        'descuentos',
        'neto',
        'pagado',
    )

    readonly_fields = (
        'neto',
    )

    list_display = (
        'empleado',
        'mes_ano',
        'salario_base',
        'bonificacion',
        'descuentos',
        'neto',
        'pagado',
    )

    search_fields = (
        'empleado__nombre_completo',
        'empleado__dni',
    )

    list_filter = (
        'pagado',
        'mes_ano',
    )

    ordering = (
        '-mes_ano',
    )


# =============================================================================
# ASISTENCIA
# =============================================================================

@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'fecha',
        'hora_entrada',
        'hora_salida',
        'minutos_trabajados',
        'estado',
    )

    search_fields = (
        'empleado__nombre_completo',
        'empleado__dni',
    )

    list_filter = (
        'estado',
        'fecha',
    )


# =============================================================================
# PERMISOS
# =============================================================================

@admin.register(Permiso)
class PermisoAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'tipo',
        'fecha_inicio',
        'fecha_fin',
        'dias',
        'estado',
        'aprobado',
    )

    search_fields = (
        'empleado__nombre_completo',
        'empleado__dni',
    )

    list_filter = (
        'tipo',
        'estado',
        'aprobado',
        'fecha_inicio',
    )

    ordering = (
        '-fecha_inicio',
    )

    actions = (
        'aprobar_permisos',
        'rechazar_permisos',
    )

    # -------------------------------------------------------------------------
    # Aprobar solicitudes seleccionadas
    # -------------------------------------------------------------------------

    @admin.action(
        description='Aprobar permisos seleccionados'
    )
    def aprobar_permisos(
        self,
        request,
        queryset
    ):

        autorizado = (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
            or request.user.groups.filter(
                name='GERENTES'
            ).exists()
        )

        if not autorizado:

            self.message_user(
                request,
                'No tienes permisos para aprobar solicitudes.',
                level=messages.ERROR
            )

            return

        cantidad = queryset.update(
            estado='aprobado',
            aprobado=True
        )

        self.message_user(
            request,
            f'{cantidad} permiso(s) aprobado(s) correctamente.',
            level=messages.SUCCESS
        )

    # -------------------------------------------------------------------------
    # Rechazar solicitudes seleccionadas
    # -------------------------------------------------------------------------

    @admin.action(
        description='Rechazar permisos seleccionados'
    )
    def rechazar_permisos(
        self,
        request,
        queryset
    ):

        autorizado = (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
            or request.user.groups.filter(
                name='GERENTES'
            ).exists()
        )

        if not autorizado:

            self.message_user(
                request,
                'No tienes permisos para rechazar solicitudes.',
                level=messages.ERROR
            )

            return

        cantidad = queryset.update(
            estado='rechazado',
            aprobado=False
        )

        self.message_user(
            request,
            f'{cantidad} permiso(s) rechazado(s) correctamente.',
            level=messages.WARNING
        )

    # -------------------------------------------------------------------------
    # Mantener sincronizado Estado / Aprobado
    # -------------------------------------------------------------------------

    def save_model(
        self,
        request,
        obj,
        form,
        change
    ):

        if obj.estado == 'aprobado':
            obj.aprobado = True

        else:
            obj.aprobado = False

        super().save_model(
            request,
            obj,
            form,
            change
        )


# =============================================================================
# EVALUACIONES
# =============================================================================

@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    form = EvaluacionForm

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.groups.filter(name__in=['RRHH', 'GERENTES']).exists()

    def has_add_permission(self, request):
        return request.user.is_superuser or request.user.groups.filter(name='RRHH').exists()

    def has_change_permission(self, request, obj=None):
        return self.has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    list_display = (
        'empleado',
        'periodo',
        'puntuacion',
    )

    search_fields = (
        'empleado__nombre_completo',
        'periodo',
    )

    list_filter = (
        'puntuacion',
        'periodo',
    )

# =============================================================================
# USUARIOS Y ROLES - CONSOLA DEL SISTEMA
# =============================================================================

# Sustituimos las vistas estándar de auth para mantener la misma interfaz de la
# consola y mostrar información útil para RRHH en lugar del indicador "staff".
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.action(description='Activar usuarios seleccionados')
def activar_usuarios(modeladmin, request, queryset):
    actualizados = queryset.update(is_active=True)
    modeladmin.message_user(request, f'{actualizados} usuario(s) activado(s).', messages.SUCCESS)


@admin.action(description='Desactivar usuarios seleccionados')
def desactivar_usuarios(modeladmin, request, queryset):
    queryset = queryset.exclude(pk=request.user.pk)
    actualizados = queryset.update(is_active=False)
    modeladmin.message_user(request, f'{actualizados} usuario(s) desactivado(s).', messages.SUCCESS)


@admin.action(description='Solicitar cambio de contraseña')
def solicitar_cambio_contrasena(modeladmin, request, queryset):
    creadas = 0
    for usuario in queryset:
        Notificacion.objects.create(
            usuario=usuario,
            mensaje='Se solicitó que actualices la contraseña de tu cuenta.',
            tipo='sistema',
            url='/cambiar-contrasena/',
        )
        creadas += 1
    modeladmin.message_user(
        request,
        f'Solicitud de cambio de contraseña enviada a {creadas} usuario(s).',
        messages.SUCCESS,
    )




def _asignar_grupo(queryset, nombre):
    grupo, _ = Group.objects.get_or_create(name=nombre)
    for usuario in queryset:
        usuario.groups.clear()
        usuario.groups.add(grupo)


@admin.action(description='Asignar rol EMPLEADO')
def asignar_rol_empleado(modeladmin, request, queryset):
    _asignar_grupo(queryset, 'EMPLEADO')
    modeladmin.message_user(request, 'Rol EMPLEADO asignado.', messages.SUCCESS)


@admin.action(description='Asignar rol GERENTES')
def asignar_rol_gerente(modeladmin, request, queryset):
    _asignar_grupo(queryset, 'GERENTES')
    modeladmin.message_user(request, 'Rol GERENTES asignado.', messages.SUCCESS)


@admin.action(description='Asignar rol RRHH')
def asignar_rol_rrhh(modeladmin, request, queryset):
    _asignar_grupo(queryset, 'RRHH')
    modeladmin.message_user(request, 'Rol RRHH asignado.', messages.SUCCESS)


@admin.register(User)
class SystemUserAdmin(DjangoUserAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Usuarios'
        return super().changelist_view(request, extra_context=extra_context)

    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'rol_sistema', 'estado_cuenta', 'last_login'
    )
    list_filter = ()
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)
    actions = (activar_usuarios, desactivar_usuarios, asignar_rol_empleado, asignar_rol_gerente, asignar_rol_rrhh, solicitar_cambio_contrasena)

    @admin.display(description='Rol')
    def rol_sistema(self, obj):
        nombre = 'RRHH' if obj.is_superuser else (obj.groups.order_by('name').values_list('name', flat=True).first() or 'SIN ROL')
        clase = 'rrhh' if nombre.upper() == 'RRHH' else ('gerente' if nombre.upper() in {'GERENTE', 'GERENTES'} else '')
        return format_html('<span class="role-badge {}">{}</span>', clase, nombre)

    @admin.display(description='Estado', boolean=False)
    def estado_cuenta(self, obj):
        clase = 'active' if obj.is_active else 'inactive'
        texto = 'Activo' if obj.is_active else 'Inactivo'
        return format_html('<span class="state-badge {}">● {}</span>', clase, texto)


@admin.register(Group)
class SystemGroupAdmin(DjangoGroupAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Roles y permisos'
        return super().changelist_view(request, extra_context=extra_context)

    list_display = ('name', 'descripcion_rol', 'cantidad_usuarios', 'cantidad_permisos')
    search_fields = ('name',)
    list_filter = ()

    @admin.display(description='Descripción')
    def descripcion_rol(self, obj):
        descripciones = {
            'EMPLEADO': 'Acceso básico al sistema y consulta de información propia.',
            'GERENTE': 'Acceso de gestión y consulta según los permisos asignados.',
            'GERENTES': 'Acceso de gestión y consulta según los permisos asignados.',
            'RRHH': 'Acceso completo para la gestión de personal.',
        }
        return descripciones.get(obj.name.upper(), 'Rol configurable del sistema.')

    @admin.display(description='Usuarios')
    def cantidad_usuarios(self, obj):
        return obj.user_set.count()

    @admin.display(description='Permisos')
    def cantidad_permisos(self, obj):
        return obj.permissions.count()
