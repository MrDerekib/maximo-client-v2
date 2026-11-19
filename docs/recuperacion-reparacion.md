# Recuperación de cierre y desecho desde MD

El resultado de una confirmación incierta nunca se interpreta automáticamente como
una acción fallida. Un timeout puede ocurrir mientras Maximo termina de procesar.
Esta lógica se aplica a **Finalizar reparación** y **Declarar irreparable** de MD;
las acciones de la extensión conservan su recorrido actual.

## Verificación y recuperación

- Antes de aceptar: espera a que la opción correcta esté seleccionada, el servidor
  esté inactivo y el botón Aceptar esté visible y habilitado. Resuelve de nuevo los
  controles después de comprobar la identidad.
- Antes de cada posible efecto se persiste la fase. Una confirmación final nunca
  se repite automáticamente, aunque Selenium pierda el botón o la respuesta.
- Si el proceso falla después de un posible enrutado final, se cierra esa sesión
  y se realizan hasta dos consultas independientes de solo lectura, reutilizando
  el sistema de recuperación persistente existente.
- Para cerrar: se espera ISSUE. Para desechar: CLOSE. Además deben coincidir la
  identidad, el incremento del historial de la acción, duración, fechas y Registro.
  Un estado final por sí solo no basta.
- Si se verifican esas evidencias se completa el proceso habitual, incluido el
  parte solicitado. Si falta alguna, la operación permanece pendiente.

## Desde la ventana de progreso

**Reverificar resultado** consulta las mismas evidencias sin Enrutar ni Aceptar.
Permite comprobar de nuevo más tarde, sin salir de la ventana. No imprime
automáticamente al recuperar: habilita la preparación manual del parte.

**Revisar y reintentar…** solo se habilita cuando no hubo un posible enrutado
final ni confirmación. Recupera el formulario conservando su escritura, desmarca
la confirmación y exige revisar y confirmar otra vez. Vuelve a comprobar estado e
identidad antes de escribir. Conserva el identificador de operación y aumenta su
contador de reintentos; el tipo de acción permanece bloqueado. Si la OT ya se
inició durante el primer intento, no se inicia de nuevo. Las entradas existentes
se contrastan para evitar duplicados o sobrescribir detalles diferentes.

No basta con observar INPRG después de un intento de Aceptar para habilitar otro
cierre: puede existir una respuesta tardía. Los registros antiguos sin evidencias
suficientes también permanecen bloqueados para repetición y admiten reverificación.

Un fallo al guardar el resultado local **no vuelve a ejecutar Maximo**. La ventana
indica que la operación está verificada y que el guardado está pendiente;
Reverificar reintenta solo ese guardado.

Los botones permanecen bloqueados mientras trabaja otro intento o recheck. La
consulta de recuperación puede detenerse incluso mientras espera turno.

## Diagnóstico y pruebas

Se conserva `operation_id`, fase, petición revisada, identidad y el historial
previo en el registro pendiente. Los eventos `repair_auto_recheck`,
`repair_preparation_resumed`, `recheck_observed`, `recheck_history` y
`recheck_verified` permiten distinguir envío, consulta y reintento. No se guardan
credenciales ni objetos de sesión.

`python -m unittest tests.test_repair_recovery tests.test_technician_repair tests.test_warehouse_recovery`

Inyecta respuesta tardía, historial ausente, fechas diferentes, identidad cambiada,
reintento obsoleto y bloqueo de guardado local. No ejecuta ninguna operación real.
