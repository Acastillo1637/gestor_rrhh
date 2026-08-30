# -----------------------------------------------------------------------------
# Enrutador principal del proyecto. Conecta el panel de administración y las URLs de la aplicación personal.
# -----------------------------------------------------------------------------
from django.contrib import admin
from django.urls import path, include

# Tabla de rutas globales del proyecto.
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('personal.urls')),
]