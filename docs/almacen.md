# Maximo Desktop — desarrollo de almacén

Las funciones de almacén están integradas en `main` y `dev` desde la versión
1.2.0. La carpeta `maximo-client-almacen` y su lanzador conservan un entorno
de pruebas con datos separados del desarrollo habitual en `maximo-client-ui`.

## Ejecutar

```powershell
.\run_warehouse_dev.ps1
```

Abre directamente la app completa, con su propio entorno `.venv` y datos en
`%LOCALAPPDATA%\MaximoDesktop-almacen`. El antiguo argumento `-FullApp` se acepta
por compatibilidad, pero ya no es necesario. Se retiraron la demo ficticia, el
selector de modo, los escenarios y el motor de simulación.

En Configuración, activa «Mostrar acciones de almacén» y guarda. Reinicia la app
para cargar los cambios de código. Marca una o varias OTs con las casillas o
Ctrl/Mayús y usa el menú contextual. El diálogo revisa la acción y las OTs antes
de ejecutarlas; la confirmación tiene «No» como opción inicial.

## Acciones

- Confirmar recepción: ejecución real validada, `WAPPR` → `APPR`.
- Dar salida: ejecución real validada, `ISSUE` → `CLOSE`.
- Confirmar y enviar a SAT externo: ejecución real validada, `WAPPR` → `ISSUE`,
  con nueva entrada de la acción concreta en el historial.
- Confirmar y enviar a SAT interno: habilitada con el mismo recorrido por indicación
  expresa del usuario y la referencia histórica consultada. No se ha ejecutado una
  nueva derivación interna durante esta validación.
- Rechazar recepción: visible pero deshabilitada hasta validar su recorrido;
  tanto el diálogo como el transporte rechazan esa acción.

La selección múltiple es general y no depende de activar almacén. El lote congela
los identificadores, excluye filas ocultas y duplicadas, conserva las OTs al ordenar
y limpia la selección al cambiar filtros.

## Proceso y reporte

### Buscar varios elementos

El buscador de OT, número de serie y descripción acepta alternativas separadas
por comas, por ejemplo `4428954, 4428920, 4428818`. Conserva la búsqueda parcial
actual: dentro de cada alternativa, los espacios exigen que aparezcan todas las
partes (`2789 298, ABC123`). Los demás filtros se aplican a todas las alternativas.
Se ignoran entradas vacías entre valores y los resultados no se duplican. Una
entrada formada solo por comas no devuelve todas las OTs.

La cola corre en un hilo con Edge headless. Muestra cada paso, resultado por OT y
resumen. El tick verde requiere verificar el resultado guardado. Las OTs se pueden
abrir desde el reporte para revisión manual. Detener termina la OT actual y evita
comenzar las siguientes; cerrar durante el trabajo solicita esa detención.

Se comprueban identidad, estado real de Edge y opción exacta antes de aceptar.
El estado del listado local sirve para preselección, nunca para acreditar éxito.
Se reutiliza sesión en operaciones verificadas y se descarta una sesión incierta.
Un envío incierto no se confirma otra vez; se registra y continúa con la siguiente
OT. Los logs y reportes están en `logs/almacen-operaciones`, con marcador de envío
forzado a disco antes de aceptar. Se coordina con el bloqueo de tareas Maximo de MD.

Cada resultado verificado actualiza inmediatamente `Seguimiento` y la fecha de
comprobación de esa OT en la base local: recepción → `EN TALLER`, salida → `CLOSE`,
SAT interno → `SAT INT` y externo → `SAT EXT`. La señal del hilo actualiza la fila
afectada y comprueba los filtros activos; no reconstruye el resto de la tabla salvo
que deba incorporar una OT que ahora cumpla los filtros y no estuviera presente.
El reporte conserva el «Estado inicial» y muestra el resultado final por separado.

No se modifica la presencia en el listado de Maximo, la fecha de última aparición
ni otras partes de la ficha. No se actualizan fallos o resultados inciertos. Un
fallo de escritura local se informa sin convertir una operación remota verificada
en una operación fallida ni reenviarla. No hay bloqueo ni prioridad especial del
estado local: el próximo update sigue sobrescribiéndolo con lo que devuelva Maximo.

## Detalles SAT

«Pedir detalles antes de enviar a SAT» se guarda como
`warehouse_ask_sat_details`, desactivada por defecto. Activada, muestra una entrada
opcional por OT en la revisión del lote; desactivada, los detalles quedan vacíos.
La preferencia no habilita acciones pendientes de validar.

La prueba de SAT externo se completó con detalles vacíos tras la nueva autorización
del usuario. La sesión anterior había caducado: una consulta nueva mostró `WAPPR`,
la asignación de recepción y ausencia de derivación en el historial. Solo después
de esa comprobación se retomó el recorrido autorizado. Se verificaron `ISSUE`, la
misma identidad y una entrada SAT externo nueva desde una sesión independiente.

Ambos SAT comparten el tratamiento del editor de detalles y OK/Cancel, con el
título exacto correspondiente a la variante elegida. El título o los controles
inesperados detienen la confirmación. Para acreditar el resultado, MD exige tanto
`ISSUE` persistido como un incremento de las entradas de la acción concreta en el
historial respecto a la consulta anterior al envío. No basta con `ISSUE`, común
a ambas variantes y a otras OTs pendientes de salida.

La referencia histórica de SAT interno tiene `ISSUE` en Edge y `SAT INT` en MD.
Se habilitó el recorrido compartido bajo la equivalencia indicada expresamente
por el usuario; su diálogo interno no se ha probado con una nueva operación real.
Rechazo permanece independiente y sin habilitar.

## Evidencias

### Diagnosticar incidencias de almacén

En `logs/almacen-operaciones` cada lote tiene `<id>-result.json` y
`<id>-events.jsonl`. Para reportar una incidencia, indicar la OT y aportar ambos
archivos de ese lote; `maximo_desktop.log` permite correlacionar el proceso general.
Las rutas concretas del reporte y diagnóstico aparecen en el tooltip del resumen.

El diario incluye versión de MD/Python/sistema, identificador de lote, secuencia,
fecha UTC, acción y posición de cada OT, tiempos por paso, estado local e inicial
real, estado final verificado, opción seleccionada, intentos únicos de confirmación,
comparación del historial SAT y persistencia local. En fallos añade tipo, traceback,
códigos BMX, contexto acotado de los diálogos y opciones disponibles, y versiones
de navegador/driver si la sesión todavía permite consultarlas. No se guardan HTML,
capturas de pantalla ni contenido de los detalles SAT. Se filtran credenciales,
cookies y tokens de URLs tanto en el diario como en los errores de almacén.

El diario se fuerza a disco antes de enviar confirmaciones. Un fallo de escritura
no provoca reintentos; las sesiones se cierran incluso si falla el propio registro
de la incidencia. Si el navegador ya no responde, se registra que el contexto no
pudo obtenerse, conservando la excepción y el paso de fallo.

- [Reconocimiento inicial](almacen-reconocimiento.md).
- [Validación de salida autorizada](almacen-validacion-salida.md).

Las operaciones reales iniciales se auditaron con scripts aislados. También se
probó el diálogo Qt → hilo → Edge headless con una OT ya recibida: su estado real
`APPR` impidió una segunda recepción antes de enrutar. Falta validar desde MD una
operación completa y un lote pequeño con OTs autorizadas nuevas. Los tests locales
sustituyen el transporte por mocks y no operan sobre equipos.

## Prioridades

Los trabajos de MD usan el [coordinador de prioridades](prioridades.md): aviso visible
de espera, cesión al terminar la OT actual y reanudación posterior. Las acciones
de la extensión permanecen independientes.
