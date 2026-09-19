Instalación y Configuración Completa del Gestor de RRHH

Requisitos del Sistema

Python 3.10 o superior.

Git instalado en el equipo.

Paso 1: Instalación de Herramientas Base (En equipos limpios)

En Ubuntu / Debian (Linux):

Bash
sudo apt update && sudo apt install python3 python3-pip python3-venv git -y
En macOS (vía Homebrew):

Bash
brew install python git
En Windows: Descargar e instalar Python y Git desde sus sitios oficiales, asegurándose de marcar la casilla "Add Python to PATH" durante la instalación de Python.

Paso 2: Descarga del Repositorio
Clonar el código fuente desde el repositorio oficial de GitHub y acceder al directorio del proyecto:

Bash
git clone https://github.com/Acastillo1637/gestor_rrhh.git
cd gestor_rrhh
Paso 3: Configuración del Entorno Virtual
Aislar las dependencias del sistema creando y activando un entorno virtual:

Crear el entorno:

Bash
python -m venv venv
Activar en Windows (PowerShell):

PowerShell
venv\Scripts\Activate
Activar en macOS / Linux:

Bash
source venv/bin/activate
Paso 4: Instalación de Dependencias Profesionales
Actualizar el gestor de paquetes e instalar todas las librerías necesarias especificadas en el proyecto:

Bash
python -m pip install --upgrade pip
pip install -r requirements.txt


Paso 5: Configuración y Migración de la Base de Datos
Generar y aplicar las tablas correspondientes en la base de datos SQLite local:

Bash
python manage.py makemigrations
python manage.py migrate


Paso 6: Creación del Usuario Administrador
Registrar credenciales para acceder al panel de control protegido y al módulo de auditoría de salarios:

Bash
python manage.py createsuperuser
(Ingresa el nombre de usuario, correo electrónico y contraseña solicitados en pantalla).

Paso 7: Ejecución del Servidor

Modo Desarrollo (Local):

Bash
python manage.py runserver
Modo Producción (Opcional con Gunicorn para Linux/Servidores):

Bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000
Una vez ejecutado el servidor, la aplicación estará disponible en [http://127.0.0.1:8000/empleados/](http://127.0.0.1:8000/empleados/) para la interfaz de gestión y en [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) para el panel administrativo.
