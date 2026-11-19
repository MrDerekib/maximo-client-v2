# Prueba de límite de OpenBLAS — 10/11/2026

## Alcance

Rama experimental `rendimiento/openblas`, basada en `76bcf6c`.
El commit `ba67bef` conserva el benchmark antes de cambiar el comportamiento.
No cambia la tabla, SQLite, los hilos de MD ni los de Edge: establece por defecto
`OPENBLAS_NUM_THREADS=1` antes de importar Pandas/NumPy. Respeta cualquier valor
explícito establecido en el entorno.

## Método y seguridad

- Copia congelada de la base de desarrollo: 2.483 filas visibles.
- Un mismo export HTML/XLS existente de 1.000 filas, sin nuevas descargas.
- Tres procesos nuevos antes y tres después de aplicar el cambio.
- Confirmación adicional mediante cuatro pares intercalados, alternando el orden
  de 20 hilos nativos (comportamiento observado inicialmente) y 1 hilo.
- UI Python offscreen con tema y funciones de datos reales. Cada proceso dispone
  de su propia copia SQLite y su propio directorio de aplicación temporal.
- Las fuentes SQLite se abren con `mode=ro`. No se copian credenciales, no se
  crean sesiones de Maximo y no se ejecutan operaciones reales.
- Los archivos de configuración y credenciales reales permanecieron intactos
  durante la suite de validación.

## Resultados de la comparación intercalada

Medianas de cuatro ejecuciones por ajuste, con la ventana cargada:

| Métrica | 20 hilos de OpenBLAS | 1 hilo de OpenBLAS |
| --- | ---: | ---: |
| Hilos totales | 24 | 5 |
| Memoria privada comprometida | 770,88 MiB | 160,26 MiB |
| RAM residente | 198,24 MiB | 197,08 MiB |
| Importar bibliotecas | 1,400 s | 1,452 s |
| Construir ventana | 0,510 s | 0,544 s |
| Refrescar tabla | 0,375 s | 0,378 s |
| Aplicar filtro sin coincidencias | 0,027 s | 0,024 s |
| Limpiar filtro | 0,350 s | 0,378 s |
| Aplicar tema y reconstruir tabla | 0,652 s | 0,734 s |
| Procesar el export | 0,195 s | 0,190 s |
| Importarlo en SQLite temporal | 2,163 s | 1,888 s |

Los tiempos varían entre procesos: no se atribuye al cambio una aceleración
significativa ni una mejora de fluidez. La reducción consistente es de unos
611 MiB de memoria privada comprometida y 19 hilos; la RAM residente apenas varía.
La diferencia de tiempo de importación SQLite tampoco se toma como una mejora
causal de OpenBLAS, ya que el trabajo principal es de SQLite y no de matrices.

Las 14 ejecuciones producen el mismo hash del DataFrame transformado y el mismo
hash de las columnas de negocio de la base resultante. Todas devuelven 0 OTs
nuevas y 50 actualizadas en su copia temporal. Se excluye del hash la fecha de
última aparición, que necesariamente cambia al ejecutar una importación.

Suite: 321 pruebas, sin fallos; 82 omitidas. Falta la comprobación de una build
empaquetada antes de promover el cambio a release.

## Repetir y revertir

`tools/benchmark_openblas.py` permite congelar entradas y ejecutar las fases
`before` y `after` en una carpeta nueva `maximo-perf-*` directamente dentro de
`TEMP`. Las salidas JSON no contienen registros ni credenciales. Las copias de
entrada y los perfiles temporales quedan en esa carpeta, fuera de Git.
Para comparar ambos ajustes sobre el mismo código se puede establecer
`OPENBLAS_NUM_THREADS=20` o `1` solo en el proceso de prueba.

Para volver al comportamiento previo sin borrar commits, cerrar la app de
desarrollo y ejecutar `git switch dev`; para continuar el experimento,
`git switch rendimiento/openblas`. La aplicación debe reiniciarse para que
OpenBLAS lea el nuevo límite durante su carga.
