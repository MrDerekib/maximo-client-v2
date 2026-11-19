# Build de Maximo Desktop 1.4.1

## Compilación

Desde PowerShell, en el proyecto actual de la UI:

```powershell
Set-Location 'C:\Users\jcamp\OneDrive - Indra\Documentos\python\opencode\maximo-client-ui'
.\build_app.ps1
```

El script utiliza el entorno `.venv` del proyecto y lee `version.py`.
No es necesario modificar opciones de Nuitka ni usar la carpeta de la versión antigua.
Si ya existe una compilación de esta misma versión, `.\build_app.ps1 -Force`
permite reemplazarla expresamente.

## Resultado

- Carpeta de compilación: `release\MaximoDesktop-1.4.1`.
- Ejecutable: dentro de la subcarpeta `*.dist` generada por Nuitka.
- Paquete completo: `release\MaximoDesktop-1.4.1\MaximoDesktop-v1.4.1-windows.zip`.

Distribuir el ZIP completo; no copiar solamente el exe.

## Validación del ejecutable antes de publicar

1. Comprobar arranque y versión 1.4.1, conservando configuración, credenciales y datos.
2. Comprobar el resumen de novedades al pasar desde 1.4.0; cerrar y volver a abrir
   para confirmar que no se muestra una segunda vez.
3. Pegar una columna de OTs en el buscador; ordenar por cabeceras; copiar una o varias
   filas a Excel o correo. El copiado actual incluye texto y tabla HTML, sin hipervínculos.
4. Redimensionar columnas, ocultar/mostrar el lateral y reabrir la app para comprobar
   que se conservan los anchos elegidos manualmente.
5. Durante una actualización, comprobar el giro del icono y que un aviso temporal
   devuelve después el progreso de la tarea en curso.
6. En una OT conocida, consultar «Actualizar datos desde Maximo» y contrastar
   Seguimiento, avería y descripción ampliada. La consulta no cambia el estado remoto.
7. Abrir una revisión previa de SAT o reparación y cerrarla durante su consulta;
   comprobar legibilidad, número de serie y conservación de la escritura manual.
   No confirmar envíos, cierres ni desechos como parte de esta validación.

## Publicación

El borrador de GitHub debe usar el tag `v1.4.1` y apuntar al commit candidato de `dev`.
Subir el ZIP después de validar el ejecutable y publicar cuando se acepte el resultado.
No modificar la release 1.4.0 ya publicada. El resumen de MD se mantiene únicamente
bajo `### Resumen` de la sección 1.4.1 de `CHANGELOG.md`; las notas de GitHub se
preparan a partir de esa misma sección.

La preparación no incorpora cambios para Outlook ni modifica los enlaces de las filas copiadas.
