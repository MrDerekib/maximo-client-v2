# Prioridades de tareas de Maximo Desktop

Implementado en la rama de almacén el 9 de noviembre de 2026.

## Reglas

1. Una acción de usuario activa no cede ante una tarea automática programada.
2. Las tareas automáticas pendientes esperan a los trabajos del usuario.
3. Un lote en curso termina la OT actual, guarda el resultado y cede antes de la
   siguiente OT. Al reanudarse mantiene las candidatas y el progreso, sin repetir
   las ya procesadas.

Las tareas de igual prioridad conservan orden de solicitud y no se interrumpen
entre sí. Solo se cede ante una prioridad superior.

Solo puede existir una actualización del listado activa o pendiente. Una solicitud
manual adicional informa de ello sin encolar otro trabajo; una automática adicional
se omite. La actualización existente continúa con su prioridad y resultado habituales.

## Clasificación

- Alta: operaciones de almacén y preparación de partes solicitadas desde MD.
- Independiente: abrir una OT por doble clic, menú contextual, enlace o reporte
  crea su propia sesión interactiva; no espera ni pausa la conciliación, la
  actualización ni la lectura ampliada. Su hilo sigue controlado por el cierre de MD.
- Media: actualización manual del listado, conciliación manual y lectura ampliada
  solicitada por el usuario.
- Automática: actualización programada y su cadena de conciliación e información
  ampliada. Se evitan duplicados automáticos de un trabajo ya pendiente.
- Independientes: tareas locales, comprobación de credenciales y trabajos de GitHub
  conservan el pool existente. Instalar una actualización mantiene el cierre ordenado.

Las automatizaciones de la extensión continúan en sus propias sesiones: no se
incorporan sus funciones de inicio/cierre/cambio de anomalías a este coordinador.

## Cesión segura

Conciliación y enriquecimiento ceden después de completar la OT en curso; al pausar
cierran exclusivamente su navegador y perfil, y abren una sesión nueva al reanudarse.
No se pausa una transacción de SQLite, ni una confirmación de almacén entre el clic
y su verificación y persistencia local.

Una descarga global es lectura interrumpible en sus esperas de Selenium. Si hay
una solicitud de mayor prioridad, se abandona su sesión propia y se descarga otra
exportación después. Si se cede tras descargar o procesar un XLS, se descarta ese
archivo y se obtiene uno nuevo antes de importar. Así una actualización de MD
pausada no importa una exportación anterior a la operación prioritaria.

Las esperas de navegación/lectura conservan los timeouts existentes de WebDriver;
no se terminan hilos por la fuerza ni se mata un navegador compartido.

## Avisos

Al esperar, almacén muestra el mensaje en su diálogo de proceso; otras acciones
muestran el cartel de actividad con el esquema de colores actual. Indica tarea y
OT que están terminando y qué acción comenzará después. El aviso desaparece al
comenzar; no exige otra confirmación. Pausa/reanudación también se reflejan en la
barra inferior como información complementaria.

## Hilos y cierre

`task_priorities.py` coordina la ejecución. Los antiguos candados de trabajos de
la ventana son contadores de actividad; la exclusión pertenece al coordinador.
Los trabajos que pueden esperar tienen QThreads propios referenciados por MD para
no agotar el pool antes de que arranque un trabajo prioritario. El resto conserva
QThreadPool. La ventana espera tareas y QThreads activos antes de finalizar.

Cerrar cancela pendientes y trabajos pausados sin abrir otra sesión para ellos.
Una operación activa termina su unidad protegida; no se destruye un QThread activo.
Los perfiles ya retirados no se vuelven a cerrar ni borrar tras cancelar una pausa.

## Validación

Pruebas sin Maximo real: orden y exclusión, pausa/reanudación, contadores, avisos
visibles Qt, prioridad con pool independiente lleno, cierre con confirmación activa,
conciliación con sesiones ficticias y candidatas conservadas, cierre durante pausa
y descarte de XLS anterior a una cesión. No se han ejecutado operaciones de almacén
ni de técnico para validar estos cambios.

## Apertura interactiva de OT

La apertura interactiva por doble clic, menú contextual, enlace o reporte crea
su propia sesión de Edge y no espera ni pausa las tareas de fondo. Su hilo y
su sesión siguen controlados por el cierre ordenado de MD. Preparar un parte
para imprimir o guardar PDF sigue pasando por el coordinador.
