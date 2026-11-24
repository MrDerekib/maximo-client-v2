# Organización de Configuración

La UI Qt mantiene cuatro pestañas con los mismos controles y ajustes existentes:

| Pestaña | Contenido |
| --- | --- |
| General | Credenciales, actualizaciones de MD, tema y legibilidad |
| Datos y sincronización | Actualización de Maximo, conciliación, información ampliada, prioridades locales, mantenimiento y rutas |
| Técnico y extensión | Inicio/cierre y anomalías de Edge, impresión y SAT técnico |
| Almacén | Activación de acciones y detalles de SAT |

Cada pestaña conserva su desplazamiento y sus controles al cambiar a otra. No se
recargan los datos ni se guardan ajustes al cambiar de pestaña. El botón **Guardar
cambios** y el aviso de cambios pendientes quedan fuera del área desplazable y
afectan a todas las pestañas. Las columnas se apilan cuando falta ancho; un grupo
único como Almacén usa todo el ancho disponible.

## Acciones de datos

En **Maximo Desktop Menú** puedes revisar las OTs no activas, completar la
información pendiente o cancelar una lectura en curso. En **Datos y
sincronización** se mantienen los contadores, las preferencias de segundo plano
y los tamaños de lote.

## Operaciones

En Listado, **Operaciones** abre los intentos que requieren revisión. El contador
incluye también los avisos silenciados. **Historial reciente** muestra los
resultados guardados por MD, entre ellos los intentos resueltos por otra vía.
Selecciona una OT para ver el último paso y, si sigue pendiente, revisarla.

## Barra lateral

Una cabecera compacta permanece visible encima de las páginas. El icono de panel
permite ocultar y recuperar la barra lateral. El menú «Maximo Desktop» da acceso
a Listado y Configuración también con el lateral oculto, sin duplicar botones
junto a los títulos. El icono sigue el color de texto del tema activo.

La preferencia `sidebar_collapsed` se conserva para el próximo arranque y es
independiente de los cambios pendientes de Configuración. Ocultar el lateral no
aplica la escritura pendiente de credenciales u otros campos. La tabla gana el
ancho liberado sin reconstruir las celdas ni consultar Maximo o la base de datos;
conserva filtros, orden y selección.

Los menús contextuales y sus submenús utilizan fondo, texto, selección y estados
deshabilitados explícitos de la paleta de MD para evitar mezclar texto del tema
oscuro con fondos nativos de Windows.

El lateral ofrece Cargar Excel de prioridades, Exportar a Excel y búsquedas guardadas; la navegación de
secciones está en el menú superior, que también permite exportar con el lateral
oculto. El contador y Limpiar selección comparten la fila inferior del recuadro
de filtros. El botón de limpiar solo aparece con filas seleccionadas y reserva
su altura para no desplazar el formulario.

## Selección de OTs

La franja izquierda de 44 px es clicable en toda la celda. Las marcas se guardan
por OT con índices persistentes; ordenar conserva el lote y cambiar el foco no
lo elimina. Un clic normal consulta una fila; doble clic abre su ficha. Ctrl y
Mayús permiten seleccionar, Espacio alterna la fila activa y Ctrl+A marca las
filas visibles. La cabecera marca todas las visibles; Limpiar selección y Esc
vacían el lote. Un clic en una zona vacía de la tabla o fuera de ella también lo
limpia; se exceptúan botones de acción y otras ventanas/menús para no perder el
lote antes de usarlo. Cambiar el foco mediante teclado no elimina las marcas.
Un clic sobre otra fila conserva el lote: la fila activa y las marcas son distintas.

El menú contextual sobre una OT marcada usa el lote. Sobre una no marcada usa
solo esa OT sin borrar las marcas anteriores. El contexto se descarta al cerrar
el menú; las acciones congelan el listado de OTs que muestran para confirmar.
Cambiar filtros o reconstruir resultados limpia la selección; las filas ocultas
se excluyen. El selector usa la cabecera vertical, sin desplazar columnas de datos
ni introducir columnas en el Excel exportado. No escribe estados de casilla en
las celdas del modelo y no crea un widget por fila.

## Actualización visual

El icono de Actualizar Maximo gira mientras la petición del listado está pendiente
o en ejecución, incluidas las actualizaciones automáticas. Se detiene y vuelve a
su orientación inicial al completar, fallar o no poder iniciar la tarea. Las tareas
posteriores (conciliación/ampliación) mantienen sus avisos independientes. El
color sigue el tema y el temporizador de animación se detiene cuando no hay una
petición de actualización. Cargar Excel reutiliza el importador validado de
prioridades `.xls`, con la misma revisión previa antes de guardar.

La barra lateral se redimensiona arrastrando su borde derecho (210–420 px).
El ancho se guarda al soltar el separador y se recupera al volver a mostrarla
y en el siguiente arranque. El botón superior sigue permitiendo ocultarla por completo.
