# Actualizaciones de la interfaz Qt

La aplicación distribuida consulta al iniciar la última release estable de GitHub.
Si su versión es superior a la instalada y tiene un ZIP con SHA-256 publicado,
ofrece descargar, instalar y reiniciar. También se puede iniciar desde
Configuración → Actualizaciones de Maximo Desktop → Actualizar ahora.

La descarga tiene progreso, cancelación y hasta tres intentos. Se verifica el
SHA-256 y el contenido del ZIP antes de preparar la instalación. El paquete debe
contener exactamente un `MaximoDesktop.exe` con sus dependencias.

La instalación pasa por el cierre ordenado de la UI: respeta los avisos de
configuración pendiente y de sesiones de Maximo abiertas, espera las tareas y
cierra Edge antes de lanzar el aplicador. El aplicador espera la salida del
proceso, copia el paquete sobre la carpeta instalada y reinicia la aplicación.
La base local y la configuración permanecen en las carpetas de datos del usuario.

Si el usuario cancela el cierre, el paquete queda preparado durante esa sesión y
puede reintentar con «Actualizar ahora». Cancelar la descarga o fallar la
verificación no inicia la instalación. Si no se puede lanzar el aplicador, la UI
permanece abierta y muestra el error.

La ejecución con `MAXIMO_DESKTOP_DEV=1` y la ejecución del script Python permiten
consultar releases, pero no instalar paquetes sobre el entorno de desarrollo.
El ZIP se guarda en una carpeta de caché reutilizada para evitar acumular una
copia completa en cada intento.

En la primera ejecución de un paquete Qt, la app copia la distribución completa
a `%LOCALAPPDATA%\MaximoDesktop\app`, crea el acceso directo y abre esa copia.
Si ya existe una instalación gestionada, compara las versiones del ejecutable;
solo sustituye una versión anterior y avisa si el paquete es más antiguo. La
copia se prepara antes de cambiar la carpeta instalada y se conserva la versión
previa. Los datos siguen en las
carpetas persistentes, fuera de `app`. El arranque Qt registra su actividad en
`logs/maximo_desktop.log`, separado del historial de Tkinter.

El script `build_app.ps1` compila la entrada Qt con Nuitka y empaqueta los
recursos de la extensión y de la interfaz. Para una prueba local se puede pasar
un intérprete alternativo con `-PythonPath`; en uso normal se emplea `.venv`.

Antes de publicar hay que validar dos paquetes Qt consecutivos en un perfil
aislado: primera instalación, actualización, cierre y reinicio. Las pruebas
unitarias no sustituyen ese ciclo real. La versión inicial V1 fue `1.0.0`; el parche actual es `1.0.1`. Ambas son
superiores a la última versión Tkinter (`0.9.9.4`).
