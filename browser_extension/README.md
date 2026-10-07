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

La extensión no modifica la OT. En modo diálogo, requiere confirmar la impresión en Edge. Solo
funciona en `https://eam.indraweb.net/maximo/*`. No almacena credenciales ni URLs
de informes; conserva durante tres minutos el número de OT en memoria de la
extensión para asociar las ventanas BIRT con la solicitud.

El flujo con diálogo se ha validado en Maximo. La impresión directa aún requiere
una prueba con la impresora real; las pruebas automatizadas verifican la
configuración de Edge y la asociación segura de ventanas.
