# Reconstrucción de tablas — 10/11/2026

## Alcance

Rama experimental `rendimiento/tabla`, basada en `f0ca69b` (límite de OpenBLAS).
El commit `1ab3db7` incorpora el benchmark con el renderizador anterior; sirve
como punto de comparación sin las optimizaciones de tabla.

Se conserva QTableWidget. No se ha migrado a QAbstractTableModel ni modificado
el esquema de SQLite, las operaciones de Maximo o las prioridades de tareas.

## Cambios

- Antes de reconstruir se compara una instantánea de los datos devueltos por
  SQLite, las prioridades y las opciones que afectan al contenido visible.
  Si no cambian, se conservan las celdas, la ordenación y la selección.
- Un cambio de filtro sigue limpiando la selección aunque devuelva las mismas
  filas. Se actualizan los indicadores y el contador de resultados.
- Los cambios de tema recolorean las celdas existentes y sus iconos, sin consultar
  SQLite, perder selección o volver a crear los objetos de celda.
- Las reconstrucciones necesarias asignan las filas de una vez, bloqueando
  señales de celda y actualizaciones durante la carga. Reutilizan colores e iconos.
- Limpiar clientes y aplicar un perfil guardado no emiten refrescos intermedios
  con filtros parcialmente actualizados.
- La conciliación y la información ampliada no refrescan la tabla al terminar
  con cero modificaciones visibles. Sus contadores y mensajes siguen actualizándose.
- La actualización general siempre comprueba los datos: `0 nuevas, 0 modificadas`
  no implica que presencia y fecha de última aparición sean iguales.
- Las actualizaciones incrementales de almacén y prioridades invalidan la
  instantánea para que una reversión posterior no deje celdas obsoletas.

## Método

`tools/benchmark_table.py` genera 5.000 OTs ficticias con estados, clientes,
averías y detalles variados. Cada proceso utiliza una base SQLite y configuración
propias en un directorio temporal nuevo. No lee datos reales, no copia credenciales
ni crea sesiones de Edge o Maximo. La UI es offscreen y se procesan los eventos
pendientes de Qt para incluir el trabajo de actualización visual.

Tres procesos antes y tres después, con los mismos datos y OpenBLAS limitado
igual en ambos casos. Se mide cada operación y el mayor intervalo observado entre
pulsos de un QTimer de 10 ms: es una aproximación al bloqueo del hilo de interfaz,
no una medición de FPS ni una garantía de latencia en todos los equipos.

## Medianas

| Operación | Antes | Después | Reducción |
| --- | ---: | ---: | ---: |
| Refresco sin cambios | 759 ms | 13 ms | 98 % |
| Tres refrescos sin cambios | 2.289 ms | 36 ms | 98 % |
| Cambio de tema | 867 ms | 542 ms | 38 % |
| Filtrar a 100 filas | 64 ms | 59 ms | 7 % |
| Limpiar filtros, volver a 5.000 | 712 ms | 411 ms | 42 % |
| Un registro modificado | 760 ms | 480 ms | 37 % |
| Fecha de última aparición modificada | 771 ms | 460 ms | 40 % |

El mayor intervalo entre pulsos pasa de 752 a 13 ms en el refresco sin cambios,
de 2.280 a 36 ms en tres refrescos y de 853 a 528 ms al cambiar de tema.
Los casos sin cambios y el cambio de tema dejan de eliminar y crear 5.000 filas.
La memoria residente final fue de 238 a 240 MiB y la privada de 202,4 a 202,9 MiB;
son muestras orientativas, no evidencia de un ahorro de RAM.

Los seis procesos terminan con el mismo hash del texto y la visibilidad de la
tabla. Los resultados completos están en `benchmarks/tabla-20261110.json`.
La tabla aún puede bloquear perceptiblemente con cambios reales o al recolorear
muchas celdas; estos resultados no equivalen a virtualizar la tabla.

## Validación y reversión

329 pruebas sin fallos; 82 omitidas. Las nuevas regresiones verifican:

- Identidad de celdas, selección y ordenación cuando no cambian los datos.
- Limpieza de selección al cambiar filtros con resultados iguales.
- Presencia y fecha tras una actualización cuyo contador es cero.
- Cambio de colores sin consulta SQL ni pérdida de selección.
- Iconos de detalle al activar/desactivar las opciones de visualización.
- Reversión de un cambio incremental de almacén.
- Un único refresco al limpiar clientes o cambiar el campo de un perfil guardado.
- Finalización de tareas sin refrescar cuando no hay cambios.

Se verificó que configuración y credenciales reales no cambian durante la suite.
Falta la validación manual con Python visible y una build empaquetada.

Para volver al experimento anterior de OpenBLAS: cerrar dev y ejecutar
`git switch rendimiento/openblas`. Para volver al código de dev previo a ambos
experimentos: `git switch dev`. Reiniciar con `./run_dev.ps1` tras cambiar de rama.
