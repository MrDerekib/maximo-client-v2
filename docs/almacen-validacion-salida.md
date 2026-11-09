# Validación real de salida de almacén — 6 de noviembre de 2026

## Alcance y resultado

El usuario autorizó expresamente la salida de una única OT. Se ejecutó esa salida
una sola vez con la cuenta de almacén. No se realizaron entradas, rechazos, envíos
a SAT ni operaciones sobre otras OTs. El prototipo de MD sigue siendo simulado;
esta prueba se hizo con un script local limitado a la OT autorizada.

Resultado confirmado: **`ISSUE` → `CLOSE`**, persistido en el servidor. Se
comprobó reabriendo la ficha y también desde otra sesión recién autenticada.
El activo, número de serie, cliente y planta coincidían antes y después.

Las evidencias detalladas con identificadores y marcas de tiempo quedan en QA
local. Este documento no contiene credenciales, tokens de sesión ni personas.

## Recorrido observado

1. Abrir la ficha y leer su número, activo, serie, cliente, planta y estado.
   Estado inicial: `ISSUE` (equivalente a `DAR SALIDA` en el listado de MD).
2. Consultar las asignaciones de flujo: existía la tarea «Salida de almacen del
   activo» del proceso `WOFLUJO4TR`. Cerrar únicamente esa vista informativa.
3. Pulsar una vez `ROUTEWF_WO-MAIN_-tbb_image`.
4. Esperar al diálogo visible `inputwf-dialog_inner`, título «Entrada manual».
   Contenía un único radio «Dar salida activo del almacén», inicialmente marcado
   por Maximo, y los botones «Aceptar» y «Cancelar».
5. Volver a contrastar identidad, estado `ISSUE`, ausencia de carga, unicidad de
   diálogo/opción/botón y selección del radio correcto. Resolver la opción por
   su etiqueta asociada, no por el ID de esa sesión ni por `value="on"`.
6. Registrar el intento de confirmación antes de pulsar «Aceptar». Pulsarlo
   exactamente una vez. No repetir el clic ante un error o una respuesta incierta.
7. Consultar la ficha de nuevo, sin volver a enrutar: estado `CLOSE` y nueva fecha
   de estado. Comprobar la misma identidad. Una sesión nueva confirmó `CLOSE`.
8. Consultar asignaciones: ya no quedaban tareas pendientes. El historial
   registró «Dar salida activo del almacén», los enlaces automáticos siguientes
   y «Se detuvo el proceso» en `WO-MAIN`.

El historial situó «Dar salida activo del almacén» a las 09:40:22 y el fin del
proceso a las 09:40:27, hora local. La ficha mostró la misma hora final de estado.
Son observaciones de este caso; no establecen un tiempo máximo de procesamiento.

## Interferencia durante la prueba

El usuario informó de una pulsación accidental de Back mientras se observaba la
respuesta. Se vio el listado en lugar de la ficha; **no se puede atribuir esa
navegación al comportamiento normal del flujo**. Tampoco se toma esta ejecución
como prueba concluyente de que nunca aparezcan diálogos posteriores.

La verificación posterior y el historial demostraron que la salida sí estaba
guardada. No se repitió ninguna confirmación. La ejecución prevista desde MD será
headless: el Back accidental no forma parte de su recorrido normal. El tratamiento
de una respuesta incierta sigue siendo necesario para pérdidas de conexión o del
navegador: consultar primero el resultado guardado, sin duplicar la acción.

## Reglas para el transporte futuro de MD

- Congelar OT y acción al revisar el lote. Antes de actuar, comparar el número de
  ficha con esa OT; conservar activo/serie/planta como comprobaciones de identidad
  cuando estén disponibles. No exigir que el usuario conozca un ID dinámico.
- Usar el estado leído en Edge como condición de ejecución. El texto de MD sirve
  para preselección. Una OT ya en `CLOSE` no debe volver a enviarse a salida.
- No deducir permisos ni idoneidad de que aparezca el botón de Enrutar: seguía
  visible con la ficha en `CLOSE`.
- Esperar respuestas/carga y volver a localizar controles tras cada actualización
  del DOM. Revalidar OT y estado inmediatamente antes de confirmar.
- Seleccionar por texto exacto normalizado y asociación ARIA dentro del diálogo
  visible. Exigir una única coincidencia; no usar posición, radio predeterminado
  o IDs `mx…` fijos. Comprobar la selección antes de aceptar.
- Acotar «Aceptar» al diálogo de la acción esperada. Una ventana desconocida o un
  mensaje del sistema exige diagnóstico; no se acepta automáticamente por título
  de botón ni se interpreta todo aviso como inofensivo.
- Mantener por OT una marca de envío y su resultado. No envolver la confirmación
  en reintentos de clic. Ante un timeout o una excepción después del envío, verificar
  el servidor antes de clasificar el resultado; no volver a ejecutar la acción.
- El éxito de salida requiere la misma OT en `CLOSE` leída del servidor. El cierre
  de un diálogo, la desaparición de campos o un indicador de carga no bastan. Las
  asignaciones y el historial son comprobaciones complementarias de diagnóstico.
- Guardar por lote/OT el paso, estado inicial/final, opción solicitada y opciones
  encontradas, intento de confirmación, tiempos y errores. No registrar contraseñas
  ni URLs con tokens. Resultados inciertos quedan disponibles para revisión manual
  mientras el lote continúa según la política del prototipo.

## Qué sigue pendiente

- Implementar y probar el transporte headless de MD usando este recorrido; la
  ejecución aislada autorizada no lo habilita en la app.
- Validar en una fase autorizada el efecto y los posibles diálogos adicionales de
  recepción, rechazo y envíos a SAT. No se extrapola `CLOSE` a esas acciones.
