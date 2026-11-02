# Maximo Desktop

Aplicación Windows para consultar y gestionar el seguimiento local de órdenes de
trabajo de IBM Maximo. La V1 utiliza Qt/PySide6, SQLite y Selenium con Microsoft
Edge. La distribución standalone no requiere Python instalado en el equipo del
usuario.

## Funciones

- Sincronización manual o periódica del listado de OT, con estado activo e histórico.
- Búsqueda, filtros combinados, búsquedas guardadas y prioridades importadas de XLS.
- Conciliación del estado de OT históricas y lectura opcional de averías y descripciones detalladas.
- Apertura de OT en Edge y exportación a Excel con enlaces locales a Maximo Desktop.
- Generación del parte de reparación para imprimirlo o guardar el PDF original de BIRT.
- Configuración de la extensión de Edge, impresión con diálogo o directa a la impresora predeterminada.
- Temas claro, oscuro y del sistema, con persistencia de la ventana y las columnas.
- Instalación por usuario y actualización de la aplicación desde GitHub Releases.
- Cierre ordenado: espera las tareas pendientes y cierra las sesiones de Edge abiertas por la app.

## Desarrollo

Usa una instalación de Python 3.14, Microsoft Edge y el entorno virtual de este
proyecto. Los módulos de la app no dependen de ninguna carpeta de la versión anterior.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Para trabajar con datos aislados:

```powershell
.\run_dev.ps1
```

Este script activa `MAXIMO_DESKTOP_DEV=1` y utiliza `%LOCALAPPDATA%\MaximoDesktop-dev`.
La ejecución directa de `ui_qt.py` sin esa variable utiliza los datos estándar de
`%LOCALAPPDATA%\MaximoDesktop`. La instalación de releases está deshabilitada en
la ejecución desde Python y en el modo de desarrollo.

## Estructura

| Archivo o carpeta | Uso |
| --- | --- |
| `ui_qt.py` | Punto de entrada e interfaz Qt |
| `maximo_client.py`, `updater.py` | Navegación en Maximo, sincronización y enriquecimiento |
| `db.py`, `search_filters.py` | SQLite, migraciones y filtros |
| `config.py`, `credential_store.py`, `app_paths.py` | Configuración, credenciales y rutas persistentes |
| `failure_catalog.py`, `failure_picker.py`, `resources/failure_catalog.json` | Catálogo validado y selección condicional de anomalías |
| `anomaly_diagnostics.py` | Registro rotativo de incidencias y opciones observadas en Maximo |
| `priority_importer.py`, `detailed_description.py`, `excel_export.py` | Prioridades, contenido enriquecido y exportación |
| `managed_install_qt.py`, `update_checker.py`, `update_installer.py` | Instalación y actualización de la aplicación |
| `maintenance.py` | Retención de exportaciones XLS procesadas |
| `deep_links.py`, `dev_link_launcher.pyw` | Apertura de enlaces de OT; el lanzador es específico de desarrollo |
| `browser_extension/` | Flujo del parte de reparación en Edge y sus pruebas |
| `icon.ico`, `ui_assets/` | Recursos visuales de la aplicación |
| `tests/` | Pruebas de la UI Qt y de los módulos de la app |
| `build_app.ps1`, `requirements.txt`, `version.py` | Compilación, dependencias y versión |

La interfaz y el instalador antiguos de Tkinter se conservan en el historial de
Git. Los módulos de negocio y las migraciones necesarios para los usuarios que
actualizan desde versiones anteriores siguen formando parte de la V1.

## Instalación y actualización

```powershell
.\build_app.ps1
```

El script usa `.venv` y crea `release\MaximoDesktop-<versión>`, con la carpeta
standalone y `MaximoDesktop-v<versión>-windows.zip`. La extensión se empaqueta con
sus archivos de ejecución y el catálogo de anomalías; las pruebas y la documentación quedan en el
repositorio. `-Force` permite reemplazar la compilación de esa misma versión y
`-KeepBuild` conserva los archivos intermedios de Nuitka.

Distribuye el ZIP completo. Al abrir el ejecutable por primera vez, la app copia
la distribución a `%LOCALAPPDATA%\MaximoDesktop\app`, crea el acceso directo y
abre la copia instalada. Una versión superior puede reemplazar una instalación
anterior; se conserva una copia de recuperación y los datos quedan fuera de `app`.

Para la actualización remota, la release estable debe ofrecer un ZIP compatible
con su SHA-256 publicado. La app comprueba la versión, verifica la descarga y pasa
por el cierre ordenado antes de instalar y reiniciar. Los detalles están en
[docs/ui-updates.md](docs/ui-updates.md).

## Datos y registros

```text
%LOCALAPPDATA%\MaximoDesktop\
├── app/                    # distribución instalada
├── config/                 # configuración y credenciales protegidas con Windows DPAPI
├── data/                   # SQLite y búsquedas guardadas
├── backups/                # copias de seguridad de SQLite
├── logs/maximo_desktop.log  # registro rotatorio de la aplicación
└── cache/
    ├── downloads/          # descarga aislada de Maximo
    ├── exports/            # XLS procesados sujetos a retención
    ├── edge-profiles/      # perfiles temporales de Edge
    └── updates/            # paquetes de actualización
```

El arranque prepara los directorios y migra el esquema de SQLite cuando sea
necesario. La migración desde el almacenamiento antiguo verifica la copia de los
datos y conserva los originales. Los datos personales y las builds están
excluidos del control de versiones.

## Comprobaciones

### Inicio opcional de OT

En **Configuración → Extensión de Edge → Órdenes de trabajo**, activa
**Mostrar «Iniciar OT» y «Cambiar anomalías» en Edge** y guarda los cambios. Está desactivado por defecto.
«Abrir OT» y los enlaces del listado siguen abriendo la ficha sin iniciarla.

Al habilitarlo aparece un botón en las nuevas ventanas de Maximo abiertas desde
MD. Utiliza la sesión abierta y muestra el progreso en el botón. El inicio está
disponible únicamente en Edge; se ha retirado la acción del menú contextual y
la ejecución del inicio en segundo plano desde MD.

En **Al pulsar Iniciar OT** se elige entre:

- **Solo iniciar:** conserva la clase y los códigos actuales.
- **Iniciar y establecer anomalías:** aplica la clase y ruta predeterminadas.
  Los desplegables son condicionales: cambiar un padre limpia sus descendientes,
  y es obligatorio completar una ruta válida. Hay rutas que terminan en un
  problema o una causa, y clases que comienzan directamente por una causa.

Las instalaciones anteriores conservan `RFN-70 → OTROS-01 → OTROS-02 → OTROS-03`
como predeterminado. **Elegir anomalías…** junto al botón de Edge permite escoger
otra combinación, o solo iniciar, para esa ejecución; no cambia la configuración
de MD. Cancelar el diálogo no modifica la OT.

La misma opción **Mostrar «Iniciar OT» y «Cambiar anomalías» en Edge** habilita
**Cambiar anomalías** cuando la OT ya está en `INPRG`. Abre el selector condicional
y permite confirmar con **Guardar anomalías**. La aplicación usa los controles
nativos, guarda y verifica la combinación y vuelve a la pestaña de origen.
Esta acción no enruta, inicia ni cierra la OT, ni cambia los predeterminados de MD.
Solo actúa mientras la ficha siga correspondiendo a la misma OT en `INPRG`.
La revisión del cierre y el cambio de anomalías se bloquean entre sí.

El flujo solo inicia OT en `APPR`. En modo configurado usa la clase y
**Seleccionar códigos de anomalía** de Maximo. Si cambia una jerarquía existente,
primero la suprime desde los controles nativos y confirma su guardado.
Cada clic avanza al siguiente nivel y la hoja cierra el diálogo; no se pulsan
los botones Seleccionar ni Seleccionar y regresar. La combinación se verifica
antes de iniciar. Si ya era correcta, se conserva. Una opción ausente o una
selección guardada inválida detiene la operación en lugar de usar otra ruta.
La rama `RFN-20 / P-RFN-139 / C-RFN-062 / S-RFN-263` no se ofrece, según las
comprobaciones documentadas en `docs/catalogos/anomalias/2026-10-28/`.

El flujo continúa el aviso conocido de problema ya informado y
acepta **Iniciar orden**. Se detiene al
confirmar `INPRG`; una OT ya iniciada no vuelve a enrutarse. Un diálogo desconocido
detiene la operación y muestra su mensaje para revisión.

Después de cambiar la clase y tras completar el selector se
guardan los cambios. La automatización no modifica los campos de
Soluciones mediante sus lupas. El guardado espera la respuesta del servidor y su
confirmación; también contempla el aviso de problema ya informado en ese paso.
Los controles deshabilitados se detectan también en el contenedor del menú.
Si Guardar está deshabilitado, se recarga la ficha únicamente para comprobar
que la clase, las filas y los códigos de Soluciones esperados se conservan.
Solo entonces se continúa; los datos que desaparezcan o no coincidan detienen
la operación. Si no se localiza ningún control Guardar, no se asume un guardado.

Si la primera pulsación de Enrutar no abre el diálogo, se comprueba de nuevo
el estado y se reintenta, con un máximo de tres pulsaciones. Los controles que
Maximo reemplaza durante una actualización se vuelven a localizar sin repetir
el proceso completo. Si la acción ya tuvo efecto, no se vuelve a enviar.
Los contenedores de avisos y diálogos que Maximo conserva ocultos no bloquean el
inicio: se comprueba la visibilidad de sus paneles, tanto en el botón como en la
automatización. Un aviso visible sigue requiriendo revisión.

### Registro de incidencias de anomalías

Si falla la validación o aplicación de una combinación, se crea una entrada en
`logs/anomalias_incidencias.jsonl`, dentro de la carpeta de datos de MD (o
`MaximoDesktop-dev` durante el desarrollo). La entrada conserva la fecha UTC,
la OT, la combinación solicitada, el nivel esperado, la etapa y el error,
además de los códigos, tipos y descripciones que se consultaron en Maximo.

Se conservan las opciones observadas antes de filtrar y el resultado filtrado,
con el filtro y la paginación disponibles. Son capturas de las páginas
consultadas: una lista parcial o recortada no se presenta como catálogo completo.
No se recorren páginas adicionales al producirse el error ni se elige otra
combinación automáticamente.

El registro rota a partir de 1 MiB y conserva tres copias anteriores. No contiene
credenciales, cookies, URLs de sesión ni HTML de la página. Un fallo al escribir
el registro no sustituye el error original ni modifica la configuración.

### Cierre de una reparación desde Edge

En **Configuración → Extensión de Edge**, activa **Mostrar «Cerrar OT» en
Edge**. Solo está disponible en una OT en `INPRG`. No hay una acción de cierre
en el menú contextual de MD ni se cierra una OT al abrir su ficha.

El botón consulta **Horas totales de reparación** en Consumos Actuales y las
fechas **Inicio real** y **Finalización real** en Orden de trabajo. Abre una
revisión que pide el inicio real, mostrando el que figura en Maximo como
referencia, y permite introducir o corregir la duración. La duración
admite únicamente múltiplos positivos de `0,25 h` (15 minutos); `0,75` son 45
minutos y `1,25` son 75 minutos. No se redondean valores no válidos.
La finalización se calcula a partir del inicio y de la duración, y no puede ser
posterior a la hora actual. Esta condición se comprueba también antes de guardar.

Cancelar esta revisión no cambia los datos. **Confirmar cierre** guarda la
duración y fechas escribiéndolas con el teclado en los campos de Maximo y pulsando
Tab para validarlos. Antes de enrutar se recarga la ficha y se comprueba que se han guardado
los tres valores. Si los datos cambiaron desde la revisión, la confirmación ha
caducado o Maximo muestra un error, se detiene sin intentar el cierre.

La operación termina en `ISSUE`, pendiente de salida del almacén. Nunca se sigue
enrutando una OT que ya está en ISSUE ni se busca el estado CLOSE. El botón de
enrutar tiene hasta tres intentos si no aparece ningún diálogo. La aceptación
final de «Cerrar OT» se envía una sola vez; si su resultado no se puede confirmar,
se pide revisar el estado en Maximo. El cierre es irreversible y debe probarse
con una OT preparada expresamente para ello.

### Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test browser_extension/tests/workflow.test.js
```

Las pruebas de navegador son opcionales y utilizan exclusivamente la página HTML
local de `tests/fixtures`, sin autenticarse ni modificar Maximo:

```powershell
$env:MAXIMO_BROWSER_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.test_workorder_start -v
Remove-Item Env:MAXIMO_BROWSER_TESTS
```

Las pruebas de Qt se ejecutan sin mostrar ventanas y con almacenamiento aislado.
Las pruebas automatizadas se complementan con la comprobación del ejecutable:
instalación, actualización, apertura de OT, cierre y reinicio. El flujo de Maximo
requiere acceso al servidor y credenciales configuradas.

La extensión y sus modos de impresión se describen en
[browser_extension/README.md](browser_extension/README.md).

## Uso

Herramienta de productividad de uso interno. Autor: Joan Camps.
