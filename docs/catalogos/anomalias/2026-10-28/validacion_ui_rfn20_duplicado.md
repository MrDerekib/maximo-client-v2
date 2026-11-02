# Validación en Maximo: causa duplicada C-RFN-062

Fecha: 2026-10-28

OT de prueba: 3088915

Alcance: inspección de la jerarquía en la pestaña «Informes de anomalías». No se eligió ninguna resolución ni se ejecutó ninguna acción de flujo de trabajo.

## Resultado observado

Bajo clase `RFN-20` y problema `P-RFN-139`, Maximo presentó dos filas UI distintas para `C-RFN-062`:

| Ocurrencia | ID de la fila | `targetid` | `mxevent` | Texto de fila |
|---|---|---|---|---|
| R0 | `mx277_tdrow_[C:0]_ttxt-lb[R:0]` | `mx277_tdrow_[C:0]_ttxt-lb[R:0]` | `click` | `C-RFN-062 · CAUSE · VOLUMEN BAJO` |
| R1 | `mx277_tdrow_[C:0]_ttxt-lb[R:1]` | `mx277_tdrow_[C:0]_ttxt-lb[R:1]` | `click` | `C-RFN-062 · CAUSE · VOLUMEN BAJO` |

Al abrir cada ocurrencia, el selector mostró una única resolución:

| Ocurrencia de causa | Resolución ofrecida | Texto de fila |
|---|---|---|
| R0 | `S-RFN-262` | `S-RFN-262 · REMEDY · AJUSTE POTENCIOMETRO VOZ INTERFONO` |
| R1 | `S-RFN-262` | `S-RFN-262 · REMEDY · AJUSTE POTENCIOMETRO VOZ INTERFONO` |

No se seleccionó `S-RFN-262` ni se pulsó ningún botón del pie del selector.

## Comprobación manual de Joan (29/10/2026)

Joan revisó manualmente la ruta `RFN-20 / P-RFN-139`. Las capturas aportadas muestran dos filas `C-RFN-062 · CAUSE · VOLUMEN BAJO` y una cadena completa que termina en `S-RFN-262`. Al preguntarle por `S-RFN-263`, respondió literalmente: «esta entrada no la veo».

El alcance comunicado no especifica que Joan abriera por separado cada una de las dos ocurrencias; por tanto, esta comprobación manual confirma lo visible en las capturas y no se presenta como dos pruebas independientes de R0 y R1.

## Conclusión

La prueba automatizada anterior registró `S-RFN-262` tras abrir R0 y R1. La comprobación manual posterior también muestra dos causas `C-RFN-062` y una ruta que termina en `S-RFN-262`; Joan no encontró `S-RFN-263` en esa ruta UI. El snapshot original conserva la relación `C-RFN-062 id=165598 → S-RFN-263 id=167710`, además de `C-RFN-062 id=165600 → S-RFN-262 id=167400`.

El resultado significa que `S-RFN-263` no se ha encontrado en la ruta UI probada, tanto por automatización como en la revisión manual comunicada. No determina la causa de la discrepancia ni permite atribuirla al servidor. Se conserva intacto el grafo crudo; en la futura configuración se debe excluir o marcar como no confirmada la combinación `RFN-20 / P-RFN-139 / C-RFN-062 / S-RFN-263` para esta ruta UI. Esto no bloquea la siguiente fase de configuración para las opciones confirmadas.
## Limpieza y estado final

Al iniciar esta pasada ya estaba presente una fila temporal `PROBLEM / P-RFN-139` de una selección previa. Se retiró usando «Marcar fila para suprimir» y «Guardar» de Acciones comunes. Tras cada rama, también se suprimieron primero la fila `CAUSE` y después `PROBLEM`; Maximo confirmó el guardado y la tabla quedó vacía. Escape envió `dialogcancel`, pero no cerró el selector dentro del plazo; se cerró el WebDriver y se limpió desde una sesión nueva antes de continuar.

Una sesión nueva confirmó estado `APPR`, clase `RFN-20` y cero filas de anomalía. No se inició, enroutó ni cerró la OT.

## Implicación para la configuración futura

El modelo configurable debe conservar IDs de ocurrencia y sus relaciones con el padre, además del código visible. No se debe colapsar un nodo solo porque comparte código y tipo con otro. Para esta ruta UI, excluir o marcar como no confirmada la combinación `RFN-20 / P-RFN-139 / C-RFN-062 / S-RFN-263`. Se mantiene la rama en el grafo crudo, sin atribuir una causa a la discrepancia. Esto no bloquea la siguiente fase de configuración para las opciones confirmadas.

La evidencia de ejecución sanitizada está en [evidencia_ui_rfn20_duplicado.json](evidencia_ui_rfn20_duplicado.json). Contiene solo IDs y textos de las opciones observadas, las ramas del snapshot estático contrastadas y el estado final; no incluye URL de sesión, cookies ni credenciales.
