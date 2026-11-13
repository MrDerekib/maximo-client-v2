# Build de prueba de Maximo Desktop 1.3.0

Desde PowerShell, en el proyecto de la UI actual:

```powershell
Set-Location 'C:\Users\jcamp\OneDrive - Indra\Documentos\python\opencode\maximo-client-ui'
.\build_app.ps1
```

Usa exclusivamente `.venv\Scripts\python.exe` de este proyecto. No se necesita
el entorno ni archivos de la versión antigua. El script lee `version.py`.

Si ya existe una compilación 1.3.0 y se quiere reemplazar expresamente:

```powershell
.\build_app.ps1 -Force
```

Paquete esperado:
`release\MaximoDesktop-1.3.0\MaximoDesktop-v1.3.0-windows.zip`.
El ZIP incluye toda la distribución; no distribuir solamente el exe.

## Comprobaciones antes de publicar

- Probar el exe local y revisar versión, arranque y actualización desde la instalada.
- Comprobar el panel lateral y sus iconos/diálogos desde el exe.
- Guardar PDF de una OT cerrada de Boixeres: un único archivo, ambas variantes,
  primero con técnico/tiempo y después sin ellos, con una sola elección de nombre.
- La primera vista preliminar PDF debe cerrarse antes de abrir la segunda variante.
- El aviso de recurso no accesible que pueda imprimir BIRT pertenece al PDF nativo
  y se acepta como limitación; no se convierte el HTML ni se oculta texto del informe.
- Comprobar el resumen al actualizar. Se extrae del bloque `### Resumen` de la
  sección 1.3.0 de CHANGELOG.md, el mismo contenido utilizado por el borrador GitHub.
- Técnico y Almacén mantienen menús, permisos y estados propios. No repetir cierres
  reales por comprobar la build; abrir fichas o reimprimir partes ya cerrados.

Subir el ZIP al borrador v1.3.0 después de validar la build y publicar solo cuando
se haya completado esa revisión. El borrador apunta al commit candidato de dev;
main se mantiene sin cambios durante esta preparación.
