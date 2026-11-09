# Reconocimiento de almacén — 6 de noviembre de 2026

Este documento recoge la primera fase sin confirmaciones. Posteriormente se
autorizó una única salida real, documentada en
[Validación real de salida](almacen-validacion-salida.md).

## Alcance

Inspección con la cuenta de almacén, sin ejecutar entradas, salidas, rechazos ni
envíos a SAT. No se seleccionan radios ni se pulsa «Aceptar» en «Entrada manual».
El transporte del prototipo sigue siendo exclusivamente simulado.

Las fichas, asignaciones, historial y mapa se consultaron con las herramientas de
Python/Selenium y de depuración de Edge. El selector de recepción fue abierto por
el usuario. No se pulsó Enrutar mediante la inspección automática: esa pulsación
fue bloqueada por la revisión automática por el posible avance directo del flujo.

## Observaciones confirmadas

- Una ficha de recepción muestra `WAPPR`; el listado local utiliza
  `PDTE CONFIRMAR`. Las dos fichas propuestas para recepción estaban en `WAPPR`.
- La ficha propuesta para salida muestra `ISSUE`; el listado local utiliza
  `DAR SALIDA`.
- Dos candidatas del listado local figuraban como `DAR SALIDA`, pero sus fichas
  reales ya estaban en `CLOSE`. No se ha demostrado cuál era el motivo del desfase.
  El estado de MD no puede autorizar la operación por sí solo.
- El control de enrutado observado es `ROUTEWF_WO-MAIN_-tbb_image`.
- Las vistas informativas disponibles incluyen `ASSIGNWF`, `LOGWF` y `SPECWF`.
  En asignaciones se observaron el proceso `WOFLUJO4TR` y tareas de recepción
  («¿Confirma recepcion o cancela?») y salida («Salida de almacen del activo»).
- El mapa de `WO-MAIN` representa ramas de confirmación/rechazo/SAT y salida.
  Es una referencia del recorrido, no una prueba de los efectos de cada acción.

## Selector de recepción observado

Contenedor visible: `inputwf-dialog_inner`, título «Entrada manual».

| Acción del prototipo | Etiqueta nativa observada | Resultado de la búsqueda |
| --- | --- | --- |
| Confirmar recepción | Confirmar recepción | Una coincidencia |
| Rechazar recepción | Rechazar recepción | Una coincidencia |
| Confirmar y enviar a SAT Interno | Confirmar y enviar a SAT Interno | Una coincidencia |
| Confirmar y enviar a SAT Externo | Confirmar y enviar a SAT Externo | Una coincidencia |

Cada control es `input[type=radio]` y referencia su etiqueta mediante
`aria-labelledby`. Los cuatro tienen el mismo `value="on"`; no se pueden distinguir
por ese atributo. Los identificadores `mx…-rb` observados pertenecen a esa sesión y
no deben quedar fijados en la automatización. La localización fiable debe resolver
la etiqueta, comprobar el texto exacto normalizado y exigir una sola coincidencia
dentro del diálogo visible.

El diálogo dispone de botones «Aceptar» y «Cancelar». Se observó el manejador
nativo de cancelación `sendEvent('dialogcancel','inputwf-dialog', null, null)`.
No se activó ningún radio ni se confirmó ninguna operación.

El segundo caso de recepción también se inspeccionó en vivo: estado `WAPPR`, mismo
diálogo y cuatro opciones. «Confirmar recepción» tiene una sola coincidencia;
aparece marcada inicialmente por Maximo, sin que la inspección altere esa selección.

## Selector de salida observado

La ficha propuesta para salida conservaba `ISSUE` con el selector abierto por el
usuario. Se observó el mismo contenedor `inputwf-dialog_inner` («Entrada manual»),
con un único radio «Dar salida activo del almacén», referenciado también mediante
`aria-labelledby`. Su etiqueta coincide exactamente con `ACTIONS['dispatch']`.
El radio estaba marcado inicialmente por Maximo; los botones disponibles eran
«Aceptar» y «Cancelar». No se seleccionó ni confirmó nada.

Se contrastaron los tres casos con las etiquetas de `warehouse.py`: SAT externo
y confirmación de recepción tienen una coincidencia única en sus respectivos
diálogos; la salida tiene una coincidencia única en el suyo. Las cuatro etiquetas
de recepción definidas en el prototipo coinciden con las cuatro opciones leídas
en ambas fichas. Esto valida su correspondencia y localización, no sus efectos.

## Implicaciones para el proceso futuro

1. Abrir la OT y contrastar identificador y estado leídos en Edge con la acción
   solicitada. Rechazar estados distintos de los permitidos, incluido `CLOSE`.
2. Reconocer el diálogo visible y localizar una única opción por su etiqueta;
   no seleccionar la primera opción ni usar el radio marcado por defecto.
3. Separar claramente la localización de la selección y la confirmación. Esta
   fase solo valida la localización.
4. Tras una futura confirmación autorizada, comprobar el resultado en la ficha.
   El cierre del diálogo no demuestra que la operación haya terminado bien.
5. Ante un resultado incierto, conservar el diagnóstico y continuar con la
   siguiente OT sin repetir la confirmación de la anterior.

## Pendiente de una fase posterior autorizada

- Los diálogos posteriores, requisitos adicionales, cambios de estado y
  persistencia de las cinco acciones no se validan en esta fase: requerirían una
  ejecución real con autorización expresa posterior.

## Referencia histórica de SAT interno

El usuario facilitó una OT ya derivada a SAT interno. Se consultó sin enrutar ni
modificarla. En Edge figura `ISSUE`, con la descripción «Pendiente dar salida del
almacén». En el listado local de MD figura `SAT INT`; «Seguimiento» no aparece como
un campo visible en esa ficha, por lo que no se atribuye ese texto a una lectura
directa de la ficha de Edge.

Su historial contiene «Confirmar y enviar a SAT Interno» y posteriormente
«Se realizó acción de direccionamiento». Conserva la asignación «Salida de almacen
del activo» en `WOFLUJO4TR`. Esto respalda `ISSUE` como estado final esperado para
SAT interno en el caso aportado. `ISSUE` o la asignación de salida por sí solos no
identifican la variante de SAT: el resultado debe contrastarse también con la acción
concreta registrada en el flujo y la referencia del envío de esa ejecución.

El usuario confirma que SAT interno también solicita detalles. No se abrió su
diálogo ni se ejecutó otra derivación durante esta consulta; su estructura exacta
sigue pendiente de inspección. Tampoco se extrapola automáticamente el estado de
SAT interno a SAT externo: la prueba de externo permanece pendiente de completar
el OK del diálogo y verificar el resultado guardado.

Las evidencias con identificadores de OT y DOM quedan en archivos locales de QA;
no se incorporan credenciales ni datos personales a este documento.
