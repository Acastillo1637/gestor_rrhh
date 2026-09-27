"""Regla compartida para nuevas cuentas del portal y futuras cargas."""
import re
import unicodedata

from django.contrib.auth import get_user_model


def normalizar_componente(valor):
    ascii_text = unicodedata.normalize('NFKD', valor or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', ascii_text.lower())


def generar_username_unico(nombre, apellido_paterno, apellido_materno=''):
    """No reutiliza cuentas; recibe componentes, nunca nombre_completo."""
    palabras = (nombre or '').split()
    primero = normalizar_componente(palabras[0] if palabras else '')
    paterno = normalizar_componente(apellido_paterno)
    materno = normalizar_componente(apellido_materno)
    inicial = next((c for c in materno if c.isalpha()), '')
    if not primero or not paterno:
        raise ValueError('El nombre y apellido paterno deben contener caracteres utilizables.')
    usuario = get_user_model()
    limite = usuario._meta.get_field('username').max_length

    def candidato(sufijo):
        disponible = limite - len(sufijo) - 1
        if disponible < 2:
            raise ValueError('No queda espacio para un username único.')
        # Conserva ambos componentes y reserva espacio para cada sufijo.
        parte_nombre = primero[:min(len(primero), disponible - 1)]
        parte_apellido = paterno[:disponible - len(parte_nombre)]
        return f'{parte_nombre}.{parte_apellido}{sufijo}'

    sufijo = ''
    numero = 2
    while True:
        username = candidato(sufijo)
        if not usuario.objects.filter(username__iexact=username).exists():
            return username
        if not sufijo and inicial:
            sufijo = inicial
        else:
            sufijo = f'{inicial}{numero}'
            numero += 1
