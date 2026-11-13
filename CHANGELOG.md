# Historial de cambios

## 1.3.0 — Operaciones de técnico y nuevo panel de Edge

### Resumen

- **Técnico:** enviar a SAT externo, finalizar reparaciones y declarar equipos irreparables desde MD.
- **Técnico:** incidencia, trabajos, pruebas, duración y fechas en una revisión previa; cierre más ágil.
- **Edge:** nuevo panel lateral con las acciones disponibles para la OT y cierre con revisión de datos.
- **Partes:** las dos variantes de Boixeres también se guardan juntas en un único PDF.
- **Formularios:** se conserva lo escrito durante la consulta y se aprovecha la avería local.
- **Roles:** menús diferenciados de Técnico y Almacén según las opciones habilitadas.

### Técnico · Envío a SAT externo desde MD

- Nueva acción «Enviar a SAT Externo · Técnico», individual o en lote, para OTs en
  APPR. Es la acción del rol de técnico; no es la recepción con derivación a SAT
  que realiza almacén.
- Revisión previa de anomalías y soluciones, horas en múltiplos de 0,25 h,
  incidencia de texto libre y motivo por OT. La incidencia se registra con un
  único prefijo `inc:`; admite números, `stock`, `sin inc` u otro texto de la etiqueta.
- El motivo se propone a partir de la avería local; Maximo solo se consulta para
  obtener esa descripción cuando no está disponible en MD.
- Preparación y envío en una misma sesión de Edge. Se espera la validación nativa
  de los campos y la disponibilidad del enrutado antes de confirmar.
- Progreso y resultado por OT, petición revisada conservada y trazas por operación.
  Un fallo anterior a Enrutar permite abrir «Reintentar preparación…», revisar los
  datos y confirmar otro intento. Si ya se intentó enrutar o confirmar, solo se
  reverifica el resultado; no se repite la acción automáticamente.

### Técnico · Finalizar reparación y declarar irreparable desde MD

- Entradas independientes «Dar salida · Técnico» y «Declarar irreparable · Técnico»
  en el menú contextual. Comparten revisión, con la acción invocada seleccionada.
- Se admiten OTs APPR e INPRG. Si todavía no se han iniciado, se inicia la OT como
  parte del proceso expresamente revisado antes de finalizarla.
- Incidencia libre, varias entradas de Registro con resumen y detalles, anomalías
  y soluciones, duración en cuartos de hora y fechas reales de reparación.
- Se puede indicar inicio o finalización y calcular la otra fecha con la duración.
  «Ahora» toma la finalización actual; el selector muestra fecha y hora y permite
  ajustar los minutos en pasos de cinco, sin exigir segundos.
- El motivo de desecho solo aparece al declarar irreparable. Se propone la avería
  como texto editable y se respetan los cambios o borrados manuales, incluida una
  edición realizada mientras se consulta la ficha.
- La consulta inicial conserva la incidencia, duración y entradas que se hayan
  escrito durante la carga. Los valores vacíos de Maximo no borran esos datos.
- Preparación sin Guardar después de cada registro ni recargas entre pasos: los
  campos se validan y el enrutado confirma los cambios. Solo se conserva el
  guardado necesario para eliminar una jerarquía de anomalías anterior cuando
  se sustituye por otra.
- Confirmación explícita antes de una acción irreversible. Se comprueban equipo,
  estado, fechas, Registro e historial; el cierre normal se verifica en ISSUE y
  el desecho en CLOSE. Un resultado incierto queda para revisión, sin repetirlo.
- Impresión opcional después de verificar. Un fallo al preparar el parte permite
  volver a solicitarlo sin iniciar, cerrar ni desechar de nuevo la OT.

### Almacén · Recepción y expedición

- Las operaciones de almacén se agrupan en su propio submenú y siguen requiriendo
  activar «Mostrar acciones de almacén» y los permisos de la cuenta de Maximo.
- Se conserva su operativa de confirmar recepción, confirmar y enviar a SAT
  interno/externo y dar salida del almacén, individualmente o en lote, con informe
  de progreso, pendientes y reverificación.
- Se distinguen las acciones y estados de técnico y almacén. «Dar salida · Técnico»
  finaliza la reparación; «Dar salida del almacén» realiza la expedición posterior.
  El seguimiento local y el estado leído en Edge se contrastan según cada acción.

### Extensión de Edge · Panel lateral y cierre dinámico

- Panel lateral con OT, cliente, estado, acciones disponibles y seguimiento. El
  acceso flotante se oculta al abrirlo y reaparece al cerrarlo.
- Icono M azul fijado en las sesiones temporales que abre MD. Se conserva el
  arranque de Edge con el aviso habitual de navegador automatizado.
- «Cerrar OT» consulta Registro, duración, fechas y anomalías antes de mostrar la
  revisión. Permite completar incidencia y trabajos cuando faltan y reutiliza las
  entradas existentes sin duplicarlas ni modificarlas.
- La preparación del cierre no pulsa Guardar ni reabre la ficha. Se mantienen las
  comprobaciones de campos y el resultado del enrutado.
- Las acciones de impresión recuperan el foco de la ficha; si el panel lo retiene,
  se cierra para permitir continuar y se muestra el progreso en el acceso flotante.
- El panel utiliza las acciones habilitadas para el estado real de la OT. El envío
  técnico a SAT y la preparación completa desde el menú de MD siguen disponibles
  desde MD; no se presentan como nuevas operaciones de almacén en Edge.

### Partes de reparación y PDF

- Boixeres mantiene sus dos variantes HTML: una con técnico y tiempo y otra sin
  esos datos. Funcionan desde la extensión y desde el menú contextual de MD, también
  con una OT ya cerrada.
- Guardar PDF de Boixeres obtiene las dos salidas PDF originales de BIRT y las une
  localmente, en ese orden, en un único archivo y con un solo diálogo «Guardar como».
- Se cierra la primera vista preliminar PDF y su visor temporal antes de generar
  la siguiente, evitando el aviso de BIRT de que ya hay una vista abierta.
- Si falla una variante, no se entrega un PDF parcial como si contuviera ambas.
  Para los demás clientes se mantiene la descarga del PDF original de una variante.
- La unión incluye pdf-lib con licencia MIT dentro de la aplicación; no descarga
  código durante el uso. El script de build incluye panel, formularios, iconos y licencia.
- Limitación de BIRT: el PDF nativo puede contener «The resource of this report item
  is not reachable» cuando el servidor no carga un recurso del diseño. Se conserva
  el contenido original; esta versión no modifica ni oculta esos avisos.

### Validación y despliegue

- Pruebas locales de preparación sin guardados, varias entradas, APPR/INPRG,
  cierre/desecho, confirmaciones inciertas, recuperación, formularios y panel.
- Validación de la candidata: 221 pruebas Python correctas (incluido Edge aislado)
  y 44 pruebas JavaScript correctas. Las pruebas locales no usan cuentas reales.
- Unión PDF comprobada con documentos locales en Node y Edge, orden de páginas,
  continuidad entre variantes y una única selección de archivo.
- El cierre normal y el desecho desde MD se han comprobado en operaciones reales.
  El último ajuste de vista preliminar del PDF conjunto de Boixeres deberá
  confirmarse en la build de prueba antes de publicar.
- La build y su instalación/actualización se validarán localmente antes de publicar
  este borrador. Las acciones conservan los permisos y comprobaciones de Maximo.

## 1.2.3 — Recuperación de almacén y mejoras de fluidez

### Resumen

- Los lotes de almacén comprueban de nuevo los resultados inciertos sin repetir la operación.
- Puedes revisar y recuperar operaciones pendientes incluso después de reiniciar MD.
- Tabla más fluida: menos reconstrucciones al actualizar, limpiar filtros y cambiar de tema.
- La actualización del listado muestra su fase y tiempo transcurrido, recuperando el aviso tras otros mensajes.
- Menor uso de hilos internos de cálculo y más información para diagnosticar incidencias de almacén.

### Recuperación de operaciones de almacén

- Si se pierde la respuesta tras intentar enrutar o confirmar, la OT queda pendiente
  de verificar y el lote continúa con las siguientes. Al acabar, MD realiza una
  segunda pasada de consulta desde una sesión independiente, sin reenviar la acción.
- Nuevo botón «Reverificar pendientes» en el reporte. También puedes acceder desde
  Configuración → Almacén → «Revisar operaciones pendientes…». Al arrancar, MD ofrece
  revisar las operaciones que hayan quedado pendientes.
- Los registros persistentes conservan la acción, la identidad del equipo y el paso
  alcanzado. Una OT con una operación pendiente queda bloqueada para nuevos envíos
  hasta resolver su comprobación, evitando reintentos por error.
- Si la operación ya está verificada en Maximo pero falla el guardado local, la
  recuperación reintenta únicamente ese guardado. Los resultados correctos del resto
  del lote se conservan y el reporte original se actualiza cuando se resuelve el caso.
- Una recepción ya en APPR o una salida ya en CLOSE se identifica como «Ya estaba
  completada», sin volver a enrutar. Para confirmar una derivación SAT se comprueban
  tanto el estado como una nueva entrada del historial de la acción correspondiente.
- Los fallos transitorios de lectura anteriores al intento de enrutar pueden
  reintentarse una vez. Desde que se intenta enrutar, la recuperación solo consulta
  el resultado: no repite Enrutar, Aceptar ni la confirmación de detalles SAT.
- Más evidencias por OT para diagnóstico y recuperación, sin guardar credenciales,
  tokens ni el texto de los detalles SAT. Los nuevos registros de recuperación se
  aplican a las operaciones realizadas con esta versión; no importan lotes antiguos.

### Progreso de actualización

- La actualización manual y automática mantienen un aviso con la fase real y el
  tiempo transcurrido: inicio de sesión, exportación y descarga, procesamiento y
  guardado. No se muestra un porcentaje estimado sin datos que lo respalden.
- Los avisos de otras acciones tienen preferencia temporal; al desaparecer se
  recupera la fase más reciente de la actualización. También se muestra si está
  esperando o pausada por una acción prioritaria.
- Corregida la desaparición del estado a los siete segundos al sustituirlo un
  aviso temporal del coordinador de tareas. El seguimiento se detiene al completar
  la actualización o fallar y deja visible su resultado.

### Rendimiento y visualización de la tabla

- Los refrescos con datos iguales conservan las celdas, la ordenación y la selección.
  Cambiar de filtro sigue limpiando la selección aunque devuelva los mismos resultados.
- Cambiar de tema recolorea la tabla existente y sus iconos sin consultar de nuevo
  los datos ni reconstruir todas las filas.
- Cargas de tabla agrupadas para reducir las señales y repintados intermedios.
  Limpiar filtros y aplicar búsquedas guardadas evitan refrescos redundantes.
- Las tareas de conciliación e información ampliada no reconstruyen la tabla si
  terminan sin cambios. Las actualizaciones generales siguen comprobando presencia
  y última aparición, aunque no haya OTs nuevas.
- OpenBLAS utiliza un hilo de cálculo por defecto. No limita los hilos de las tareas
  de MD y respeta una configuración explícita del entorno.

### Validación

- Pruebas locales de pérdida de respuesta, caída tras el clic, recuperación tras
  reiniciar, errores de guardado local y continuidad de lotes, sin operar sobre Maximo.
- Suite conjunta: 274 pruebas correctas y 82 pruebas de Edge offline omitidas.
- Comprobación sintética con 5.000 OTs ficticias: refresco sin cambios de unos 13 ms
  y limpieza de filtros de unos 424 ms en el equipo de prueba. Los tiempos reales
  dependen del equipo y de los datos.
- La recuperación de almacén queda pendiente de validación controlada con operaciones
  reales. La build empaquetada deberá comprobarse antes de publicar esta release.

## 1.2.1 — Acciones de almacén en la versión instalada

### Resumen

- Corregida la aparición de las acciones de almacén en el exe al habilitarlas en Configuración.
- Abrir una OT en Edge ya no espera a la conciliación ni a otras tareas de fondo.

### Corrección

- La apertura interactiva de OTs utiliza su propia sesión y no entra en la cola
  de operaciones de fondo. El doble clic y «Abrir OT» pueden utilizarse mientras
  se actualiza el listado, se concilia o se completa información.
- Retiradas las restricciones del antiguo prototipo que ocultaban el menú y
  bloqueaban la revisión de lotes fuera del entorno de desarrollo de almacén.
  Las acciones se habilitan con «Mostrar acciones de almacén» y «Guardar cambios»;
  se mantienen la confirmación previa, las comprobaciones de estado y los
  permisos de la cuenta de Maximo.

## 1.2.0 — Operaciones de almacén y prioridades de tareas

### Resumen

- Acciones de almacén individuales y en lote, con progreso y resultado por OT.
- Selección de varias OTs mediante casillas, Ctrl o Mayús.
- Búsquedas de varios valores separados por comas.
- Prioridad para tus acciones: las tareas de fondo pausan y reanudan su cola.
- Actualizaciones sin duplicados y corrección del bucle de descargas.
- Novedades al actualizar y mejoras en el cierre de OT y en Configuración.

### Operaciones de almacén

- Nuevas acciones desde el menú contextual de MD, sobre una OT o una selección
  múltiple: confirmar recepción, dar salida del almacén y confirmar con envío a
  SAT interno o externo. Se muestran al activar «Mostrar acciones de almacén»
  en Configuración y requieren una cuenta con los permisos correspondientes.
- Los lotes se procesan en segundo plano con revisión y confirmación previa.
  El diálogo muestra el paso actual, el resultado de cada OT y un resumen final;
  permite detener el lote después de la OT en curso y abrir las fichas para
  revisión manual. Los resultados inciertos no repiten automáticamente el envío.
- El estado se comprueba directamente en Maximo y, tras verificar la operación,
  se refleja inmediatamente en el listado de MD. Las siguientes actualizaciones
  siguen tomando Maximo como referencia.
- Opción para pedir detalles por OT antes de enviar a SAT, desactivada por defecto.
  Nuevos registros y reportes por lote para diagnosticar incidencias.
- «Rechazar recepción» permanece deshabilitado hasta validar ese recorrido.

### Selección, búsqueda y configuración

- Casillas para seleccionar varias OTs y seleccionar todas las filas visibles,
  además de Ctrl y Mayús. La selección múltiple es independiente de las funciones
  de almacén.
- Búsquedas de varias OTs, números de serie o descripciones separados por comas.
  Ejemplo: `4428954, 4428920, 4428818`. Se mantienen las búsquedas parciales,
  las palabras separadas por espacios y los demás filtros.
- Opciones de configuración redistribuidas para aprovechar las dos columnas.

### Prioridad para las acciones del usuario

- Las acciones solicitadas desde MD tienen prioridad sobre las tareas automáticas.
  La conciliación y la lectura de información terminan la OT actual antes de
  pausar su cola y la reanudan después, conservando el progreso.
- Aviso visible cuando una acción debe esperar, con la tarea y la OT en curso
  cuando corresponde. Las confirmaciones y el guardado de datos no se interrumpen.
- Si ya hay una actualización del listado en curso o pendiente, una nueva petición
  informa de ello sin duplicarla ni cancelar la existente. Corregido el bucle de
  pausas y descargas entre actualizaciones de la misma prioridad.

### Novedades y correcciones

- Tras actualizar, el primer arranque muestra las novedades de la versión instalada
  una sola vez. Usa las notas de la release y dispone del changelog incluido como
  respaldo sin conexión.
- El cierre de OT reintenta la navegación cuando Maximo ignora un cambio de pestaña,
  antes de continuar con la operación.

## 1.1.0 — Inicio y cierre de OT desde Edge y anomalías configurables

- Corregida la carga inicial de los desplegables de anomalías en Maximo,
  que sustituye el constructor JavaScript Event. La combinación predeterminada
  aparece completa sin cambiar antes de clase; confirmar permanece deshabilitado
  hasta disponer de una selección válida.
- Corregido el bloqueo al intentar Guardar desde un menú deshabilitado tras
  seleccionar anomalías. Si Maximo ya las ha guardado, se confirma su persistencia
  recargando la ficha antes de continuar, sin esperar una respuesta de un botón
  inactivo. La comprobación también se aplica a «Cambiar anomalías».
- Nuevo botón «Cambiar anomalías» en las OT iniciadas (INPRG). Permite elegir,
  guardar y verificar otra combinación sin enrutar la OT ni modificar los
  predeterminados de MD. Comparte la activación con «Iniciar OT» y vuelve a la
  pestaña de origen. El cambio y la revisión del cierre no se ejecutan a la vez.
- «Elegir anomalías…» conserva y vuelve a mostrar los desplegables al alternar
  entre aplicar una combinación y solo iniciar. Una ruta incompleta sigue
  requiriendo completar sus opciones antes de iniciar con anomalías.
- El inicio de OT permite conservar las anomalías actuales o aplicar una
  combinación predeterminada mediante listas condicionales en Configuración.
  «Elegir anomalías…» en Edge permite cambiarla solo para esa ejecución.
  El catálogo conserva las relaciones entre clase, problema, causa y resolución;
  no se ofrecen las combinaciones descartadas en la validación.
- Las incidencias del flujo de anomalías se guardan en un registro local con
  la combinación solicitada, el paso fallido y las opciones consultadas en Maximo,
  incluyendo filtros y paginación. El archivo tiene rotación automática.
- La impresión conserva la preferencia de cerrar ventanas después de recargar
  la ficha al cerrar una OT, durante la misma sesión de Edge.
- El diálogo de cierre mantiene la distribución al cambiar entre las acciones
  o entre hora de inicio y finalización. Avisa de que cerrar, desechar y retener
  son acciones irreversibles; el diálogo de justificación de Desechar activo
  se reconoce como un paso manual del proceso.

- «Imprimir parte» localiza el OT y su estado por las etiquetas de Maximo además
  de los IDs habituales, para que el botón siga disponible al cambiar a otras
  pestañas internas de la ficha.
- El diálogo «Cerrar OT» permite elegir Cerrar, Desechar o Retener equipo.
  Desechar y Retener exigen una confirmación adicional con casilla antes de
  ejecutar la acción; el flujo nativo se limita a la opción elegida.
- La configuración reúne las opciones de acciones de OT y partes de reparación
  de la extensión bajo una única sección «Extensión de Edge».
- Las acciones «Iniciar OT» y «Cerrar OT» vuelven a la pestaña de Maximo desde
  la que se lanzaron. «Iniciar OT» solo aparece en estado APPR y «Cerrar OT»
  solo aparece cuando la orden ya está iniciada (INPRG).
- El botón «Imprimir parte» se vuelve a insertar si Maximo reconstruye la página
  al cambiar de pestaña, evitando tener que recargar la ficha para recuperarlo.
- El cierre introduce inicio y fin con el formato de Maximo (`dd/MM/yy HH:mm:ss`)
  y Tab. Los valores se mantienen en la ficha hasta confirmar el enrutado; después
  se recarga la OT y se verifican en ISSUE antes de dar el proceso por terminado.

- Las acciones «Iniciar OT» y «Cerrar OT» se habilitan por separado en
  Configuración y se ejecutan únicamente desde las ventanas de Edge abiertas
  por MD. Retirado el inicio de OT del menú contextual y su ejecución en segundo
  plano desde la aplicación. «Abrir OT» sigue abriendo únicamente la ficha.
- Nuevo cierre de reparación desde Edge: revisa las horas en Consumos Actuales,
  permite indicar el inicio o el final y calcula la otra hora según la duración,
  sin superar la hora actual. Solo acepta duraciones en tramos de 0,25 h
  (15 minutos). La revisión exige confirmación explícita;
  cancelar no modifica los datos. Al confirmar, enruta hasta ISSUE, pendiente de
  salida del almacén, y verifica duración y fechas tras recargar, sin continuar a CLOSE.
  Ante un resultado incierto no repite la aceptación final del cierre.
- «Ahora» completa la finalización con la hora actual. Las fechas se introducen
  con precisión de minuto; el selector avanza en intervalos de cinco minutos.
  El diálogo se ha rediseñado para mantener los controles legibles y accesibles
  en ventanas pequeñas.
- «Iniciar OT» y «Cerrar OT» comparten posición en la parte inferior derecha; solo
  se muestra la acción correspondiente al estado, sin reservar espacio para la otra.

- Corregido el falso aviso de diálogo abierto al iniciar una OT: Maximo conserva
  el contenedor `warndiv` aunque su panel esté oculto. El botón y la automatización
  comprueban ahora la visibilidad del panel real, sin bloquear por contenedores
  inactivos ni dejar pasar los avisos que sí están abiertos.

- Corregida la recuperación cuando Maximo reconstruye un diálogo antes de pulsar
  «Continuar» u otro botón del inicio de OT. Se vuelve a localizar el control y se
  comprueba el resultado antes de repetir una acción.
- «Enrutar flujo de trabajo» se reintenta hasta tres veces si no abre ningún
  diálogo y la OT sigue en APPR. No se vuelve a pulsar mientras Maximo está
  cargando ni después de iniciar la orden. Los errores técnicos completos se
  conservan en el log; el botón muestra un mensaje breve.

- El inicio de OT usa «Seleccionar códigos de anomalía» en Informes de anomalías:
  aplica la ruta elegida, esperando el avance de cada nivel y el cierre automático
  del diálogo. Soluciones se utiliza para verificar los valores, sin modificar
  sus tres campos mediante lupas. Los cambios se guardan tras configurar la
  clase y después de completar el selector; los errores se comunican sin timeout.
- La opción «Iniciar orden» también se identifica cuando Maximo relaciona el
  botón de selección con su texto mediante ARIA o la fila contenedora.

- Nuevo inicio opcional de OT en Edge. La combinación predeterminada inicial
  es RFN-70 / OTROS-01/02/03, modificable desde Configuración. El modo configurado
  utiliza los selectores nativos para aplicar la ruta elegida antes de iniciar
  la orden. El progreso se muestra en el botón del navegador.
- El inicio comprueba el estado real: solo actúa sobre APPR, no vuelve a enrutar
  una OT ya iniciada y se detiene ante avisos desconocidos. Verifica el resultado
  guardado antes de actualizar el seguimiento local.

- La preparación de cada parte recupera el foco de la ficha de OT antes de
  introducir su número. Esto permite validar el campo también en la segunda
  copia de Boixeres cuando las ventanas del primer parte permanecen abiertas.
  Se respeta la opción de cerrar o conservar las ventanas.

## 1.0.2 — Partes de reparación y revisión de OT

- Para las OT de TMB BOIXERES, la impresión HTML genera dos copias consecutivas:
  el parte habitual y una segunda copia sin nombre del técnico ni tiempo de reparación.
  Se utiliza el parámetro original de Maximo, seleccionado mediante su lupa.
- Nueva opción para cerrar las ventanas del visor y del parte después de la
  impresión directa, también entre las dos copias de Boixeres. Con el diálogo
  de impresión, las ventanas permanecen abiertas para revisar los ajustes o cancelar.
- La revisión prioritaria de OT muestra en la barra de estado cuántas órdenes
  se han revisado, el total pendiente y la OT en curso.

- Retirados la interfaz, el instalador y las pruebas exclusivos de Tkinter.
- Eliminadas las opciones de seguimiento manual y sus recursos obsoletos.
- El entorno de desarrollo utiliza exclusivamente la `.venv` de este proyecto.
- La build incluye solo los recursos ejecutables de la extensión, sin sus pruebas ni documentación.
- Corregido el aislamiento de la prueba de migración para que su resultado
  no dependa de otras pruebas ejecutadas antes.

## 1.0.1 — Ajustes para el primer lanzamiento

- El registro de la aplicación se guarda en `maximo_desktop.log`.
- El indicador de desarrollo solo se muestra en la ejecución aislada; las instalaciones estándar no lo muestran.

## 0.9.8.4 — Mantenimiento de registros históricos

- Configuración permite activar o desactivar la conciliación automática de OT
  no activas y elegir el tamaño de lote, entre 1 y 100 OT.
- Añadida una revisión prioritaria manual: procesa todas las OT pendientes en
  una sola sesión y reserva las actualizaciones normales mientras termina.
- Añadida una purga confirmada de todos los registros no activos, limitada a la
  base de datos local.
- El nombre visible de la aplicación y sus metadatos de Windows pasan a ser
  «Maximo Desktop».

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
