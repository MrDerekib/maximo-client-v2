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

## Novedades tras actualizar

El primer arranque del exe con una versión nueva muestra un diálogo con su
changelog. Se presenta después de abrir la ventana principal y antes de comprobar
si existe otra actualización, evitando superponer ambos avisos. Al cerrar el
diálogo se registra la versión mostrada y no vuelve a aparecer en los siguientes
arranques de esa versión.

Las notas se toman del cuerpo Markdown de la release de GitHub, conservado al
consultar actualizaciones. Si no hay una copia para la versión instalada, se usa
solo su sección de `CHANGELOG.md`, que el script incluye en la distribución.
El popup muestra únicamente el bloque `### Resumen` de esa versión, hasta el
siguiente título. «Ver todos los cambios» abre la release con las notas completas.
El resumen y el detalle se mantienen juntos en `CHANGELOG.md`; al preparar la
release se utiliza esa misma sección. Si una caché antigua no incluye resumen,
se prioriza el resumen local; las versiones antiguas sin bloque conservan su visor.
Esto permite mostrar las notas sin conexión y también al actualizar desde un
cliente anterior que todavía no guardaba las notas de GitHub. Si no hay notas
para esa versión se omite el aviso vacío y queda constancia en el log.

No hay un segundo changelog que mantener. `config/release_notes_state.json` es
estado generado automáticamente: guarda la versión ya mostrada y una única
release en caché, fuera de la carpeta actualizable `app`. Un rollback no reduce
la versión registrada ni provoca que se repitan unas notas ya vistas. La caché
de notas tiene longitud limitada y se reemplaza en las siguientes consultas.

Las configuraciones nuevas se inicializan con la versión instalada y no reciben
un aviso de actualización en su primera instalación. Una configuración heredada
sin historial muestra las notas una vez al estrenar esta función. Python/dev no
abre el diálogo automático ni marca como leídas las novedades del exe. El visor
respeta el tema de la app y no carga imágenes ni recursos externos del Markdown.

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
unitarias no sustituyen ese ciclo real. La versión inicial V1 fue `1.0.0`;
las versiones Qt de la serie `1.x` son superiores a la última versión Tkinter (`0.9.9.4`).
