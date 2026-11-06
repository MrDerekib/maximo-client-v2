# Prototipo aislado de almacén

Estado: interfaz y procesamiento **simulado**, sin transporte a Maximo.

- Rama temporal `feature/almacen`, creada desde `dev` en `a165605`.
- Carpeta de trabajo independiente `maximo-client-almacen`; la carpeta habitual
  `maximo-client-ui` permanece en `dev`.
- No se cambia la versión, el proceso de impresión ni los flujos de técnico.
- No se fusionará con `dev` ni `main` hasta validar con almacén.

## Probar

Desde esta carpeta, con su propio entorno `.venv` y `requirements.txt`:

```powershell
.\run_warehouse_dev.ps1
```

La demostración usa seis OTs ficticias y no lee credenciales ni base de datos.
Las casillas y Ctrl/Mayús están disponibles siempre. Activa «Mostrar acciones de
almacén» para añadirlas al menú contextual. «Dar entrada» contiene Confirmar
recepción, Rechazar recepción, Confirmar y enviar a SAT Interno y Confirmar y enviar
a SAT Externo. La salida figura como una acción aparte. Todas siguen siendo simuladas.
La revisión permite elegir un recorrido correcto o incidencias.

```powershell
.\run_warehouse_dev.ps1 -FullApp
```

Abre la app completa con datos en `%LOCALAPPDATA%\MaximoDesktop-almacen`, separados
de producción y del desarrollo habitual. En Configuración, activa las funciones
de almacén y guarda. Las acciones de lote siguen siendo exclusivamente simuladas.
Los enlaces de OT en esta app completa sí abren la ficha real para revisión manual,
con las credenciales configuradas allí; no ejecutan la acción de almacén.
No se registra el protocolo de enlaces ni se comprueban releases automáticamente
en este modo aislado. Usa este lanzador para mantener ese aislamiento.

## Comportamiento

- Individual y múltiple comparten revisión y reporte; botón secundario sobre una
  fila ya seleccionada conserva el lote. Se excluyen filas ocultas y duplicados.
- Las casillas reflejan la misma selección que Ctrl/Mayús. La casilla de cabecera
  selecciona solo las filas visibles y muestra un estado parcial si procede.
  Se muestra un contador y «Limpiar selección». Cambiar filtros limpia la selección;
  ordenar mantiene las OTs elegidas. El selector es general (`workorder_selection.py`)
  y no depende de activar almacén; ese interruptor solo controla sus acciones.
  La tabla usa un dibujo consistente de las marcas y el resaltado para evitar los
  defectos del estilo nativo de Windows 11.
- Configuración reparte acceso, actualizaciones, apariencia, mantenimiento,
  información ampliada y rutas en «Aplicación y datos»; extensión, almacén y
  prioridades quedan en «Órdenes de trabajo». Las columnas se apilan con menos ancho
  y vuelven a separarse al ampliarlo, sin conservar un ancho mínimo anterior.
- Se congelan los identificadores y datos al abrir la revisión. Ordenar o filtrar
  después no cambia el lote. Esta fase no comprueba estados en el servidor.
- Para validar el estado del listado, `PDTE CONFIRMAR` equivale a `WAPPR` y
  `DAR SALIDA` a `ISSUE`. Se conserva el texto original en la tabla y el reporte.
  La demostración usa las etiquetas de MD; estas equivalencias no autorizan acciones
  sobre estados distintos ni sustituyen la futura comprobación en Maximo.
- Una sola simulación activa, secuencial y en un hilo aparte; UI disponible.
- Las cuatro opciones de entrada requieren `WAPPR` / `PDTE CONFIRMAR`, conservan
  su acción específica en la revisión y el reporte y no presuponen estados finales
  ni diálogos posteriores todavía no validados con la cuenta de almacén.
- El tick verde solo significa «Simulación correcta», nunca operación real.
- Los fallos y resultados inciertos se conservan en el reporte para revisión manual
  y el lote continúa con la siguiente OT, sin repetir la confirmación de la OT incierta.
  Detener termina primero la OT en curso y deja las siguientes sin procesar.
- Cerrar/Escape durante el trabajo solicita detener y conserva el reporte abierto.
- Los reportes JSON, marcados `simulation: true`, quedan en
  `logs/almacen-simulaciones`. No se modifica el seguimiento local de las OTs.

## Pendiente de la cuenta de almacén

Capturar el DOM y recorrido completo de recepción y salida; confirmar estado
inicial/final y diálogos adicionales; validar permisos, errores y persistencia.
Después se podrá implementar el transporte real reutilizando sesión y navegación.
Las reglas reales de verificación deben aprobarse antes de habilitar operaciones.
Se comprobarán los códigos leídos en Edge antes y después de cada operación;
el estado del listado de MD solo sirve para preselección, no para acreditar el éxito.

## Descartar o continuar

Para seguir trabajando en lo actual, usa `maximo-client-ui`, que permanece en `dev`.
El trabajo experimental se conserva únicamente en `feature/almacen` y su carpeta.
Si se abandona, basta con retirar ese worktree y rama tras revisar si se desea
conservar algo. Sus datos de prueba están en una carpeta separada; no se necesitan
migraciones inversas ni cambios en la instalación distribuida.
