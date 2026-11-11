# SAT externo desde el rol de técnico — fase 1

Rama: `tecnico/sat-externo`. Flujo independiente de la recepción de almacén con
«Confirmar y enviar a SAT Externo». La extensión de Edge se reserva para fase 2.

## Reconocimiento del 11/11/2026

OT de referencia: 4433097, APPR. Inspección mediante la sesión Selenium existente,
sin CUA, sin iniciar la OT ni confirmar el envío.

- Consumos Actuales: «Horas totales de reparación» es editable en APPR.
- Registro → Fila Nueva: tipo predeterminado CLIENTNOTE; «Resumen» editable.
  El usuario confirma el formato `inc: número`. No se ha confirmado contenido
  adicional para Detalles. La fila vacía de inspección se descartó con No al
  aviso de guardar; después se reabrió la OT y se comprobó que había cero filas.
- El usuario abrió Entrada manual. Se identificó el diálogo `inputwf-dialog_inner`
  y cuatro opciones: Iniciar orden, Cancelar orden, Enviar a SAT Interno y
  **Enviar a SAT Externo**. Esta última estaba habilitada, sin seleccionar.
- Los controles se identificarán por el diálogo y la etiqueta exacta; los IDs
  `mx...` observados son variables y no deben fijarse en el flujo.
- No se pulsó Aceptar. El diálogo posterior de motivo, los requisitos adicionales
  y el estado/historial final del envío técnico están pendientes de inspección.
  No se asumen equivalentes a los de recepción SAT de almacén.

## Preparación de datos

`technician_sat.reviewed_sat_plans` valida todas las OTs del lote antes de cualquier
operación: ruta de anomalías completa, duración positiva en múltiplos de 0,25 h,
número de incidencia y motivo no vacío. Cada OT requiere sus propios valores.
La selección se copia para que cambios posteriores en los diccionarios del
formulario no alteren un lote ya revisado. No se usan datos de ejemplo en Maximo.

Cinco pruebas locales cubren validación, datos faltantes y aislamiento de entradas.
Todavía no hay una acción SAT técnica habilitada en el menú de MD.

## Recorrido a completar

1. Revisar selección y datos por OT en MD con confirmación explícita.
2. Abrir en sesión técnica, contrastar OT, identidad y estado permitido.
3. Aplicar anomalías y soluciones usando el catálogo y la lógica existente.
4. Introducir duración y validar; crear el registro de incidencia sin duplicarlo.
5. Comprobar el guardado antes de enrutar.
6. Localizar exclusivamente Enviar a SAT Externo y completar su motivo.
7. Verificar el estado y evidencia específica de ese envío desde una nueva lectura.
8. Integrar progreso, reporte y recuperación de incertidumbres sin reenviar
   automáticamente una confirmación que pueda haberse ejecutado.

Pendientes para el caso real: duración, número de incidencia real y motivo del
usuario, inspección del diálogo posterior y autorización concreta para confirmar.
