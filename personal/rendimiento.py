"""Utilidades pequeñas para listados y datos reutilizados solo durante un request."""
from functools import wraps

from django.core.paginator import Paginator


def roles_usuario(user):
    if not user.is_authenticated:
        return frozenset()
    if hasattr(user, '_roles_del_request'):
        if user._roles_del_request is None:
            user._roles_del_request = frozenset(user.groups.values_list('name', flat=True))
        return user._roles_del_request
    return frozenset(user.groups.values_list('name', flat=True))


def roles_en_request(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        user._roles_del_request = None
        try:
            return view(request, *args, **kwargs)
        finally:
            del user._roles_del_request
    return wrapped


def paginar(request, queryset, total=None):
    opciones = (10, 25, 50, 100)
    valor = request.GET.get('por_pagina', '10')
    cantidad = int(valor) if valor in {str(n) for n in opciones} else 10
    paginator = Paginator(queryset, cantidad)
    if total is not None:
        paginator.count = total
    pagina = paginator.get_page(request.GET.get('page'))
    filtros = request.GET.copy()
    filtros.pop('page', None)
    filtros['por_pagina'] = str(cantidad)
    return pagina, {
        'pagina': pagina, 'por_pagina': cantidad, 'opciones_pagina': opciones,
        'filtros_pagina': filtros.urlencode(),
        'filtros_selector': [(k, v) for k, valores in filtros.lists()
                             if k != 'por_pagina' for v in valores],
        'paginas_visibles': paginator.get_elided_page_range(pagina.number),
    }
