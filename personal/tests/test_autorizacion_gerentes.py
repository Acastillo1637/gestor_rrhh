from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from ..models import Asistencia, Evaluacion, Notificacion, Salario
from . import test_permisos_departamento


class AutorizacionGerentesTests(test_permisos_departamento.PermisosDepartamentoTests):
    """Incluye también las regresiones de autorización por departamento."""

    def test_consultas_y_exportaciones(self):
        for nombre in ['dashboard_gestion', 'dashboard_gerente', 'listar_empleados',
                       'gestion_permisos', 'gestion_asistencia', 'gestion_evaluaciones',
                       'gestion_nomina', 'historial_salarial', 'exportar_nomina_excel',
                       'exportar_nomina_pdf']:
            with self.subTest(vista=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 200)
        html = self.client.get(reverse('dashboard_gestion')).content.decode()
        self.assertIn(reverse('gestion_evaluaciones'), html)
        self.assertNotIn('href="/admin/"', html)

    def test_escrituras_administrativas_denegadas(self):
        evaluacion = Evaluacion.objects.create(empleado=self.local, periodo='2026 - 1 semestre', puntuacion=4)
        salario = Salario.objects.create(empleado=self.local, mes_ano=timezone.localdate(), salario_base=1000000)
        destinos = [('crear_empleado', []), ('editar_empleado', [self.local.pk]),
                    ('crear_evaluacion', []), ('editar_evaluacion', [evaluacion.pk]),
                    ('crear_liquidacion', []), ('marcar_liquidacion_pagada', [salario.pk])]
        for nombre, argumentos in destinos:
            for metodo in ['get', 'post']:
                with self.subTest(vista=nombre, metodo=metodo):
                    with CaptureQueriesContext(connection) as consultas:
                        respuesta = getattr(self.client, metodo)(reverse(nombre, args=argumentos),
                            {'nombre_completo': 'Alterado', 'salario_mensual': 1, 'pagado': True})
                    self.assertIn(respuesta.status_code, [302, 403])
                    self.assertEqual([q['sql'] for q in consultas if q['sql'].lstrip().upper().startswith(
                        ('INSERT ', 'UPDATE ', 'DELETE '))], [])
        salario.refresh_from_db()
        self.assertFalse(salario.pagado)

    def test_controles_de_escritura_ocultos(self):
        salario = Salario.objects.create(empleado=self.local, mes_ano=timezone.localdate(), salario_base=1000000)
        for pagina, acciones in [
            ('listar_empleados', [('crear_empleado', []), ('editar_empleado', [self.local.pk])]),
            ('gestion_evaluaciones', [('crear_evaluacion', [])]),
            ('gestion_nomina', [('crear_liquidacion', []), ('marcar_liquidacion_pagada', [salario.pk])]),
        ]:
            respuesta = self.client.get(reverse(pagina))
            for accion, args in acciones:
                self.assertNotContains(respuesta, reverse(accion, args=args))

    def test_buzon_compartido_solo_lectura(self):
        aviso = Notificacion.objects.create(mensaje='Compartido')
        for nombre, args in [('marcar_notificacion_leida', [aviso.pk]),
                             ('eliminar_notificacion', [aviso.pk]),
                             ('marcar_notificaciones_leidas', [])]:
            with CaptureQueriesContext(connection) as consultas:
                respuesta = self.client.post(reverse(nombre, args=args))
            self.assertEqual(respuesta.status_code, 403)
            self.assertEqual([q['sql'] for q in consultas if q['sql'].lstrip().upper().startswith(
                ('INSERT ', 'UPDATE ', 'DELETE '))], [])
            aviso.refresh_from_db()
            self.assertFalse(aviso.leida)
        respuesta = self.client.get(reverse('dashboard_gestion'))
        self.assertContains(respuesta, 'Compartido')
        for nombre, args in [('marcar_notificacion_leida', [aviso.pk]),
                             ('eliminar_notificacion', [aviso.pk]),
                             ('marcar_notificaciones_leidas', [])]:
            self.assertNotContains(respuesta, reverse(nombre, args=args))

    def test_notificaciones_personales_conservan_acciones(self):
        aviso = Notificacion.objects.create(usuario=self.gerente, mensaje='Personal')
        self.assertEqual(self.client.post(reverse('marcar_notificacion_leida', args=[aviso.pk])).status_code, 302)
        aviso.refresh_from_db()
        self.assertTrue(aviso.leida)
        self.assertEqual(self.client.post(reverse('eliminar_notificacion', args=[aviso.pk])).status_code, 302)
        self.assertFalse(Notificacion.objects.filter(pk=aviso.pk).exists())

    def test_autoservicio_y_asistencia_ajena(self):
        for nombre in ['mi_cuenta', 'mis_permisos', 'mis_evaluaciones', 'mis_liquidaciones',
                       'mi_asistencia', 'cambiar_contrasena']:
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)
        inicio = timezone.localdate() + timedelta(days=10)
        respuesta = self.client.post(reverse('solicitar_permiso'), {
            'tipo': 'administrativo', 'fecha_inicio': inicio, 'fecha_fin': inicio,
            'empleado': self.ajeno.pk,
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(self.jefe.permisos.exists())
        self.assertFalse(self.ajeno.permisos.exists())
        self.client.post(reverse('mi_asistencia'), {'accion': 'entrada', 'empleado': self.ajeno.pk})
        self.assertTrue(Asistencia.objects.filter(empleado=self.jefe).exists())
        self.assertFalse(Asistencia.objects.filter(empleado=self.ajeno).exists())
        with CaptureQueriesContext(connection) as consultas:
            self.client.post(reverse('gestion_asistencia'), {'empleado': self.ajeno.pk, 'estado': 'presente'})
        self.assertEqual([q['sql'] for q in consultas if q['sql'].lstrip().upper().startswith(
            ('INSERT ', 'UPDATE ', 'DELETE '))], [])
