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
Activa «Mostrar acciones de almacén», marca las casillas o selecciona filas con
Ctrl/Mayús y abre el
menú contextual. La revisión permite elegir un recorrido correcto o incidencias.

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
  ordenar mantiene las OTs elegidas. El selector se oculta al desactivar almacén.
  La tabla usa un dibujo consistente de las marcas y el resaltado para evitar los
  defectos del estilo nativo de Windows 11. Al desactivar almacén restaura el dibujo anterior.
- Se congelan los identificadores y datos al abrir la revisión. Ordenar o filtrar
  después no cambia el lote. Esta fase no comprueba estados en el servidor.
- Una sola simulación activa, secuencial y en un hilo aparte; UI disponible.
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

## Descartar o continuar

Para seguir trabajando en lo actual, usa `maximo-client-ui`, que permanece en `dev`.
El trabajo experimental se conserva únicamente en `feature/almacen` y su carpeta.
Si se abandona, basta con retirar ese worktree y rama tras revisar si se desea
conservar algo. Sus datos de prueba están en una carpeta separada; no se necesitan
migraciones inversas ni cambios en la instalación distribuida.
