# Auditoría de temas Qt · 2026-11-13

Se revisa la UI nueva de MD con todos los temas registrados (Claro, Oscuro, Dracula, Catppuccin Mocha,
SynthWave ’84, Tokyo Night, Gruvbox Dark, Catppuccin Latte, Rosé Pine Dawn y Nord), cada uno en Normal, Mayor visibilidad
y Alto contraste. No se realizan acciones reales ni se utilizan cuentas de Maximo.

## Problemas corregidos

- El formulario de reparación buscaba colores en `sys.modules['ui_qt']`. Al ejecutar
  `ui_qt.py` como `__main__` podía usar un fallback claro mientras la app estaba
  oscura. Se ha eliminado esa dependencia y su hoja local de colores.
- Formularios, progreso y confirmaciones heredaban fondos de diferentes orígenes.
  Ahora usan estilos comunes de aplicación, incluidos scroll y sus paneles.
- Editores de detalles, fecha/hora, barras de progreso, tooltips, casillas y radios
  no tenían todos sus estados definidos. Se cubren estados normal, foco, selección
  y deshabilitado con tokens de la paleta.
- Los menús contextuales y submenús mezclaban estilos nativos. Tienen fondo, texto,
  selección y deshabilitados explícitos.
- Calendarios e importación de prioridades tenían colores o iconos locales. Los
  días, cabeceras y flechas siguen ahora el tema, también en calendarios creados
  después del cambio de colores.
- Novedades y avisos de actividad mantenían colores capturados al abrirse. Heredan
  los estilos comunes y se adaptan al cambiar el tema mientras permanecen abiertos.
- Ayudas y placeholders normales reciben contraste mínimo de 4,5:1 en superficies
  comunes; Alto contraste refuerza los textos principales a 7:1.

## Cobertura visual reproducible

33 superficies por combinación, **990 capturas**:

- Listado y las cuatro pestañas de Configuración.
- Filtros, selector de clientes y menús contextual, Técnico y Almacén.
- Importación de prioridades y calendarios, incluido fecha/hora de reparación.
- Formularios de cierre y desecho, detalles, confirmación y progreso/recuperación.
- SAT técnico, recepción, salida, SAT interno/externo y recuperación de operaciones.
- Avisos de información, advertencia y error; entrada de texto y descarga.
- Novedades, descripción detallada, casillas/radios y selector de archivos Qt.

```powershell
.\.venv\Scripts\python.exe tools/audit_themes.py --output C:\Temp\md-theme-audit
```

El script usa `tests` para aislar datos, desactiva los trabajos de arranque y
bloquea `QThread.start`. Genera `index.html` y un manifiesto con capturas de datos
ficticios. El directorio de salida debe quedar fuera de la distribución.

## Regresión

`tests.test_theme_surfaces` comprueba las seis combinaciones sobre ventanas ya
creadas: fondo de diálogos y paneles, texto de formularios y confirmaciones,
contraste de editores y fechas, novedades y calendarios. Incluye la reproducción
sin alias `ui_qt` para que no reaparezca el fallback de `__main__`.

La comprobación de roles y capturas no certifica accesibilidad completa. Las barras
de título y los selectores nativos de Windows siguen el tema del sistema; la UI
de Maximo/Edge y el contenido del parte son superficies externas a los temas de MD.

## Decoración nativa y paletas neutras

Claro y Oscuro se revisan con sus paletas renovadas. Los iconos del lateral y el
texto de marca heredan el contraste del tema, incluido el lateral claro.

`tests.test_native_titlebar` comprueba el orden COLORREF y tamaño de los valores
DWM, la actualización de ventanas abiertas/nuevas, caché, exclusión de ventanas
sin marco y compatibilidad con atributos no disponibles. La validación manual
mediante ventanas ficticias de Windows 11 comprobó 60 combinaciones (10 temas ×
3 perfiles × ventana principal/diálogo nuevo), con llamadas DWM aceptadas y sin
alterar los flags nativos. La galería offscreen no captura marcos del sistema;
esta prueba nativa complementa las capturas de widgets.
