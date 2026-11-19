# Lectura de avería y descripción ampliada

La consulta automática trabaja con OTs activas. Cada campo tiene una marca de lectura independiente:
una lectura correcta, incluso vacía, lo deja fuera de las siguientes colas automáticas.
Los errores mantienen el campo pendiente y respetan 24 horas antes de otro intento automático,
aunque no quede otro trabajo pendiente. No se borran las marcas al actualizar el listado.

El menú contextual «Actualizar datos desde Maximo» consulta Seguimiento, avería y descripción ampliada de la OT
o del lote marcado, aunque ya estuvieran leídos o las OTs sean no activas. No depende de
habilitar las consultas automáticas. Usa prioridad manual y la coordinación habitual;
no enruta ni cambia datos en Maximo. Se conserva la selección de OTs al solicitar la acción.

No se vacía la caché ni se reinician fechas de lectura antes de consultar: cada campo se
actualiza solo tras una lectura correcta. Un fallo conserva el dato y la fecha de éxito
anteriores. Una lectura vacía correcta sí sustituye el dato anterior por vacío.
La cancelación conserva lo leído correctamente y permite actualizar lo que falte más tarde.

La lectura manual del Seguimiento aprovecha la ficha abierta para la avería y también
se guarda en OTs activas. Cada campo se actualiza por separado y una lectura fallida
no borra el dato anterior. La presencia en el listado sigue dependiendo de la descarga XLS.

La conciliación automática del seguimiento es otra tarea: comprueba OTs no activas con estados
pendientes, incluidos DAR SALIDA e ISSUE; no depende de la avería ni fuerza CLOSE.
