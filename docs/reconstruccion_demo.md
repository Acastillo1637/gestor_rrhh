# Reconstrucción de datos demo

Esta implementación no autoriza ni ejecuta automáticamente la limpieza de PostgreSQL.
Sin `--ejecutar`, el comando solo consulta y planifica en memoria.

```powershell
python manage.py reconstruir_demo_rrhh --dry-run --seed 2026 --fecha-referencia 2026-09-27
```

El dry-run no guarda archivos, no crea usuarios ni grupos y no consume secuencias.
Informa los usuarios seleccionados y supervivientes, dependencias de yubel, registros
que se eliminarían, distribución y cantidades de los registros nuevos.
Los usernames definitivos se resuelven al crear las cuentas, mediante
`personal.usernames.generar_username_unico`, contra las cuentas supervivientes y
las nuevas cuentas ya creadas en esa transacción. No se intenta reservarlos en simulación.

## Alcance y protecciones

- Verifica `rrhh`: ID 1, username exacto, cuenta activa/staff/superusuario,
  contraseña utilizable y ausencia de ficha de empleado. Compara todos sus campos,
  grupos, permisos directos y permisos de sus grupos antes y después.
- Reconstruye todos los registros de los nueve modelos de negocio enumerados
  en `NEGOCIO`. No borra feriados, grupos, permisos, content types ni migraciones.
- Selecciona para eliminar únicamente usuarios vinculados a empleados reemplazados,
  `yubel` identificado por ID 10 y username exacto, y usernames explícitos mediante
  `--eliminar-usuario`. Preserva los demás usuarios. Otro superusuario seleccionado
  hace abortar el comando. `rrhh` nunca puede seleccionarse.
- Incluye además `gerente.prueba`, ID 20, inspeccionado como cuenta demo: activo,
  sin staff/superusuario, sin email/nombres de User, únicamente GERENTES, sin permisos
  directos, ficha, notificaciones ni auditoría propia o sobre su cuenta. Si existe
  con otro ID o perfil, aborta para revisión; no decide por el nombre solamente.
- Una identidad inconsistente de yubel, una relación nueva desconocida, migraciones
  pendientes o una diferencia en el inventario antes del borrado impiden continuar.
- Invalida TODAS las sesiones Django existentes, incluida la de rrhh, por autorización
  explícita. No decodifica su contenido. El dry-run solo cuenta; no elimina ninguna.
  Invalidar sesiones no modifica cuentas, contraseñas, grupos ni permisos.
- Archiva todos los `LogEntry` antes del borrado. Elimina de la BD únicamente los de
  actores eliminados; conserva los de rrhh y otros supervivientes sin reasignar actores.
  Los `object_id` históricos pueden apuntar a objetos ya inexistentes: son referencias
  textuales de auditoría, no fichas nuevas. No se reinician secuencias.
- Conserva notificaciones de usuarios supervivientes, incluida rrhh. Sustituye las
  generales y las de usuarios eliminados. Las notificaciones antiguas conservadas
  pueden incluir enlaces históricos; no se reescriben para apuntar a personas nuevas.

## Ejecución futura, solo después de revisión y autorización

Antes debe existir un respaldo completo restaurable de PostgreSQL. El archivo de
auditoría no sustituye ese respaldo. Detener escrituras de la aplicación durante
la ejecución: el comando bloquea las tablas afectadas en PostgreSQL, con un tiempo
máximo de espera de diez segundos. Una transacción `atomic()` contiene la limpieza,
la carga y las validaciones; un error revierte los cambios de datos.

La ejecución requiere ambas opciones `--ejecutar` y
`--confirmar RECONSTRUIR_DEMO_RRHH`. `--dry-run` y `--ejecutar` son incompatibles.
No ejecutar ahora. No invocar `flush`, comandos antiguos de carga ni migraciones.

El comando puede reconstruir nuevamente una población previa: sigue siendo una
operación destructiva explícita y exige las mismas opciones y revisión. No es un
comando para ejecutar automáticamente al iniciar el servidor.

## Credenciales y archivos locales

Una ejecución real usa `.demo_rrhh/<identificador-unico>/`, ignorado por Git:

- `auditoria_anterior.json`: copia previa de auditoría, sin hashes de User.
- `plan.json`: inventario y cantidades de la ejecución.
- `credenciales_demo_rrhh.csv`: 80 cuentas nuevas, nombre, departamento, cargo,
  rol, username, contraseña demo y estado activo/inactivo.
- `COMPLETADO.txt`: confirmación posterior a la transacción.

Contraseña exclusivamente de demostración: `DemoRRHH!<seed>`; para seed 2026,
`DemoRRHH!2026`. Django la almacena mediante `create_user`, con su hasher configurado.
Los históricos tienen `is_active=False`. La cuenta rrhh jamás se exporta.
Los archivos deben permanecer locales y privados, no subirse ni servirse por HTTP.

Si falla la transacción se elimina el CSV y se conserva el archivo de auditoría
con `FALLO.txt`. El sistema de archivos y la BD no forman una transacción distribuida:
ante una interrupción abrupta, verificar la BD y los archivos antes de reintentar.
Las secuencias de PostgreSQL pueden avanzar en una ejecución REAL fallida; nunca se
reinician. Esta limitación no afecta al dry-run, que no escribe.

## Datos y límites del modelo actual

Se crean exactamente 80 empleados: 73 activos, 4 `renuncio`, 3 `despedido`.
Los siete responsables de departamento pertenecen a GERENTES, cuatro empleados
de RRHH a RRHH y los restantes a EMPLEADO. Ninguna cuenta nueva es staff o superusuario.
Amaro Castillo Ahumada es jefe de Tecnología; su username usa el helper compartido.

La semilla, fecha de referencia y calendario conservado determinan el plan.
Las cuentas supervivientes determinan las colisiones de usernames. Los IDs, sales
de contraseñas y marcas técnicas de ejecución no se prometen idénticos entre cargas.

- Nombres combinados ficticios; identificadores inequívocamente sintéticos `DEMO-0001`.
  No se presentan como RUT reales o validados. Emails bajo `empresa.example`.
  Teléfonos opcionales vacíos para no asignar números potencialmente reales.
- El departamento textual se sincroniza con el puesto relacionado. Cada activo
  tiene exactamente un puesto actual; los históricos tienen sus asignaciones cerradas.
- La fecha de salida no existe en Empleado: se conserva en el plan determinista y
  la fecha de término del último puesto. No se inventa un campo ni una migración.
- Se crean ascensos y cambios salariales para una parte de la plantilla, hasta doce
  meses de nómina según antigüedad, evaluaciones de semestres terminados, solicitudes
  aprobadas/rechazadas/pendientes y hasta un año de asistencia.
- Se conserva la cronología previa al ajustar el volumen de solicitudes. Hay un
  pendiente de subordinado por departamento, tres en Tecnología y uno propio de
  Amaro para RRHH (10 en total). Se reduce la frecuencia de permisos médicos y
  administrativos y se evitan vacaciones de incorporaciones menores a seis meses.
- Los empleados comparten Puesto por departamento, cargo y nivel. Su salario_base
  es una referencia del nivel; salario_mensual e historial conservan los importes
  individuales. Los puestos históricos equivalentes también se reutilizan.
- Las liquidaciones utilizan el cálculo simplificado del modelo, no un motor de
  remuneraciones legal. No se simulan cotizaciones o prorrateos que el sistema no modela.
- Se conserva el calendario existente. La asistencia respeta la regla del proyecto:
  feriado irrenunciable, fin de semana, permiso aprobado, jornada normal. No descarga
  ni inventa calendarios de feriados. Los permisos cuentan días corridos.
- `auto_now_add` se ajusta únicamente en los nuevos registros de historial salarial
  y notificaciones personales para representar fechas históricas.
- La auditoría importada no se atribuye a rrhh ni se fabrica actividad humana.

Las pruebas usan SQLite en memoria y directorios temporales. La rama de bloqueo
específica de PostgreSQL necesita validación en una copia aislada antes de la primera
reconstrucción real; no se ha probado sobre la BD del usuario.
