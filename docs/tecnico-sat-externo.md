# SAT externo desde el rol de técnico — fase 1

Rama: `tecnico/sat-externo`. Acción distinta de la recepción de almacén con
«Confirmar y enviar a SAT Externo». Comparte el procesador de lotes, el reporte,
las prioridades y la recuperación; no comparte la acción ni el estado inicial.
La extensión de Edge queda para fase 2 y no se ha modificado.

## Uso desde MD

En Configuración → Envío a SAT · Técnico, activar «Mostrar envío técnico a SAT
externo en MD» y guardar. No requiere habilitar funciones de almacén.
Seleccionar una o varias filas y usar el menú contextual de envío técnico.

El diálogo consulta primero las fichas sin modificarlas y propone como motivo la
avería original de Maximo, editable por OT. También propone las horas ya existentes.
Si alguna ficha no está en APPR, el envío queda deshabilitado y hay que revisar
la selección. Antes de ejecutar, el usuario completa o revisa:

- Combinación de anomalías para el lote, inicialmente la predeterminada de MD.
- Horas de cada OT, positivas en múltiplos de 0,25 h.
- Incidencia o referencia de cada OT. Admite números y texto como `stock`.
- Motivo de cada OT, inicialmente el Resumen de Orden de trabajo en Maximo.

El inicio requiere confirmación explícita con No por defecto. Cada OT se prepara
con anomalías/soluciones, horas y un registro CLIENTNOTE con `inc: referencia`.
La preparación se guarda y se contrasta desde una recarga antes de enrutar.
Un registro idéntico visible no se duplica. Si no se encuentra y hay más páginas
de registro que no se han inspeccionado, se detiene para revisión en lugar de
crear una posible incidencia duplicada.

## Recorrido validado en la OT 4433097 — 11/11/2026

Estado inicial APPR; activo 136930, serie SA408, planta LAB-BAD. El usuario autorizó
expresamente el envío real después de revisar la preparación:

1. RFN-70 → OTROS-01 → OTROS-02 → OTROS-03.
2. Horas de reparación 0,50.
3. Un registro CLIENTNOTE `inc: stock`, sin duplicarlo al repetir la preparación.
4. En Entrada manual, elegir exactamente «Enviar a SAT Externo». Las otras opciones
   son Iniciar orden, Cancelar orden y Enviar a SAT Interno.
5. Aceptar abre `ENVIAR_SAT_EXT-dialog_inner`, título SAT Externo, editor Detalles.
6. Motivo real: `NO ADMITE`, tomado del Resumen original de la OT.
7. Tras OK, el resultado es ISSUE. Una sesión independiente confirmó la misma
   identidad y una nueva entrada de «Enviar a SAT Externo» en el historial, de 0 a 1.

La preparación real y el recorrido final se probaron por partes con Selenium.
La cola completa del nuevo diálogo de MD se ha validado con simulaciones, no con
un nuevo lote real. No se ha reenviado 4433097 después de su transición a ISSUE.
La evidencia acotada del caso está en `validaciones/tecnico-sat-4433097.json`.

## Incidencias encontradas y corregidas

- Maximo puede sustituir elementos mientras se consulta si Guardar está disponible.
  Se reintenta únicamente esa lectura si caduca la referencia, sin repetir el envío.
- El editor SAT valida el texto de forma asíncrona al salir con Tab. En la prueba
  la capa de carga interceptó el primer clic en OK: Selenium acreditó que no se
  entregó. Después de verificar APPR, mismo diálogo, mismo motivo y ausencia de
  bloqueo, se confirmó el OK dentro de la autorización original.
- El código ahora espera la respuesta de validación del editor y comprueba que el
  botón no está tapado antes de registrar el intento y pulsarlo una sola vez.
  No reintenta automáticamente una confirmación incierta.

## Recuperación y diagnóstico

Los registros compartidos están en `logs/almacen-operaciones`, diferenciados por
acción `technician_sat_external`. Se crea una evidencia persistente en fase
`preparing` antes de la primera escritura. Se actualiza antes de Enrutar, Aceptar
y el OK de detalles. Una preparación fallida puede conservar cambios parciales y
queda para revisión; no se reejecuta a ciegas.

Se reutilizan las comprobaciones de identidad, el incremento del historial de la
acción exacta y el estado ISSUE para verificar el envío técnico. Los resultados
inciertos se consultan al final del lote y mediante Reverificar, sin volver a
preparar ni enviar. El estado local verificado se refleja como SAT EXT, sujeto a
las posteriores lecturas de Maximo. El motivo y la referencia no se incorporan
como campos del registro de recuperación ni del reporte normal.

La revisión de pendientes se ofrece para los roles habilitados en Configuración.
Las tareas no alteran credenciales ni usan otra cuenta para sortear permisos.

## Límites de esta fase

- Solo envío técnico a SAT externo desde APPR. No inicia la OT previamente.
- La avería es un valor propuesto, no una justificación inventada; el usuario puede
  editarla y un motivo vacío impide comenzar.
- No se han añadido botones de SAT a la extensión de Edge.
- No se ha generado build ni fusionado esta rama con dev/main.


## Validación final

24 pruebas nuevas de preparación, consulta, interfaz, confirmación, guardado,
estados incompatibles y recuperación de respuesta perdida. Suite completa:
386 pruebas, 304 correctas y 82 de Edge offline omitidas. Los seis archivos de
configuración y credenciales de producción/dev/almacén conservaron sus hashes.
El envío real de referencia se realizó por etapas con autorización; el nuevo
lote completo desde el diálogo de MD queda pendiente de la próxima OT autorizada.


## Ajuste antes de la siguiente prueba real

El primer lote desde MD sobre 4431127 guardó y verificó la preparación. Al pulsar
Enrutar, Maximo mostró un msgbox BMXAA4214E en lugar de Entrada manual. No se llegó
a seleccionar SAT ni se pulsaron Aceptar/OK. La reverificación observó APPR. El
usuario pudo continuar manualmente, por lo que el registro no permite atribuir
la causa a un dato inválido ni demostrar un fallo permanente de Maximo.

Se refuerza la sincronización, sin afirmar que el origen esté confirmado:

- Antes del enrutado técnico, si cambia a Orden de trabajo, esperar una respuesta
  nativa posterior al cambio; el atributo aria-expanded por sí solo no basta.
- Comprobar ficha, OT, estado APPR, activo/planta visibles y botón Enrutar accesible
  antes del clic. Registrar esa evidencia como `technician_route_ready`.
- Conservar el texto nativo y código BMX de cualquier diálogo inesperado, sin
  sustituirlos por el error genérico del selector.
- Mantener el error original también cuando la reverificación solo observa APPR.
- No descartar avisos desconocidos ni añadir reintentos de la derivación.

Cuatro regresiones nuevas reproducen respuesta tardía, botón bloqueado, aviso BMX
y conservación del error durante una consulta posterior. Falta contrastar esta
espera reforzada con una nueva OT autorizada; no se ha repetido la operación en
las OTs terminadas manualmente.


## Separación de sesiones tras el segundo fallo

La espera anterior no evitó el BMXAA4214E en 4431263: la respuesta de pestaña había
pasado de 0 a 1, los campos eran correctos y el botón estaba accesible. Eso descarta
que la espera aplicada bastase para resolver el caso; no revela la excepción interna.

Con autorización del usuario exclusivamente para abrir el selector, se hicieron
consultas en sesiones nuevas headless sobre la misma OT ya preparada, sin escribir
campos ni seleccionar SAT ni pulsar Aceptar. Ambas abrieron Entrada manual y dejaron
APPR. La segunda incluyó la verificación de horas, incidencia, clase/códigos, seguida
del historial y de la espera de navegación. Evidencia en
`validaciones/selector-4431263-sesion-limpia.json`. Las sesiones se cerraron después.

El procesador técnico ahora separa las fases:

1. Sesión de preparación: aplicar, guardar y verificar campos. No consulta historial
   de flujo ni pulsa Enrutar.
2. Cerrar esa sesión antes del primer intento de enrutado.
3. Sesión nueva con la misma cuenta: volver a cargar la OT, comprobar APPR e identidad
   y verificar los datos guardados sin volver a escribirlos.
4. Consultar el historial previo en esta sesión, después de la preparación, y guardar
   el contador en el registro persistente antes de enrutar.
5. Abrir el selector y continuar con la acción explícita y su único Aceptar/OK.

Si cambian el estado, el equipo o la clase, no se enruta. No se reinicia una sesión
para repetir una confirmación incierta: los cambios de contexto solo ocurren antes
del primer Enrutar. Las acciones de almacén conservan su recorrido anterior.

Añade un inicio de sesión por OT técnica; el coste se acepta para aislar el contexto
que falla después de modificar y recargar. No se afirma haber identificado la causa
interna de Maximo. Falta validar el envío completo desde el nuevo lote de MD.

Validación de esta separación: suite completa de 393 pruebas, 311 correctas y
82 omitidas. Los seis archivos de configuración/credenciales conservaron sus hashes.
