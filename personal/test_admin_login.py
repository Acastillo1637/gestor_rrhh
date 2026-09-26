from django.contrib.auth.models import User
from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('admin_login_test', password='Prueba-admin-2026!', is_staff=True)
        User.objects.create_user('sin_permiso', password='Prueba-admin-2026!')
        User.objects.create_user('inactivo', password='Prueba-admin-2026!', is_staff=True, is_active=False)

    def test_formulario_oficial_y_presentacion(self):
        response = self.client.get(reverse('admin:login'), {'next': '/admin/auth/user/'})
        self.assertContains(response, 'Consola del Sistema')
        self.assertContains(response, 'console-login-card')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'name="next" value="/admin/auth/user/"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, 'Iniciar sesión')
        self.assertContains(response, 'Volver al portal RRHH')

    def test_login_staff_respeta_next(self):
        response = self.client.post(reverse('admin:login'), {
            'username': self.staff.username, 'password': 'Prueba-admin-2026!', 'next': '/admin/',
        })
        self.assertRedirects(response, '/admin/', fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.staff.pk)

    def test_credenciales_invalidas_no_staff_e_inactivo(self):
        for username, password in [('admin_login_test', 'incorrecta'), ('sin_permiso', 'Prueba-admin-2026!'), ('inactivo', 'Prueba-admin-2026!')]:
            with self.subTest(username=username):
                response = self.client.post(reverse('admin:login'), {
                    'username': username, 'password': password, 'next': '/admin/',
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].non_field_errors())
                self.assertContains(response, 'class="errornote"')
                self.assertNotIn('_auth_user_id', self.client.session)
                self.assertContains(response, 'name="next" value="/admin/"')

    def test_csrf_y_redireccion_externa(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('admin:login'), {
            'username': self.staff.username, 'password': 'Prueba-admin-2026!',
        }).status_code, 403)
        response = self.client.post(reverse('admin:login'), {
            'username': self.staff.username, 'password': 'Prueba-admin-2026!',
            'next': 'https://example.com/',
        })
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)
