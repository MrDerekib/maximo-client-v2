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
sus cuatro archivos de ejecución; las pruebas y la documentación quedan en el
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

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test browser_extension/tests/workflow.test.js
```

Las pruebas de Qt se ejecutan sin mostrar ventanas y con almacenamiento aislado.
Las pruebas automatizadas se complementan con la comprobación del ejecutable:
instalación, actualización, apertura de OT, cierre y reinicio. El flujo de Maximo
requiere acceso al servidor y credenciales configuradas.

La extensión y sus modos de impresión se describen en
[browser_extension/README.md](browser_extension/README.md).

## Uso

Herramienta de productividad de uso interno. Autor: Joan Camps.
