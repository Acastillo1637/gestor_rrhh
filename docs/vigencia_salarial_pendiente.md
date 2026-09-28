# Vigencia salarial pendiente de diseño y despliegue

El 27 de septiembre de 2026 se retiró temporalmente el bloque no desplegado de
`HistorialSalario.fecha_vigencia`, incluida la migración local 0013 y sus diez
pruebas específicas. Supabase continúa en 0012 y no dispone de esa columna.
No se aplicaron ni simularon migraciones ni se alteraron datos.

El código vuelve a utilizar el historial anterior para permitir revisar el portal.
Las mejoras de rendimiento, paginación, permisos, asistencia y Nueva Liquidación
permanecen independientes de este trabajo.

## Reglas acordadas para retomar

- Cada liquidación utiliza el salario vigente el día 1 de su mes, sin prorrateo.
- Agregar una fecha de vigencia nullable, normalizada al día 1. Solicitar el mes
  explícitamente al cambiar salarios en el portal y el administrador.
- Conservar `fecha_modificacion` exclusivamente como auditoría.
- Los registros anteriores deben conservar vigencia NULL, identificados como
  legado pendiente de revisión; nunca rellenarlos desde la fecha de modificación.
- Validar meses duplicados por empleado. Proponer y obtener autorización para
  una restricción de unicidad que también cubra concurrencia; una validación de
  formulario/modelo por sí sola no garantiza esto en PostgreSQL.
- Definir primero una representación explícita del salario inicial y su vigencia.
  El salario actual del empleado y el importe anterior de un cambio no garantizan
  una reconstrucción histórica completa.
- Definir cómo afectan los cambios futuros al salario actual; no se implementó
  un mecanismo de actualización programada.
- No automatizar el salario de liquidaciones mientras existan períodos ambiguos.

## Despliegue futuro

Recrear la migración sobre el historial vigente en ese momento. Probar en una
base aislada la preservación de filas, auditoría y NULL históricos, normalización,
obligatoriedad condicional en ambos formularios y rechazo de duplicados.
Coordinar y autorizar la migración antes de desplegar código que seleccione el
nuevo campo. No basta con ocultarlo en una plantilla: el ORM lo selecciona.
