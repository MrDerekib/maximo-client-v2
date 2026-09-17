# Historial de cambios

## 0.9.8.3 — Estado de sincronización y filtros ágiles

- Cada OT guarda si apareció en la última actualización correcta y cuándo se
  vio por última vez. La tabla muestra «Activo» o «No activo» como primera
  columna, con ayuda al pasar el ratón y un aspecto atenuado para el histórico.
- Una actualización fallida no modifica ese estado. Al volver a aparecer, una
  OT se reactiva automáticamente. Los cambios de seguimiento de una OT no
  activa permanecen locales mientras siga fuera del listado.
- El menú contextual permite copiar OT, número de serie o descripción, abrir la
  OT, cambiar seguimiento desde un submenú, eliminar OT no activas y consultar
  su sincronización sin depender de la celda seleccionada.
- La búsqueda rápida empieza por «Nº de serie» e incorpora acciones de cortar,
  copiar, pegar y seleccionar todo con clic derecho.
- Los filtros avanzados ofrecen calendario para las fechas y autocompletado de
  equipos por coincidencia parcial en su descripción.
- Tras una actualización correcta, se revisan en segundo plano hasta cinco OT
  no activas cuyo seguimiento sea «PDTE CONFIRMAR», «EN TALLER», «APPR» o
  «INPRG». La aplicación lee su
  estado real en Maximo, lo normaliza y actualiza el seguimiento local. Cada OT
  se consulta como máximo una vez cada 24 horas.

## 0.9.8 — Perfiles temporales de Edge controlados

- Los perfiles de Edge usados para actualizar, abrir OT o probar credenciales
  pasan de `%TEMP%` a `MaximoDesktop/cache/edge-profiles`. Esto evita las
  restricciones de permisos observadas en temporales corporativos.
- Tras cerrar Edge se reintenta la eliminación del perfil durante unos segundos.
  Si un proceso tarda en terminar, el mantenimiento puede retirarlo más adelante
  desde la carpeta controlada por la aplicación.

## 0.9.7 — Comprobación de credenciales

- Nuevo botón «Probar credenciales» en Configuración. Comprueba el acceso a
  Maximo con los valores escritos, sin guardarlos ni actualizar la base de datos.
  Ejecuta Edge en segundo plano con un perfil temporal que se cierra y elimina
  siempre. El resultado se muestra en la barra de estado y en un mensaje claro.
- La prueba no sobrescribe las credenciales ya guardadas, ni siquiera si falla.
  Tras una comprobación correcta, el usuario decide si desea conservar los
  valores mediante «Guardar configuración».

## 0.9.6.1 — Registro del arranque

- El inicio fuerza la configuración del registro de la aplicación incluso si
  Selenium u otra librería había añadido antes un handler de consola. Los logs
  vuelven a escribirse en `MaximoDesktop/logs` con nivel INFO.

## 0.9.6 — Almacenamiento persistente y descargas aisladas

- Nuevo árbol fijo en `%LOCALAPPDATA%\MaximoDesktop`, separado del código y de
  futuras actualizaciones del ejecutable. La GUI muestra las rutas y permite
  abrir la carpeta principal; no se añaden selectores editables.
- La primera ejecución copia la base de datos anterior mediante la API de backup
  de SQLite y verifica integridad y número de registros antes de activarla.
  También migra perfiles, backups y opciones de seguimiento. Los originales se
  conservan y el proceso no se repite una vez completado.
- Edge descarga cada exportación en una subcarpeta exclusiva dentro de
  `cache/downloads`, evitando procesar otros Excel de Descargas. Exportaciones,
  logs y temporales quedan agrupados bajo el mismo árbol.
- Las credenciales dejan de guardarse en texto plano y se protegen con Windows
  DPAPI para el usuario actual. Se eliminan del JSON anterior tras verificar la
  migración y se redactan los logs antiguos. Selenium y urllib3 ya no registran
  contenido de nivel DEBUG.
- Se elimina el archivo obsoleto `clientes_unicos.txt`; la GUI obtiene los
  clientes directamente de SQLite.

## 0.9.5.2 — Normalización al guardar y migración local

- Se normalizan los espacios en cliente, tipo de trabajo y seguimiento antes
  de importar en SQLite, así como en los cambios manuales de seguimiento.
- Migración única al inicializar la BD: corrige también las OT históricas que
  ya no aparecen en las descargas. Conserva NULL y el resto de columnas.
- Antes de modificar registros existentes, crea una copia completa de SQLite
  mediante su API de backup en `backups/`, junto a la base de datos. Si la copia
  falla, no modifica los registros. La actualización y su marca de migración
  se confirman en una sola transacción; no se repiten en siguientes arranques.
- La limpieza automática no elimina estas copias. Para recuperar los valores
  previos hay que cerrar la aplicación y restaurar la copia de la BD; revertir
  el código mediante Git no revierte los datos. Se conservan las protecciones
  de normalización al consultar y al cargar perfiles.

## 0.9.5.1 — Opciones duplicadas por espacios invisibles

- Normalización de espacios normales/no separables, repetidos y exteriores en
  opciones y consultas de cliente, tipo de trabajo y seguimiento. Los perfiles
  anteriores también normalizan sus selecciones al cargarse. Una sola opción
  «DAR SALIDA» encuentra tanto los valores importados como los editados localmente.
- Los datos originales de SQLite permanecen intactos.

## 0.9.5 — Filtros avanzados y perfiles de búsqueda

- Nueva función: panel avanzado plegado por defecto, combinado con el buscador
  sencillo. Equipo busca por palabras en la descripción. Selección múltiple de
  clientes, estado/tipo de trabajo y seguimiento; intervalo de fechas inclusivo
  en formato AAAA-MM-DD. No se añade filtro de planta.
- Dentro de un campo se acepta cualquiera de las opciones; entre campos deben
  cumplirse todos. Sin selección no se restringe ese campo. Los clientes del
  panel avanzado prevalecen sobre el selector sencillo, como indica la interfaz.
- Resumen persistente de filtros aplicados y contador de resultados; limpiar
  filtros reinicia ambos modos. Cerrar el panel no desactiva sus filtros.
- Perfiles con nombre: guardar, cargar, sustituir y eliminar. Se conservan en
  `data/search_profiles.json`, separado de credenciales y configuración; no se
  suben a Git. Se guardan criterios, no copias de las OT. Se arranca sin filtros.
- Opciones de filtros obtenidas de SQLite y refrescadas al consultar, incluyendo
  valores de seguimiento editados localmente. Los perfiles conservan selecciones
  aunque temporalmente no existan registros con esos valores.
- La numeración 0.9.5 corresponde a una función nueva; los parches posteriores
  usarán 0.9.5.1, etc. Punto anterior: commit `41fabab`.

Las correcciones menores usan un cuarto número: `0.9.4.1`, `0.9.4.2`, etc.
Se mantienen commits independientes para poder revertir cada cambio.

## 0.9.4.1 — Diagnóstico de limpieza y reintentos

- Renombrada desde la versión local 0.9.5 (no publicada). El comparador de
  actualizaciones y la interfaz reconocen el cuarto número de revisión.

- Los errores de limpieza incluyen el motivo exacto de Windows y la ruta que
  falló. No se modifican permisos ni se fuerza la eliminación de archivos.
- Se corrige el aviso de fallo al consultar GitHub: solo aparece después de
  agotar los intentos, con el número real (tres al iniciar, uno en consulta manual).
- Se comprobó en lectura que Windows deniega el acceso al temporal
  `maximo-ot-36usz1p1`, incluso fuera del entorno restringido. La corrección mejora
  el diagnóstico; no resuelve ni altera los permisos de estos restos.

## 0.9.4 — Limpieza automática

- Al iniciar, en segundo plano, y después de importar correctamente, se eliminan
  exportaciones antiguas de la carpeta configurada. Se conservan las cinco más
  recientes y todas las del último día. Solo se reconocen los nombres numéricos
  de ocho dígitos de versiones anteriores (con UUID opcional) y los nuevos
  `maximo-export-<uuid>.xls`. Otros nombres se conservan.
- Al iniciar se revisan las carpetas `maximo-ot-*`, `maximo-update-*`,
  `maximo-edge-*` y `maximo-download-*` del temporal de Windows y de la carpeta de
  descargas configurada. Solo se eliminan las de más de siete días que no estén
  usadas por procesos Edge. Si no se pueden consultar los procesos, se omite la
  limpieza. No se siguen enlaces ni junctions.
- Las sesiones actuales mantienen su limpieza al finalizar; las carpetas
  antiguas bloqueadas se conservan para intentar limpiarlas en otro arranque.
- Log rotativo junto al programa: 5 MiB por archivo y tres copias anteriores
  (aproximadamente 20 MiB en total). Los logs existentes en otros directorios
  permanecen intactos. Los archivos de log rotados se excluyen de Git.
- No se modifica la base de datos, la configuración ni el seguimiento local.
- Versión anterior: commit `6d39afb`. La reversión del código no recupera los
  archivos eliminados por la limpieza. La política se aplica al ejecutar esta
  versión; las pruebas solo limpian carpetas creadas para los tests.

## 0.9.3 — Optimización de acceso a Máximo

- Login y apertura del listado con esperas condicionadas (hasta 60 segundos por
  condición), en lugar de pausas fijas. Se mantiene el reintento de carga del login.
- Descarga en una subcarpeta temporal exclusiva dentro de la ruta configurada.
  Se espera hasta 180 segundos a un XLS nuevo, no vacío, sin descargas parciales
  pendientes y estable entre comprobaciones. Un timeout se comunica como error;
  no se importa un fichero antiguo ni se registra una actualización correcta.
- Exportaciones archivadas con un nombre único para conservar descargas previas.
- Una sola actualización de datos en curso por instancia de la GUI.
- Log con duraciones por etapa y tiempo total para medir el resultado real.
- Se mantienen sesiones nuevas e independientes para cada OT y para la
  actualización en segundo plano. No se reutilizan sesiones que puedan caducar.
- Se conservan las OT ausentes del listado y la edición local de seguimiento.
- Los filtros de descarga siguen desactivados. La función `apply_filter`, que
  actualmente no se ejecuta, conserva sus esperas anteriores.

### Validación

Pruebas locales con Selenium simulado y archivos temporales reales:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

La validación real pendiente consiste en actualizar el listado, abrir dos OT
simultáneas y actualizar de nuevo mientras ambas permanecen abiertas. Revisar los
tiempos y posibles timeouts en `maximo_client.log`. Las condiciones de pantalla
usan los identificadores del código anterior; no se ha inspeccionado el DOM de
la instalación de Máximo ni medido aún el ahorro contra el servidor.

Las esperas siguen el patrón de [esperas explícitas de Selenium](https://www.selenium.dev/documentation/webdriver/waits/).

### Recuperación

Rama de trabajo: `codex/optimizar-esperas-maximo`.

El commit `0ffdda0` guarda el estado local anterior a esta optimización, incluyendo
la edición local de seguimiento y `seguimiento_options.txt`. La carpeta `backup/`
se ha dejado intacta y fuera de los commits. Configuración, credenciales, base de
datos y logs tampoco se incluyen en los commits.

Para deshacer esta optimización conservando el historial, usar `git revert` con
el commit `perf: replace fixed Maximo waits with conditional downloads` visible en
`git log --oneline`. Esto revierte el código; no borra ni restaura los datos locales.
