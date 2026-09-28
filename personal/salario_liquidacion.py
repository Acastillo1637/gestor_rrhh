from django.utils import timezone


def modo_salario(fecha):
    """Solo el mes local actual dispone de un salario conocido automáticamente."""
    actual = timezone.localdate().replace(day=1)
    if fecha is None:
        return 'manual'
    mes = fecha.replace(day=1)
    return 'actual' if mes == actual else ('historico' if mes < actual else 'futuro')
