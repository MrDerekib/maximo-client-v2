# Reintento de preparación técnica SAT

- El informe y la revisión de pendientes ofrecen «Reintentar preparación…» exclusivamente para el técnico SAT externo, fase `preparing`, sin intentos de Enrutar, Aceptar ni OK SAT.
- El botón abre una nueva revisión por OT. No ejecuta operaciones al abrirse. Consulta APPR y la identidad actual; el usuario revisa anomalías, horas, incidencia y motivo, y confirma expresamente antes del nuevo intento.
- La petición revisada se conserva en el registro local pendiente para sobrevivir a reinicios. No contiene credenciales ni objetos de sesión. La consulta actual no sobrescribe los campos revisados recuperados; sus valores actuales se muestran en las ayudas de los campos.
- Los registros anteriores sin petición guardada se admiten: se propone avería y duración actuales; solo se recupera una referencia `inc:` cuando la página completa del Registro contiene una única referencia CLIENTNOTE. Lo que no pueda reconstruirse se deja para revisión del usuario.
- Backend comprueba de nuevo identificador de operación, fase, flags, estado APPR e identidad antes de reutilizar el mismo registro. Un cambio de fase bloquea el reintento. Enrutar y confirmaciones siguen marcándose antes de pulsarse y no se repiten automáticamente.
- Preparación incompleta se informa como fallida y reintentable, sin esperar ISSUE ni marcar los pasos de envío como completados. Los resultados inciertos tras Enrutar mantienen únicamente la reverificación.
- Al finalizar con éxito, el flujo habitual verifica ISSUE e incremento de historial, actualiza MD y el informe original, y resuelve el pendiente.

Validación: pruebas locales de persistencia/reapertura, cancelación, petición antigua, estado cambiado, rechazo después de Enrutar, reutilización del registro y un único envío, consulta de pendientes sin acciones. No se ha ejecutado el reintento real sobre SA202: queda para la revisión y confirmación del usuario.
