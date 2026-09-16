# Historial de cambios

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
