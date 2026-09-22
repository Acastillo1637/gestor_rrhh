# Gestor de RRHH: levantar el sistema en local

## Requisitos

- Python 3.10 o superior y Git.
- Acceso a una base PostgreSQL. El proyecto usa PostgreSQL, no SQLite.

## 1. Descargar el proyecto

```bash
git clone https://github.com/Acastillo1637/gestor_rrhh.git
cd gestor_rrhh
```

Si ya tienes una copia, entra en su carpeta y ejecuta `git pull origin main` antes de continuar.

## 2. Crear el entorno virtual e instalar dependencias

En Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En macOS o Linux:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

## 3. Configurar `.env`

Copia `.env.example` como `.env` en la raíz del proyecto. En PowerShell usa `Copy-Item .env.example .env`; en macOS o Linux usa `cp .env.example .env`.

Genera una clave nueva y copia el resultado en `CLAVE_SECRETA_DJANGO`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Completa el archivo con los datos de tu propia base PostgreSQL:

```dotenv
CLAVE_SECRETA_DJANGO=pega_aqui_la_clave_generada
MODO_DEPURACION=si
DOMINIOS_PERMITIDOS=localhost,127.0.0.1,[::1]
DB_NAME=nombre_de_la_base
DB_USER=usuario_de_la_base
DB_PASSWORD=contrasena_de_la_base
DB_HOST=servidor_de_la_base
DB_PORT=5432
```

Usa el puerto y el usuario exactos que entregue tu proveedor de PostgreSQL. Si ya tenías un `.env` con `DB_*`, conserva esos valores y agrega las tres variables de Django. `.env` está excluido de Git: no lo subas al repositorio.

## 4. Comprobar la configuración y la base

```bash
python manage.py check
python manage.py showmigrations
```

`showmigrations` comprueba la conexión y muestra las migraciones aplicadas. **Solo si la base es nueva** y está vacía, crea sus tablas con `python manage.py migrate`. En una base compartida existente, revisa las migraciones pendientes antes de aplicarlas.

Si la base es nueva y aún no tiene una cuenta administradora, crea una con `python manage.py createsuperuser`.

## 5. Iniciar el servidor

```bash
python manage.py runserver
```

Abre [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/) para iniciar sesión o [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) para el administrador. El nombre de usuario distingue mayúsculas de minúsculas.

Para detener el servidor, presiona `Ctrl+C` en la terminal.
