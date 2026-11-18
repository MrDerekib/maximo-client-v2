"""Curated, bundled application fonts; independent of colours and legibility."""
from dataclasses import dataclass
import logging

@dataclass(frozen=True)
class FontOption:
    label: str
    family: str = ""
    asset: str = ""

FONT_OPTIONS = {
    "theme": FontOption("Predeterminada del tema"),
    "system": FontOption("Sistema"),
    "atkinson_hyperlegible_next": FontOption("Atkinson Hyperlegible Next", "Atkinson Hyperlegible Next", "atkinson-hyperlegible-next/AtkinsonHyperlegibleNext-Variable.ttf"),
    "space_grotesk": FontOption("Space Grotesk", "Space Grotesk", "space-grotesk/SpaceGrotesk-Variable.ttf"),
    "inter": FontOption("Inter", "Inter", "inter/Inter-Variable.ttf"),
    "ibm_plex_sans": FontOption("IBM Plex Sans", "IBM Plex Sans", "ibm-plex-sans/IBMPlexSans-Variable.ttf"),
    "jetbrains_mono": FontOption("JetBrains Mono", "JetBrains Mono", "jetbrains-mono/JetBrainsMono-Variable.ttf"),
}
THEME_FONTS = {
    "light": "inter", "dark": "inter", "catppuccin_mocha": "inter", "catppuccin_latte": "inter",
    "dracula": "jetbrains_mono", "synthwave84": "jetbrains_mono", "tokyo_night": "jetbrains_mono",
    "gruvbox_dark": "ibm_plex_sans", "rose_pine_dawn": "ibm_plex_sans", "nord": "ibm_plex_sans",
}

def normalize_font(preference):
    return preference if isinstance(preference, str) and preference in FONT_OPTIONS else "theme"

def resolved_font_key(preference, theme):
    preference = normalize_font(preference)
    return THEME_FONTS.get(theme, "inter") if preference == "theme" else preference

def apply_font(app, assets_root, preference, theme):
    """Load fonts once per QApplication, falling back to its original system font."""
    from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
    if not hasattr(app, "_md_system_font"):
        app._md_system_font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
        app._md_system_font.setFamily(QFontInfo(app._md_system_font).family())
        app._md_font_families = {}
        for key, option in FONT_OPTIONS.items():
            if not option.asset:
                continue
            font_id = QFontDatabase.addApplicationFont(str(assets_root / "fonts" / option.asset))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                app._md_font_families[key] = option.family if option.family in families else families[0]
            else:
                logging.warning("No se pudo cargar la tipografía %s; se usará la del sistema.", option.label)
    key = resolved_font_key(preference, theme)
    font = QFont(app._md_system_font)
    family = app._md_font_families.get(key, font.family())
    font.setFamily(family)
    app.setFont(font)
    return family
