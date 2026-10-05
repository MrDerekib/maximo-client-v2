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

Antes de publicar queda validar el ciclo real entre dos versiones empaquetadas
con la entrada Qt, incluida la copia y el reinicio, y revisar la primera
instalación por usuario. Estas pruebas no se sustituyen por las pruebas unitarias
del flujo. La adaptación del script de build se abordará después.
