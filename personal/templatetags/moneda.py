from django import template

register = template.Library()


@register.filter
def pesos(valor):
    if valor is None:
        return "$0"

    try:
        numero = int(round(float(valor)))
        return "$" + f"{numero:,}".replace(",", ".")
    except (ValueError, TypeError):
        return valor