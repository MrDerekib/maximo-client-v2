# Apariencia y legibilidad

Configuración → Apariencia conserva el tema (Según Windows, Claro, Oscuro, Dracula, Catppuccin Mocha, SynthWave ’84, Tokyo Night, Gruvbox Dark, Catppuccin Latte, Rosé Pine Dawn, Nord) y el
perfil de legibilidad de forma independiente. La vista previa es inmediata y
se conserva al pulsar **Guardar cambios**. No modifica datos ni preferencias de Edge.

| Perfil | Tipografía | Colores |
| --- | --- | --- |
| Normal | Texto base de 13 px, peso regular | Paleta del tema |
| Mayor visibilidad | Texto base de 15 px, seminegrita, filas más altas | Paleta del tema |
| Alto contraste | Como Mayor visibilidad | Textos y bordes reforzados a partir de la paleta |
| Personalizado | Tamaño y grosor elegidos por el usuario | Contraste y bordes ajustables por separado |

**Distinguir estados con colores** es una preferencia independiente y
está desactivada de forma predeterminada. Afecta a Estado en Maximo y Seguimiento.
Estado en Maximo: activo verde, prioridad ámbar, no activo rojo y desconocido violeta.
En Seguimiento:
texto de color seminegrita sin fondo: pendientes violeta, taller azul,
Dar salida/ISSUE verde, Cerrada/CLOSE cian/turquesa, retenidos/SAT ámbar y
cancelados/desechados rojo. Los estados de Maximo conocidos se muestran con su
nombre descriptivo. Al pasar el cursor se ve también el código de Maximo.
Las filas seleccionadas usan el color de selección para seguir siendo legibles.
Los estados desconocidos conservan el texto y el color originales.

## Añadir temas

`appearance.py` contiene las paletas de roles semánticos, los perfiles y los
cálculos de contraste. Para añadir un tema se registra una paleta con las mismas
claves que claro/oscuro. El selector, la validación de configuración y los perfiles
usan ese registro; no necesitan ramas específicas para cada tema. La elección de
iconos claros/oscuros depende de la luminancia, no de un hexadecimal concreto.
Los textos principales del perfil de alto contraste buscan una relación de 7:1
sobre superficies comunes y los bordes 3:1. Esto no equivale a certificar toda la UI.

Las cadenas QSS existentes se adaptan mediante el mapa de roles del tema base y
`legibility_css`; los componentes nuevos deben usar roles semánticos e heredar la
tipografía. Evitar colores y tamaños locales sin pasar por esta capa. Los perfiles
no corrigen cualquier combinación arbitraria de colores: cada nueva paleta debe
pasar las pruebas de contraste y revisión visual de widgets, selección y diálogos.

Cambiar apariencia recolorea las celdas existentes sin SQL ni reconstrucción de
la tabla. Los colores de seguimiento se calculan una vez por estado distinto,
no durante el pintado. El tamaño de filas se ajusta al perfil. No se alteran los
anchos de columna guardados, filtros, orden ni selección.

## Validación

`python -m unittest tests.test_appearance tests.test_filters tests.test_ui_settings_layout`

Las pruebas usan datos temporales aislados. Cubren todos los temas registrados y los tres perfiles,
un tema adicional ficticio, alias de estados, migración de ajustes, persistencia,
vista previa y conservación de celdas/selección sin consultas a la base de datos.

Los diálogos y editores comparten `component_css`; no deben capturar paletas en hojas de estilo locales ni buscar el módulo principal por nombre. Véase `auditoria-temas.md` para cobertura y generación de la galería.

## Primer tema adicional: Dracula

Basado en [Dracula Classic](https://draculatheme.com/spec): fondo #282A36,
texto #F8F8F2 y acento violeta #BD93F9. Las superficies intermedias y el texto
secundario se adaptan a formularios y tablas; no se usa el tono de comentarios
original para textos pequeños, para conservar su legibilidad. Los estados mantienen
su significado y los perfiles funcionan con el mismo motor de contraste.

El tema usa JetBrains Mono como fuente sugerida; se puede elegir otra sin cambiar
los colores. No requiere instalar extensiones ni acceder a Internet.
Los SVG de MD siguen siendo independientes de las fuentes instaladas.

El registro de temas alimenta la configuración, el selector y la matriz de auditoría;
la galería incluye automáticamente las nuevas paletas en los tres perfiles.

## Catppuccin Mocha

Basado en la [paleta oficial Mocha](https://catppuccin.com/palette/), con base
#1E1E2E, texto #CDD6F4 y acento malva #CBA6F7. El lateral usa Crust/Mantle;
las superficies intermedias se adaptan para distinguir filas y formularios.
Comparte los perfiles de legibilidad y los significados de estado de los demás
temas. Usa Inter como tipografía sugerida, incluida con MD.

## Más paletas

- **SynthWave ’84**: fondo violeta, rosa neón y cian, adaptado de
  [SynthWave VS Code](https://github.com/robb0wen/synthwave-vscode/blob/master/themes/synthwave-color-theme.json).
- **Tokyo Night**: azul nocturno y acentos azules, basado en
  [TokyoNight](https://github.com/folke/tokyonight.nvim/tree/main/lua/tokyonight/colors).
- **Gruvbox Dark**: grises cálidos, crema y ámbar, basado en
  [Gruvbox](https://github.com/morhetz/gruvbox).

Las superficies se adaptan para MD y los perfiles corrigen el contraste mediante
el motor compartido. El estilo neón no añade animaciones ni efectos de brillo;
los estados mantienen su significado habitual. La tipografía predeterminada acompaña al tema y puede sustituirse desde Configuración.

Para generar solo las capturas de una paleta: `python tools/audit_themes.py
--output RUTA --themes synthwave84`. Sin `--themes` se auditan todas.

## Variantes claras y Nord

- **[Catppuccin Latte](https://catppuccin.com/palette/)**: base clara y acento violeta.
- **[Rosé Pine Dawn](https://rosepinetheme.com/palette/)**: crema cálido y acento rosa.
- **[Nord](https://www.nordtheme.com/docs/colors-and-palettes/)**: gris azulado y cian suave.

Latte y Dawn incluyen laterales claros. Marca e iconos de búsqueda se colorean con
el texto semántico del lateral al arrancar y al cambiar el tema. Los colores
originales se adaptan a superficies de MD; el motor compartido refuerza contraste.

## Claro y Oscuro renovados

Claro usa superficies grises frías, texto grafito, acento azul y lateral claro.
Oscuro usa carbón neutro, superficies escalonadas y acento azul suave. Conservan
sus identificadores de configuración y el seguimiento Según Windows.

## Barra de título nativa

La ventana principal y los diálogos propios usan fondo, texto y borde de su paleta
mediante DWM. Se actualizan al mostrar/recrear una ventana y al cambiar el tema,
sin alterar los botones, el arrastre, el maximizado ni los estilos nativos.
Las ventanas sin marco, menús y tooltips se excluyen. Los atributos no disponibles
se ignoran en Windows antiguos; no se cambian preferencias globales del sistema.
La API admite los colores de caption en Windows 11. El selector nativo de archivos
u otras ventanas externas a los widgets de MD conservan su decoración del sistema.


## Tipografías incluidas

En General → Apariencia hay siete opciones: Predeterminada del tema, Sistema,
Inter, IBM Plex Sans, JetBrains Mono, Atkinson Hyperlegible Next y Space Grotesk. La elección personal se conserva al cambiar
el tema y solo se guarda al pulsar Guardar cambios. Los perfiles de legibilidad
siguen controlando el tamaño, el peso y el contraste de forma independiente.

| Temas | Predeterminada |
|---|---|
| Claro, Oscuro, Catppuccin Mocha y Latte | Inter |
| Dracula, SynthWave ’84 y Tokyo Night | JetBrains Mono |
| Gruvbox Dark, Rosé Pine Dawn y Nord | IBM Plex Sans |

Las fuentes variables se registran solo en el proceso de MD, sin instalación en
Windows. `ui_assets/fonts` contiene los TTF, sus licencias OFL y un manifiesto de
procedencia con SHA-256. El script de build ya incluye ese directorio completo.
Si no se carga una fuente, MD registra el fallo y usa la del sistema. Las barras
de título y otros diálogos nativos conservan la tipografía que controla Windows.

Atkinson Hyperlegible Next y Space Grotesk son opciones personales adicionales;
se mantienen las fuentes predeterminadas de los temas existentes.


## Legibilidad personalizada

El perfil Personalizado permite elegir un tamaño base entre 12 y 20 px, grosor
Regular/Seminegrita/Negrita, contraste de texto reforzado y bordes más visibles.
Contraste y bordes son independientes. Las filas de la tabla ajustan su altura al
tamaño elegido. Se conservan las jerarquías de títulos y los indicadores de estado.
La tipografía y los colores de seguimiento siguen siendo opciones independientes.

La vista previa es inmediata; Guardar cambios conserva la combinación. Cambiar a
un perfil predefinido no borra los ajustes personales. Descartar restaura lo guardado.
Las configuraciones anteriores mantienen el perfil que usaban y reciben una
combinación personal inicial de 13 px, peso regular y sin refuerzos adicionales.
