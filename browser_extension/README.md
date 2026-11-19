# Parte de reparación desde Edge

Esta extensión de Maximo Desktop añade «Imprimir parte» a la ficha de una OT en estado
`ISSUE` o `CLOSE` de Maximo. Abre «Ejecutar informes» → «Parte de reparación», envía el número
de OT, selecciona HTML en BIRT y abre la vista de impresión de Edge. En modo diálogo, Edge abre la impresión con blanco y negro y sin encabezados
ni pies; el usuario elige la impresora y confirma «Imprimir».
El clic de «Ejecutar informes» se hace en el contexto JavaScript de Maximo,
porque su menú depende de código de la propia página.

## Probar sin empaquetar

1. En Edge, abre `edge://extensions`, activa «Modo de desarrollador» y elige
   «Cargar extensión sin empaquetar». Selecciona esta carpeta.
2. Recarga la pestaña de Maximo y abre una OT en estado `ISSUE` o `CLOSE` de la que puedas
   imprimir el parte. Comprueba el número de OT antes de pulsar el botón azul.
3. Verifica que la OT mostrada en la vista de impresión es la misma. Si alguna
   ventana no se abre, comprueba si Edge ha bloqueado ventanas emergentes del
   sitio. Cancela la impresión si el documento o los ajustes no son correctos.

Al activar «Mostrar Imprimir parte en Edge» en Configuración de Maximo Desktop,
la app carga esta extensión automáticamente en las nuevas ventanas de OT que abre.
Desde el menú contextual de una OT en el listado también se puede elegir
«Imprimir parte…» o «Guardar parte en PDF…». Estas acciones cargan la extensión
solo para esa ventana, incluso si el botón de Edge está desactivado en la configuración.
La opción PDF selecciona la salida PDF original de BIRT y abre «Guardar como»;
no convierte el HTML. Si Edge impide la descarga, el PDF queda abierto para
guardarlo desde su visor.
«Mostrar diálogo de impresión» conserva el paso manual. «Imprimir directamente»
usa la impresora predeterminada de Windows y las preferencias de blanco y negro
sin encabezados; si no hay impresora predeterminada al abrir Edge, se muestra
el diálogo. El modo directo afecta a cualquier impresión de esa ventana Edge.
La opción de Configuración para cerrar las ventanas del parte solo se aplica al
modo directo; con diálogo manual, el visor y el HTML permanecen abiertos.

Para informes HTML cuyo campo Cliente de la OT contiene `TMB BOIXERES`, la extensión
prepara dos impresiones consecutivas usando el parámetro de Maximo «Incluir nombre y
tiempo reparación»: primero `S` (parte habitual) y después `N` (sin técnico ni tiempo).
La selección de `N` la completa Maximo Desktop con un click WebDriver real; por tanto,
esta variante requiere Edge iniciado y controlado por Maximo Desktop.
En otras OT el flujo sigue generando una sola impresión. Guardar PDF de Boixeres
obtiene las dos variantes PDF nativas de BIRT y las une localmente en un único
archivo, primero con técnico/tiempo y después sin ellos. Hay un solo «Guardar como».
El primer PDF se conserva temporalmente en storage.session hasta terminar la unión
o cancelar/fallar el proceso; no se guarda un documento parcial como resultado.
Después de recuperar el primer PDF se cierran su vista y su visor temporal antes
de abrir la segunda variante: BIRT solo permite una vista preliminar PDF abierta.
Solo se cierran las ventanas identificadas del trabajo actual; la ficha de la OT
se conserva. Para los demás clientes continúa la descarga PDF nativa de una sola
variante.

La unión utiliza pdf-lib 1.17.1, empaquetado localmente en `vendor/`, sin descargar
código durante la ejecución. Licencia MIT en `vendor/pdf-lib.LICENSE.md`.
Fuente: https://pdf-lib.js.org/ y paquete oficial npm `pdf-lib@1.17.1`.
SHA-256 de `vendor/pdf-lib.min.js`:
`0f9a5cad07941f0826586c94e089d89b918c46e5c17cf2d5a3c6f666e3bc694f`.
El script de build incorpora la biblioteca y su licencia.

Las acciones de informes no modifican la OT. Las acciones técnicas requieren su
revisión y confirmación explícitas. En modo diálogo, se confirma la impresión en Edge. Solo
funciona en `https://eam.indraweb.net/maximo/*`. No almacena credenciales ni URLs
de informes; conserva durante tres minutos el número de OT en memoria de la
extensión para asociar las ventanas BIRT con la solicitud.

El flujo con diálogo se ha validado en Maximo. La impresión directa aún requiere
una prueba con la impresora real; las pruebas automatizadas verifican la
configuración de Edge y la asociación segura de ventanas.


## Panel lateral de Edge

Las acciones se agrupan ahora en el panel nativo de Edge. Se abre pulsando
«MD · Acciones» en la ficha o el icono de la extensión; Edge permite cerrarlo
para recuperar el ancho de la página. No se abre automáticamente.

El panel consulta la pestaña activa de su ventana. Cada acción valida de nuevo
la pestaña, OT y estado antes de reutilizar los controles existentes de MD.
Iniciar y elegir anomalías requieren APPR; cambiar anomalías y revisar el cierre,
INPRG; imprimir, ISSUE o CLOSE. Los permisos de Configuración de MD siguen vigentes.
Una revisión abierta o proceso ocupado impide lanzar otra acción.

En esta primera integración, los formularios de anomalías y cierre siguen
apareciendo en la ficha de Maximo con sus confirmaciones originales. El panel
muestra los mensajes del proceso, sin deducir una impresión física ni confirmar
un enrutamiento por su cuenta. HTML, PDF desde MD, las dos variantes de Boixeres
y la preferencia de cerrar ventanas conservan el flujo actual.

Los controles antiguos se conservan como adaptadores internos, ocultos mediante
la capa de presentación. No se eliminan: MD necesita invocarlos para imprimir y
gestionar las solicitudes. El diseño lateral está separado de la lógica para
permitir incorporar otras presentaciones posteriormente.

Para probar desde Python, cerrar la sesión de Edge gestionada por MD y abrir
una nueva OT; cambiar archivos no recarga una extensión ya cargada. No hace falta
compilar. No es necesario borrar perfiles, configuración ni credenciales.


### Integración con las ventanas de MD

MD conserva el modo de automatización normal de EdgeDriver. Su aviso superior
se puede cerrar con la ×; no se excluye `enable-automation`, para evitar el aviso
de extensiones en modo desarrollador. Los perfiles temporales se mantienen.
La identidad pública del manifest permite fijar el mismo icono aunque cambie la
ruta de instalación. MD prepara `extensions.pinned_extensions` y marca la migración
de la barra como realizada para que Edge no borre esa lista en su primer arranque.
Estas preferencias se aplican únicamente al perfil temporal que abre MD, sin
modificar el registro, las políticas corporativas ni el perfil personal de Edge.

El cierre se solicita mediante el control DOM existente: una función global creada
por WebDriver puede no estar disponible en el mundo MAIN de la extensión. El clic
solo prepara la revisión; duración, fechas, acción final y confirmación conservan
sus validaciones. Los errores del script se devuelven explícitamente al panel para
evitar sustituir su causa por un genérico «No se pudo leer la ficha».


El botón flotante «MD · Acciones» se oculta mientras el panel está abierto y
reaparece al cerrarlo. Se usan los eventos nativos onOpened/onClosed y estado
temporal por ventana/pestaña para conservar la presentación tras recargar Maximo.
El icono de la barra superior utiliza una M azul sólida sobre fondo transparente, con PNGs
en varios tamaños. Se regeneran mediante `tools/generate_extension_icons.py`.


## Cierre dinámico desde el navegador

«Cerrar OT» sigue limitado a INPRG. Al pulsarlo se leen duración, fechas, Registro
completo (incluida paginación), clase de anomalía y soluciones, sin caché ni trabajos
de lectura en segundo plano. El diálogo conserva las fechas existentes, incluidos
sus segundos, mientras el usuario no las edite.

Las notas se muestran como historial y nunca se sobrescriben. La incidencia admite
texto libre y se guarda con un único prefijo `inc:`. Si hay varias, hay que elegir;
añadir otra exige confirmación. Las entradas CLIENTNOTE existentes requieren que el
usuario confirme que documentan sus trabajos/pruebas; las incidencias y notas de
sistema no se consideran por sí solas actividad técnica. Si faltan datos se pueden
añadir varias entradas con Resumen y Detalles.

Un Registro incompleto o ilegible bloquea la confirmación. Se revisan los valores
actuales de la ficha, incluidos los cambios pendientes del usuario, sin recargarla.
Tras confirmar se contrasta que no hayan cambiado los datos revisados, se añaden
las entradas nuevas y se validan los campos con la respuesta nativa de Maximo.
No se pulsa Guardar ni se reabre la ficha durante esta preparación: el enrutado
confirma los cambios. Después se comprueban el estado, las fechas y, si se añadieron
entradas, el Registro. Una creación o un cierre inciertos nunca se repiten
automáticamente. Desechar y Retener conservan sus confirmaciones y diálogos nativos.

Pruebas locales: `MAXIMO_BROWSER_TESTS=1` y `python -m unittest tests.test_browser_close_records tests.test_workorder_close tests.test_extension_panel`.
Las fixtures no acceden a Maximo ni usan perfiles o credenciales reales.
