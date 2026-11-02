# Catálogo de anomalías de Maximo

Extracción: 2026-10-28T12:16:13.919229+01:00

- Clases raíz: 126; coinciden con las 126 del listado exportado.
- Nodos descargados: 374,730.
- Nodos alcanzables desde estas clases: 369,924.
- Síntomas (PROBLEM): 2,078.
- Relaciones de causa (CAUSE): 23,744.
- Relaciones de resolución (REMEDY): 343,976.
- Definiciones recuperadas: 9,160.

## Archivos

- `catalogo_anomalias.json`: opciones y descripciones de todas las clases con sus dependencias reales.
- `resumen_clases.csv`: recuentos por clase, para revisar en Excel.
- `incidencias_catalogo.json`: registros fuera de la estructura habitual y definiciones ausentes.
- `relaciones_originales.json.gz`: instantánea completa con los IDs originales y sus padres.

## Estructura y conservación de relaciones

`classes[].options_ref` referencia una lista de `option_sets`. Cada opción conserva su
`code` y `type`. Si tiene opciones dependientes, `children_ref` referencia el siguiente grupo.
Las descripciones están en `descriptions[organizacion][codigo]`.

Solo se comparten grupos cuando su contenido completo es idéntico. La expansión del catálogo
compacto coincide exactamente con todos los nodos alcanzables del original. Se conserva el
tipo real de cada opción, incluso cuando la jerarquía no sigue el orden habitual.

CAUSE y REMEDY cuentan relaciones: un mismo código puede figurar bajo padres distintos.
El CSV incluye también el número de códigos distintos por clase.

## Incidencias del catálogo consultado

- Hay 4,806 resoluciones cuyos 153 padres no aparecen
  en la consulta completa ni en consultas individuales por identificador. Se conservan
  en la instantánea original y en el informe de incidencias; no se asignan a una clase inventada.
- Hay 3 causas directamente bajo la clase CD-19. Se mantienen
  con su tipo y posición originales.
- Hay 6 códigos sin definición recuperable: CD-6-6-10-10, CD-6-6-10-11, CD-6-6-10-12, CD-6-6-10-3, CD-6-6-10-4, CD-6-6-10-5.
  Sus nodos y códigos se conservan; la descripción queda en null.

## Verificación

- Descarga paginada con total estable y sin IDs duplicados.
- Consulta independiente de las opciones de cada una de las 126 clases.
- Comprobación individual de todos los padres y definiciones ausentes.
- Contraste de las 28 opciones PROBLEM exportadas del selector nativo de BUS-10
  y las seis opciones CAUSE observadas bajo P-BUS-001.
- Comprobación desde otra sesión de la restitución de clase, códigos y estado de la OT de consulta.

La extracción completa usó consultas GET. En la comprobación inicial del selector nativo,
Maximo guardó P-BUS-001 en la OT 4394026 al seleccionarlo, sin pulsar Guardar. Se retiró
esa fila y se verificó desde otra sesión que la OT quedaba en APPR, con BUS-10, sin
PROBLEMCODE y sin filas de FAILUREREPORT, como antes de la comprobación. No se ejecutó
ningún cambio de estado. Se cerraron los navegadores aislados de consulta.

Los detalles verificables están en `metadata.verification`.
