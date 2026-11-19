# Build de Maximo Desktop 1.4.2

## Compilación

Desde PowerShell:

```powershell
Set-Location 'C:\Users\jcamp\OneDrive - Indra\Documentos\python\opencode\maximo-client-ui'
.\build_app.ps1
```

El script usa `.venv` y `version.py`. Si ya existe esta compilación, revisar su
contenido antes de usar `-Force`. Distribuir el ZIP completo, no solo el exe.

Resultado: `release\MaximoDesktop-1.4.2\MaximoDesktop-v1.4.2-windows.zip`.

## Validación antes de publicar

- Arranque, versión 1.4.2 y conservación de configuración y datos.
- Desde 1.4.1 se muestran solo las novedades de 1.4.2. Desde 1.4.0 se incluyen
  1.4.1 y 1.4.2. Tras aceptar no reaparecen. Instalación nueva sin historial completo.
- Prueba del compañero: pegar su rango de Excel en Detalles desde la extensión;
  revisar que conserve todas las líneas y completar el cierre de una OT autorizada.
  Repetir desde MD cuando haya otra OT disponible. El formato de tabla no se conserva.
- Ante un fallo previo al cierre: Comprobar y continuar, revisar la confirmación y
  verificar que respeta INPRG y no duplica Registro. Una confirmación final incierta
  permite solo reverificar, sin reenviar.
- Calendario: selección visible y Aplicar fecha y hora sin alterar datos manuales.
- Enlaces de integración: abrir, abrir y filtrar, o solo filtrar una OT exacta.
  El complemento de Outlook no se distribuye dentro de la build de MD.

## GitHub

Borrador con tag `v1.4.2` apuntando al candidato de `dev`. Subir el ZIP y publicar
tras comprobar el ejecutable y decidir la distribución de la prueba. No modificar
las releases ya publicadas. El resumen mostrado por MD está en `### Resumen` de
1.4.2 en `CHANGELOG.md` y se combina con los de versiones intermedias si procede.
