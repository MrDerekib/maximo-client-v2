# Recuperación de operaciones de almacén

Implementación experimental en `almacen/recuperacion`, separada de las pruebas de
rendimiento. No cambia la versión publicada ni genera una build.

## Comportamiento

1. Antes de enrutar, MD consulta la OT, compara equipo, número de serie y planta,
   y exige el estado inicial de la acción. Una lectura transitoria puede
   reintentarse una vez, antes de cualquier intento de enrutar.
2. Antes de Enrutar se crea un registro persistente exclusivo por OT. Antes de
   Aceptar y del OK de detalles SAT se actualiza ese registro y el diario, con
   vaciado a disco. Si no se puede guardar la evidencia, no se pulsa ese control.
3. Desde el intento de Enrutar no se repite automáticamente ninguna acción del
   flujo. Una respuesta perdida queda pendiente de verificar y el lote continúa.
4. Al terminar las OTs normales, se consulta cada pendiente de ese lote desde una
   sesión independiente. Se permiten hasta dos intentos de consulta, sin Enrutar,
   Aceptar ni OK. Se comprueban identidad y estado final. Para SAT se exige además
   un incremento del historial de la acción concreta respecto al valor previo.
5. Si Maximo está verificado, MD actualiza su estado local. Un error de guardado
   local se reintenta una vez; si persiste, queda ámbar y se conserva el registro.
   Una recuperación posterior reintenta solo el guardado local conocido.
6. Las OTs que no puedan verificarse siguen pendientes. No se ofrece reenviar la
   operación ni liberar automáticamente su bloqueo.

Una recepción ya en APPR o una salida ya en CLOSE se muestra como «Ya estaba
completada», sin enviar una nueva acción. Un estado ISSUE por sí solo no acredita
una derivación SAT.

## Interfaz

El reporte incorpora «Reverificar pendientes». Conserva las filas ya correctas y
actualiza únicamente las pendientes. También se pueden abrir desde Configuración,
sección Almacén, con «Revisar operaciones pendientes…».

Al arrancar con almacén habilitado, si hay registros pendientes, MD ofrece abrir
su revisión. Abrirla no inicia trabajo. Su botón «Reverificar (solo consulta)»
inicia exclusivamente la comprobación y/o el guardado local. Se puede detener sin
borrar las evidencias pendientes. Los resultados anteriores permanecen disponibles.

Una nueva acción sobre la misma OT se bloquea mientras exista un registro sin
resolver, incluso si se solicita otra acción. Una revisión antigua cuyo registro
ya haya cambiado no puede restaurar un estado local anterior.

## Archivos para diagnóstico

Dentro de `logs/almacen-operaciones`:

- `<lote>-events.jsonl`: pasos, intentos, comprobaciones, errores y guardado local.
- `<lote>-result.json`: resultado por OT, `operation_id` y `local_status_saved`.
- `pendientes/<hash-de-ot>.json`: evidencia de recuperación, identidad, acción,
  fase, intentos posibles de envío y estado final verificado, si existe.
- Cada reverificación tiene un diario nuevo, enlazado por OT y `operation_id`.
  Cuando se resuelve, se actualiza también el reporte original si está disponible.

Los pendientes usan creación exclusiva y reemplazo atómico; se eliminan al
finalizar el guardado local y la actualización del reporte. No contienen claves,
cookies, tokens ni texto de detalles SAT. Un archivo corrupto bloquea el nuevo
envío y requiere revisión: no se descarta silenciosamente.

Los registros de recuperación solo existen para operaciones ejecutadas con esta
implementación. Los diarios antiguos de versiones publicadas no se convierten
automáticamente en pendientes.

## Validación local — 10/11/2026

27 pruebas nuevas de recuperación, más las regresiones existentes de transporte e
interfaz: 55 pruebas dirigidas correctas. Suite completa: 346 pruebas, 264
correctas y 82 omitidas (pruebas de Edge offline, activadas por variable aparte).
Configuraciones y credenciales de producción, dev y almacén: hashes sin cambios.

Se inyectan fallos de lectura, persistencia, Enrutar, Aceptar, OK SAT, verificación
y guardado local; también caída del proceso tras el clic y recuperación desde disco.
La simulación de 18 salidas pierde la respuesta en la séptima, completa las once
posteriores y recupera la séptima al final. Se acredita una sola confirmación por
OT. Hay pruebas de identidad distinta, historial SAT insuficiente, registros
corruptos u obsoletos, cancelación, preservación de resultados y revisión manual.

Estas pruebas usan un servidor ficticio en memoria y datos temporales; no operan
sobre Maximo. No demuestran el comportamiento de todos los diálogos ni los tiempos
reales de producción. La siguiente validación debe ser un lote pequeño autorizado,
con revisión de reporte y diario por los usuarios de almacén. No garantiza entrega
exactamente una vez en el servidor: evita el reenvío automático ante incertidumbre.
