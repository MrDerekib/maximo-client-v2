# Auditoría de relaciones del catálogo de anomalías de Maximo

Fecha de extracción auditada: 2026-10-28T12:16:13.919229+01:00

## Dictamen

El catálogo es apto como fuente de desplegables dependientes si la implementación conserva cada relación por padre (y la clase/organización) y usa las rutas reales, sin forzar una profundidad fija. La representación compacta conserva el multiconjunto de rutas por código/tipo alcanzables; la estructura no equivale a un árbol universal de tres niveles: hay rutas de distinta longitud y tres causas bajo una clase. Los 4.806 nodos con padres ausentes son resoluciones consultadas que no se pueden ubicar en la jerarquía exportada. Los códigos no son claves únicas: el compacto no conserva los IDs de nodo, y el duplicado C-RFN-062 tiene descendientes distintos bajo el mismo problema; un selector cuyo valor sea solo el código no puede elegir de forma inequívoca su siguiente grupo. Hace falta una clave de ocurrencia o una regla de resolución de Maximo validada para ese caso.

La auditoría es estática, de todos los registros descargados. La decisión sobre el comportamiento actual de los desplegables solo requiere una muestra dirigida en Maximo (casos estándar, ruta corta/larga, duplicado divergente, clase no estándar), no recorrer manualmente cada selector.

## Validación dirigida en Maximo

La auditoría estática se contrastó con pruebas dirigidas en Maximo: la causa duplicada `C-RFN-062` (automatizada y revisión manual de Joan el 29/10) y tres formas de ruta. En ambas revisiones de la ruta UI se observó `S-RFN-262`; aunque el snapshot original conserva la rama `S-RFN-263`, no se encontró en la ruta probada. Para la futura configuración, excluir o marcar como no confirmada esa combinación en esta ruta, sin alterar el grafo crudo ni atribuir una causa. Esto no bloquea la siguiente fase. Detalles: [validacion_ui_rfn20_duplicado.md](validacion_ui_rfn20_duplicado.md) y [validacion_ui_formas.md](validacion_ui_formas.md).

## Recuento y consistencia de descarga

- failurelist: **374,730** filas; metadato: 374,730. Coincide: **True**.
- failurecode: **9,160** definiciones; metadato: 9,160. Coincide: **True**.
- Clases exportadas: **126**; raíz en volcado: **126**; metadato: 126.
- IDs repetidos: **0**.
- Recuento por tipo (raíz sin type contada como CLASS): `{'CLASS': 126, 'PROBLEM': 2078, 'CAUSE': 23744, 'REMEDY': 348782}`; metadato: `{'CLASS': 126, 'PROBLEM': 2078, 'CAUSE': 23744, 'REMEDY': 348782}`.
- Total de filas frente al total declarado: coincide (374,730). La instantánea no conserva cursores ni conteos por página; por tanto puede confirmarse el total final, pero no reconstruir independientemente los límites/solapamientos de cada página a partir de estos archivos.

## Grafo, compactación y rutas

- Alcanzables desde clases: **369,924** (metadato 369,924); no alcanzables: **4,806** (incidencias documentadas 4,806). Coincidencia IDs: **True**.
- Padres ausentes: **153 IDs / 4,806 registros hijos**; coincidencia IDs documentados: **True**. Toda relación con padre presente apunta a un ID existente; las faltantes están en incidencias_catalogo.json.
- Aristas no estándar (hijo distinto de PROBLEM directamente bajo clase): **3**, mismas aristas documentadas: **True**.
- Expansión compacta: 344,326 rutas terminales; multiconjunto de rutas completas por código/tipo igual al grafo alcanzable: **True**; referencias colgantes: **0**. El compacto no incluye IDs, por lo que esta igualdad no distingue ocurrencias con código idéntico.
- Grupos compactos compartidos: 1,602. La comprobación compara rutas expandidas por ocurrencia con rutas reconstruidas desde ID padre, no solo el contenido/hash de los grupos; cualquier mezcla de descendientes altera el multiconjunto y habría fallado.
- Profundidad de rutas (aristas desde clase): `{1: 49, 2: 313, 3: 343964}`.

## Incidencias verificadas y ejemplos

### Códigos sin definición (6)

Coinciden exactamente con incidencias: **True**. Códigos: CD-6-6-10-10, CD-6-6-10-11, CD-6-6-10-12, CD-6-6-10-3, CD-6-6-10-4, CD-6-6-10-5.

IDs y rutas de los seis nodos: CLASS:CD-6[id=441] → PROBLEM:CD-6-6[id=485] → CAUSE:CD-6-6-10[id=24997] → REMEDY:CD-6-6-10-3[id=41018]; CLASS:CD-6[id=441] → PROBLEM:CD-6-6[id=485] → CAUSE:CD-6-6-10[id=24997] → REMEDY:CD-6-6-10-4[id=41020]; CLASS:CD-6[id=441] → PROBLEM:CD-6-6[id=485] → CAUSE:CD-6-6-10[id=24997] → REMEDY:CD-6-6-10-5[id=41022]; CLASS:CD-6[id=441] → PROBLEM:CD-6-6[id=485] → CAUSE:CD-6-6-10[id=24997] → REMEDY:CD-6-6-10-10[id=41024]; CLASS:CD-6[id=441] → PROBLEM:CD-6-6[id=485] → CAUSE:CD-6-6-10[id=24997] → REMEDY:CD-6-6-10-11[id=41026]; CLASS:CD-6[id=441] → PROBLEM:CD-6-6[id=485] → CAUSE:CD-6-6-10[id=24997] → REMEDY:CD-6-6-10-12[id=41028]

### Tipos/longitudes no estándar

Causas directamente bajo CD-19: **3**: CLASS:CD-19[id=435] → CAUSE:CD-19-0-3[id=1875]; CLASS:CD-19[id=435] → CAUSE:CD-19-0-0[id=1881]; CLASS:CD-19[id=435] → CAUSE:CD-19-0-2[id=4641]

Profundidades por clase (número de aristas desde clase): CD-19: {2: 12}; FGV-00: {3: 1000, 2: 245}; FGV-20: {3: 22509, 2: 14}; FGV-30: {2: 42, 3: 18982}; LG-01: {1: 3}; LG-02: {1: 4}; LG-03: {1: 6}; LG-04: {1: 9}; LG-05: {1: 2}; LG-06: {1: 2}; LG-07: {1: 3}; LG-08: {1: 4}; LG-09: {1: 2}; LG-10: {1: 2}; LG-11: {1: 2}; LG-12: {1: 2}; LG-13: {1: 2}; LG-14: {1: 2}; LG-15: {1: 2}; LG-16: {1: 2}

Rutas RFN-70 observadas con IDs: CLASS:RFN-70[id=278488] → PROBLEM:OTROS-01[id=278490] → CAUSE:OTROS-02[id=278492] → REMEDY:OTROS-05[id=278502]; CLASS:RFN-70[id=278488] → PROBLEM:OTROS-01[id=278490] → CAUSE:OTROS-02[id=278492] → REMEDY:OTROS-04[id=278500]; CLASS:RFN-70[id=278488] → PROBLEM:OTROS-01[id=278490] → CAUSE:OTROS-02[id=278492] → REMEDY:OTROS-03[id=278498]

### Padres ausentes (153 IDs)

Primeros registros con padre ausente y su código/ID: S-TMB-001 id=353892 parent=353862; S-TMB-005 id=353894 parent=353862; S-TMB-040 id=353896 parent=353862; S-TMB-021 id=353898 parent=353862; S-TMB-007 id=353900 parent=353862

Estos nodos son inubicables desde clases en esta descarga; no deben colgarse de una clase inferida.

### Códigos duplicados bajo un mismo padre (490 pares)

Grupos/código duplicados dentro de option_sets: **490**; apariciones adicionales: **492**. Equivalentes (misma subestructura): **489**; con descendientes distintos: **1**. Los 489 equivalentes son resoluciones hoja repetidas. C-RFN-062: clase RFN-20[id=163460] → problema P-RFN-139[id=164920] → causa C-RFN-062[id=165598, 165600] → resoluciones S-RFN-263[id=167710] y S-RFN-262[id=167400]; comparten padre pero no descendientes. grupo g_3192904c660119c5, subárboles [(('REMEDY', 'S-RFN-263', ()),), (('REMEDY', 'S-RFN-262', ()),)]

Ejemplos de grupos duplicados:

- Grupo g_81eaeb13071fcbdd, código R-0370 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_6e7bdf8c77331b8c, código R-0410 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_09d5542f43cac48f, código R-0420 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_0a47446156f5c476, código R-0440 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_eb3438bb494b9b9c, código R-0450 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_0429dec5daef499a, código R-0460 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_1b6494497f245e52, código R-1001 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_1b6494497f245e52, código R-1003 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_1b6494497f245e52, código R-1004 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_1b6494497f245e52, código R-1006 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_1b6494497f245e52, código R-1007 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]
- Grupo g_1b6494497f245e52, código R-1008 (REMEDY), ocurrencias=2, pares=1, descendientes_equivalentes=True; subárboles=[(), ()]

## Accesibilidad y duplicados de opciones

- Opciones exportadas en grupos compactos: 13,171; grupos/código repetidos: 490.
- Los 4,806 no alcanzables son de tipo(s) `{'REMEDY': 4806}`; los padres ausentes detectados están documentados: True.
- Una ruta compacta puede repetir el mismo código en grupos distintos: eso es válido porque el valor depende del padre. La UI debe guardar/enviar también el código correspondiente al nivel y respetar el padre seleccionado.

## Formato de informe legible recomendado

Mantener el catálogo original intacto y generar una vista tabular por ruta: `organización | clase (código/ID/descr.) | problema (código/ID/descr.) | causa (código/ID/descr.) | resolución (código/ID/descr.) | profundidad | anomalía | definición`. Una fila por camino completo, con celdas vacías cuando el nivel no existe. Para rutas más profundas, usar columnas `nivel_n (tipo, código, ID, descripción)` o JSON Lines con `path: [{id,type,code,description}]`. Incluir IDs evita colapsar duplicados de código y ayuda a revisar descendientes distintos.

## Reproducción

En PowerShell, desde esta carpeta, ejecutar:

```powershell
& 'C:\Users\jcamp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\auditar_relaciones.py
```

El script solo lee `catalogo_anomalias.json`, `relaciones_originales.json.gz` e `incidencias_catalogo.json`; sobrescribe únicamente este informe Markdown. No consulta Maximo ni crea/actualiza OTs.
