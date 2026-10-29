# Validación UI de formas de rutas en Maximo

Fecha: 2026-10-28

OT de prueba: 3088915

Pestaña: «Informes de anomalías»

Alcance: tres formas de jerarquía. No se ejecutó ningún flujo de trabajo: no se inició, enroutó, cerró, desechó ni retuvo la OT, ni se dio salida al equipo.

## Resultado

Se observaron tres rutas con formas distintas. Las filas creadas por las selecciones de prueba se marcaron para suprimir y se guardaron desde «Acciones comunes → Guardar». Las rutas LG-01 y FGV-20 tuvieron cierre terminal del selector; CD-19 añadió una causa directa y mantuvo el selector abierto mostrando resoluciones.

| Caso | Ruta estática (tipo, código, ID) | Observación directa en Maximo | Resultado |
|---|---|---|---|
| LG-01, una opción terminal | CLASS LG-01 (120) → PROBLEM LG-01-01 (178) | La lista de clase mostró la opción PROBLEM LG-01-01. Al elegirla se añadió una fila PROBLEM y el selector se cerró. | Ruta de un nivel confirmada. |
| FGV-20, dos niveles terminales | CLASS FGV-20 (42286) → PROBLEM P-0170 (321325) → CAUSE C-0370 (321560) | Al elegir P-0170, Maximo mostró seis causas, incluida C-0370 («Software y Firmware (Metro Valencia)»). Al elegir C-0370, añadió la fila CAUSE y cerró el selector sin pedir REMEDY. | Ruta terminal de dos niveles confirmada. |
| CD-19, CAUSE directamente bajo clase | CLASS CD-19 (435) → CAUSE CD-19-0-3 (1875) | La causa apareció en el nivel raíz. Al elegirla, el selector permaneció abierto y mostró cuatro REMEDY: CD-19-0-3-1 «Cleaning», CD-19-0-3-3 «Repair», CD-19-0-3-4 «Replacement» y CD-19-0-3-2 «False alarm». El orden visible difirió del orden por código. | Ruta directa a CAUSE y conjunto de cuatro remedios confirmados; no se seleccionó ningún remedio. |

Los IDs numéricos de la tabla proceden del snapshot `relaciones_originales.json.gz`; la UI mostró los códigos, tipos, descripciones y enlaces de selección del diálogo. La evidencia técnica conserva los IDs/targetids DOM observados para las opciones siguientes a P-0170 y CD-19-0-3.

## Estado y limpieza

La pasada empezó con una lectura fresh de la OT en estado `APPR`, clase `RFN-20` y cero filas. Se cambió la clase mediante su lookup a cada clase de la muestra y se guardó explícitamente. La clase final quedó en `CD-19`, conforme al último caso probado.

Para LG-01 y FGV-20, Maximo confirmó el guardado de las supresiones con `BMXAA4205I`; cada caso se releyó desde una sesión nueva antes de continuar. Para CD-19, el primer script terminó con `failed`: al salir del selector, la reconexión encontró la fila CAUSE recién persistida y el harness esperaba incorrectamente cero filas. No se presenta esa ejecución como totalmente exitosa. Se limpió después esa única fila temporal en una sesión nueva, Maximo confirmó `BMXAA4205I` y una lectura fresh final verificó `OT 3088915 / APPR / CD-19 / 0 filas`.

La salida de limpieza se conserva como observación de `stdout` de `cleanup_cd19.py`; no existía un JSON crudo de esa ejecución. No se hicieron más cambios después de esa lectura final.

## Qué queda confirmado para el modelo

La muestra confirma que el flujo real no debe asumir una secuencia fija `PROBLEM → CAUSE → REMEDY`: existen hojas PROBLEM, hojas CAUSE y clases que empiezan por CAUSE. La UI permite terminar sin seleccionar niveles de tipo REMEDY cuando la ruta llega a una hoja antes.

Esto complementa la validación del caso duplicado RFN-20: sus dos ocurrencias UI de C-RFN-062 mostraron S-RFN-262, mientras que el snapshot también contiene la rama S-RFN-263. Esa discrepancia sigue pendiente; no invalida el grafo completo ni convierte S-RFN-263 en una opción confirmada para automatizar.

Para la futura configuración, el modelo debe preservar clase, tipo, ID de ocurrencia y relación con el padre; detener el selector cuando la UI termina la ruta; y representar explícitamente las discrepancias de catálogo frente a UI. Esta muestra dirigida confirma las tres formas solicitadas, no verifica todas las opciones del catálogo.

## Evidencia

La evidencia sanitizada está en [evidencia_ui_formas.json](evidencia_ui_formas.json). La ejecución detallada que contiene la interacción y las respuestas observadas está en el artefacto temporal indicado dentro del JSON; no contiene cookies ni credenciales.
