Instalación y Configuración Completa del Gestor de RRHH

Paso 1: Instalar Python

Descarga el instalador oficial de Python desde python.org (versión 3.10 o superior).

Ejecuta el instalador descargado y marca obligatoriamente la casilla "Add Python to PATH" (Añadir Python al PATH) en la parte inferior de la ventana antes de hacer clic en Install Now.

Abre una nueva terminal (PowerShell o CMD) y verifica que se haya instalado correctamente escribiendo:

Bash
python --version
Paso 2: Descargar el Código del Proyecto

Asegúrate de tener Git instalado. Clona el repositorio oficial ejecutando en tu terminal:

Bash
git clone https://github.com/Acastillo1637/gestor_rrhh.git
Entra a la carpeta del proyecto recién descargada:

Bash
cd gestor_rrhh
Paso 3: Crear y Activar un Entorno Virtual

Crea un entorno virtual dentro de la carpeta del proyecto para aislar las dependencias:

Bash
python -m venv venv
Activa el entorno virtual según tu sistema operativo:

En Windows (PowerShell):

Bash
venv\Scripts\Activate
En macOS / Linux:

Bash
source venv/bin/activate
Paso 4: Instalar Django y las Dependencias

Con el entorno virtual activo, instala automáticamente Django y todas las librerías necesarias ejecutando:

Bash
pip install -r requirements.txt
Paso 5: Configurar la Base de Datos (Migraciones)

Prepara las tablas en la base de datos local ejecutando las migraciones:

Bash
python manage.py makemigrations
python manage.py migrate
Paso 6: Crear un Usuario Administrador

Registra una cuenta de superusuario para poder ingresar al panel de control y ver las auditorías:

Bash
python manage.py createsuperuser
Introduce el nombre de usuario, tu correo electrónico y tu contraseña cuando el sistema te lo solicite.

Paso 7: Ejecutar el Servidor de Pruebas

Pon en marcha la aplicación localmente con el comando:

Bash
python manage.py runserver
Paso 8: Acceder a la Aplicación

Abre tu navegador web favorito.

Entra a la Vista Principal (Dashboard, filtros y calculadora de nómina en vivo) en: http://127.0.0.1:8000/empleados/

Entra al Panel de Administración (Control de usuarios e Historial de Salarios) en: http://127.0.0.1:8000/admin/
