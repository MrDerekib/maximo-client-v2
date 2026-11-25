# Maximo Desktop 1.5.0

## Novedades acumuladas

### Resumen para el aviso de MD

- **Todos los roles:** una acción unificada permite reintentar operaciones pendientes elegibles. Las operaciones y su historial están accesibles desde el listado.
- **Todos los roles:** navegación organizada en Archivo, Ver y Maximo. Se puede volver al listado desde Configuración, ocultar columnas y leer los estados de Maximo con etiquetas más claras. El formulario avisa si el estado no permite finalizar la OT, sin impedir la edición de los datos.
- **Técnico:** la incidencia se exige solo para TMB y L9. Boixeres queda excluido de esa regla. La comparación del número de serie admite diferencias de espacios equivalentes.
- **Técnico · Partes de reparación:** el origen se obtiene de la descripción de Ubicación inicial para ATM y L9, con selección configurable por proyecto y ubicación dentro de Datos del equipo. El logo actual de Indra y la limpieza de avisos BIRT de recursos no disponibles se pueden activar por separado. Ambas opciones vienen activadas por defecto.
- **Técnico · Boixeres:** se preparan dos copias del parte.
- **Almacén:** se mantienen las funciones existentes de recepción y salida con revisión de las OTs. Esta versión no añade acciones nuevas de almacén.

## Preparación del paquete

La versión del ejecutable se toma de `version.py`. El script de build empaqueta automáticamente los recursos de `browser_extension`.

```powershell
.\build_app.ps1
```

Paquete esperado:

`release/MaximoDesktop-1.5.0/MaximoDesktop-v1.5.0-windows.zip`

## Smoke test

1. Se abre el listado y aparecen las opciones Archivo, Ver y Maximo.
2. El menú Ver permite ocultar y volver a mostrar columnas.
3. Configuración muestra el botón Volver al listado junto a Guardar cambios.
4. En una OT de prueba autorizada, revisar que los estados sean legibles y que los contadores de operaciones pendientes se actualicen.
5. En una OT apta para impresión, comprobar las preferencias del logo y la limpieza de avisos BIRT, junto con el origen en Datos del equipo.
6. Verificar las dos copias del parte para el flujo Boixeres.

7. En un PDF con la primera página llena, comprobar que se añade la continuación sin cortar texto y se actualiza la numeración.
8. Actualizar desde 1.4.3: aparecen solo las novedades de 1.5.0. Desde una versión anterior aparecen también los resúmenes intermedios pendientes. Al aceptar no vuelven a mostrarse.

Las comprobaciones del ejecutable se hacen después de compilar, antes de publicar. El resumen mostrado por MD se toma de `### Resumen` de 1.5.0 en `CHANGELOG.md`.

## GitHub

El borrador de release usa el tag `v1.5.0` y el commit candidato de `dev`.
Tras compilar y comprobar el ejecutable, subir el ZIP completo al borrador y publicarlo.
