from django.contrib.auth.models import User
from django.test import TestCase

from ..models import Empleado
from ..usernames import generar_username_unico
from ..views import crear_usuario_para_empleado


class UsernameTests(TestCase):
    def test_amaro(self):
        self.assertEqual(generar_username_unico('Amaro', 'Castillo', 'Ahumada'), 'amaro.castillo')

    def test_nombre_compuesto(self):
        for nombre, paterno, materno, esperado in [
            ('Amaro Andrés', 'Castillo', 'Ahumada', 'amaro.castillo'),
            ('María José', 'Cruz', 'Pérez', 'maria.cruz'),
            ('María José de la', 'Cruz', 'Pérez', 'maria.cruz'),
        ]:
            self.assertEqual(generar_username_unico(nombre, paterno, materno), esperado)

    def test_normalizacion(self):
        for nombre, paterno in [('José', 'Muñoz'), (' JOSÉ  ', '  MUÑOZ  '),
                                ('José!', 'Mu-ño.z')]:
            self.assertEqual(generar_username_unico(nombre, paterno, 'Álvarez'), 'jose.munoz')

    def test_colisiones_correlativas_no_sobrescriben(self):
        for esperado in ['amaro.castillo', 'amaro.castilloa', 'amaro.castilloa2',
                         'amaro.castilloa3', 'amaro.castilloa4']:
            self.assertEqual(generar_username_unico('Amaro', 'Castillo', 'Ahumada'), esperado)
            User.objects.create_user(esperado, password='Original', email='original@example.test')
        antes = list(User.objects.order_by('pk').values())
        self.assertEqual(generar_username_unico('Amaro', 'Castillo', 'Ahumada'), 'amaro.castilloa5')
        self.assertEqual(list(User.objects.order_by('pk').values()), antes)

    def test_materno_ausente(self):
        User.objects.create_user('amaro.castillo')
        self.assertEqual(generar_username_unico('Amaro', 'Castillo'), 'amaro.castillo2')
        User.objects.create_user('amaro.castillo2')
        self.assertEqual(generar_username_unico('Amaro', 'Castillo'), 'amaro.castillo3')

    def test_limite_y_colisiones(self):
        for _ in range(4):
            username = generar_username_unico('A' * 150, 'B' * 150, 'C')
            self.assertLessEqual(len(username), User._meta.get_field('username').max_length)
            self.assertRegex(username, r'^[a-z0-9]+\.[a-z0-9]+$')
            User.objects.create_user(username)

    def test_colision_mayusculas(self):
        User.objects.create_user('AMARO.CASTILLO')
        self.assertEqual(generar_username_unico('Amaro', 'Castillo', 'Ahumada'), 'amaro.castilloa')

    def test_componentes_sin_caracteres_utilizables(self):
        with self.assertRaises(ValueError):
            generar_username_unico('!!!', 'Castillo', 'Ahumada')

    def test_creacion_usa_componentes_y_preserva_cuentas(self):
        existente = User.objects.create_user('amaro.castillo', password='Original')
        antes = User.objects.filter(pk=existente.pk).values().get()
        empleado = Empleado.objects.create(nombre_completo='Texto que no debe separarse')
        nuevo, _ = crear_usuario_para_empleado(empleado, nombre='Amaro Andrés',
                                              apellido_paterno='Castillo', apellido_materno='Ahumada')
        self.assertEqual(nuevo.username, 'amaro.castilloa')
        self.assertEqual(User.objects.filter(pk=existente.pk).values().get(), antes)
        with self.assertRaises(ValueError):
            crear_usuario_para_empleado(empleado, nombre='Otro', apellido_paterno='Nombre')
        self.assertEqual(User.objects.count(), 2)
