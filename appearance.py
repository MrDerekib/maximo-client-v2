"""Theme tokens and independent legibility profiles; no Qt or application data.

A theme supplies the same semantic roles as the existing palettes. Profiles derive
contrast and typography from those roles, never from a theme name or exact hex.
"""
import re
from dataclasses import dataclass

THEME_PALETTES = {
    "light": {
        "canvas":"#f4f5f7", "surface":"#ffffff", "subtle":"#eaedf2", "text":"#24292f",
        "heading":"#1f2328", "muted":"#57606a", "border":"#d8dee4", "border_strong":"#a8b3c0",
        "control":"#e8ecf1", "hover":"#dde4eb", "accent":"#0969da", "accent_hover":"#0758b8",
        "accent_light":"#e1ecfa", "sidebar":"#e8ecf1", "sidebar_surface":"#f2f4f7",
        "sidebar_hover":"#dbe2ea", "nav":"#0969da", "nav_border":"#0758b8",
        "sidebar_text":"#24292f", "sidebar_muted":"#57606a", "danger_bg":"#ffebe9",
        "danger":"#b42318", "grid":"#e8edf2", "header":"#edf1f5", "header_text":"#384353",
        "header_hover":"#dde4eb", "separator":"#cbd3dc", "soft_border":"#7d8998",
        "check_hover":"#e1ecfa", "success":"#18753c", "inactive":"#65717e",
        "priority":"#9a6700", "button_text":"#384353",
    },
    "dark": {
        "canvas":"#181b20", "surface":"#20242b", "subtle":"#272c34", "text":"#edf0f4",
        "heading":"#f7f9fb", "muted":"#b4bdc9", "border":"#383f4a", "border_strong":"#657285",
        "control":"#303741", "hover":"#3c4552", "accent":"#69a7ff", "accent_hover":"#8fbfff",
        "accent_light":"#2c4668", "sidebar":"#14171c", "sidebar_surface":"#1c2027",
        "sidebar_hover":"#2b333e", "nav":"#69a7ff", "nav_border":"#8fbfff",
        "sidebar_text":"#edf0f4", "sidebar_muted":"#b4bdc9", "danger_bg":"#422c33",
        "danger":"#f18b96", "grid":"#303741", "header":"#2a3039", "header_text":"#c7d0dc",
        "header_hover":"#363e49", "separator":"#454e5c", "soft_border":"#8996a8",
        "check_hover":"#2c4668", "success":"#79d5a4", "inactive":"#b4bdc9",
        "priority":"#edc878", "button_text":"#edf0f4",
    },
}
# Dracula Classic: https://draculatheme.com/spec . Intermediate surfaces are
# adapted for a data-heavy desktop UI; contrast profiles remain independent.
THEME_PALETTES['dracula'] = {
    'canvas':'#282a36', 'surface':'#30323f', 'subtle':'#383a4a', 'text':'#f8f8f2',
    'heading':'#f8f8f2', 'muted':'#b1b6cf', 'border':'#44475a', 'border_strong':'#727994',
    'control':'#44475a', 'hover':'#505369', 'accent':'#bd93f9', 'accent_hover':'#cfaefa',
    'accent_light':'#44475a', 'sidebar':'#21222c', 'sidebar_surface':'#282a36',
    'sidebar_hover':'#383a4a', 'nav':'#bd93f9', 'nav_border':'#cfaefa',
    'sidebar_text':'#f8f8f2', 'sidebar_muted':'#b1b6cf', 'danger_bg':'#4a303b',
    'danger':'#ff5555', 'grid':'#44475a', 'header':'#383a4a', 'header_text':'#d9d6ea',
    'header_hover':'#44475a', 'separator':'#44475a', 'soft_border':'#a49bc2',
    'check_hover':'#44475a', 'success':'#50fa7b', 'inactive':'#b1b6cf',
    'priority':'#ffb86c', 'button_text':'#f8f8f2',
}
# Catppuccin Mocha: https://catppuccin.com/palette/ . The intermediate
# surface is adapted to keep data rows distinct from the page background.
THEME_PALETTES['catppuccin_mocha'] = {
    'canvas':'#1e1e2e', 'surface':'#242436', 'subtle':'#2b2b40', 'text':'#cdd6f4',
    'heading':'#cdd6f4', 'muted':'#bac2de', 'border':'#45475a', 'border_strong':'#7f849c',
    'control':'#313244', 'hover':'#45475a', 'accent':'#cba6f7', 'accent_hover':'#f5c2e7',
    'accent_light':'#45475a', 'sidebar':'#11111b', 'sidebar_surface':'#181825',
    'sidebar_hover':'#313244', 'nav':'#cba6f7', 'nav_border':'#b4befe',
    'sidebar_text':'#cdd6f4', 'sidebar_muted':'#bac2de', 'danger_bg':'#452c40',
    'danger':'#f38ba8', 'grid':'#313244', 'header':'#313244', 'header_text':'#cdd6f4',
    'header_hover':'#45475a', 'separator':'#45475a', 'soft_border':'#9399b2',
    'check_hover':'#313244', 'success':'#a6e3a1', 'inactive':'#bac2de',
    'priority':'#f9e2af', 'button_text':'#cdd6f4',
}
# Adapted from the original theme palettes (sources in docs/apariencia.md).
THEME_PALETTES['synthwave84'] = {
    'canvas':'#262335', 'surface':'#2a2139', 'subtle':'#34294f', 'text':'#f4efff',
    'heading':'#ff7edb', 'muted':'#c7b7de', 'border':'#51416b', 'border_strong':'#9d8bca',
    'control':'#3b2e50', 'hover':'#463465', 'accent':'#ff7edb', 'accent_hover':'#03edf9',
    'accent_light':'#463465', 'sidebar':'#171520', 'sidebar_surface':'#241b2f',
    'sidebar_hover':'#34294f', 'nav':'#ff7edb', 'nav_border':'#03edf9',
    'sidebar_text':'#f4efff', 'sidebar_muted':'#c7b7de', 'danger_bg':'#512b42',
    'danger':'#fe4450', 'grid':'#3b2e50', 'header':'#34294f', 'header_text':'#03edf9',
    'header_hover':'#463465', 'separator':'#51416b', 'soft_border':'#b893ce',
    'check_hover':'#463465', 'success':'#72f1b8', 'inactive':'#c7b7de',
    'priority':'#fede5d', 'button_text':'#f4efff',
}
THEME_PALETTES['tokyo_night'] = {
    'canvas':'#1a1b26', 'surface':'#1f2335', 'subtle':'#24283b', 'text':'#c0caf5',
    'heading':'#c0caf5', 'muted':'#a9b1d6', 'border':'#3b4261', 'border_strong':'#737aa2',
    'control':'#292e42', 'hover':'#394b70', 'accent':'#7aa2f7', 'accent_hover':'#bb9af7',
    'accent_light':'#33467c', 'sidebar':'#16161e', 'sidebar_surface':'#1a1b26',
    'sidebar_hover':'#292e42', 'nav':'#7aa2f7', 'nav_border':'#7dcfff',
    'sidebar_text':'#c0caf5', 'sidebar_muted':'#a9b1d6', 'danger_bg':'#472b40',
    'danger':'#f7768e', 'grid':'#2f3549', 'header':'#24283b', 'header_text':'#c0caf5',
    'header_hover':'#292e42', 'separator':'#3b4261', 'soft_border':'#737aa2',
    'check_hover':'#292e42', 'success':'#9ece6a', 'inactive':'#a9b1d6',
    'priority':'#e0af68', 'button_text':'#c0caf5',
}
THEME_PALETTES['gruvbox_dark'] = {
    'canvas':'#282828', 'surface':'#32302f', 'subtle':'#3c3836', 'text':'#ebdbb2',
    'heading':'#fbf1c7', 'muted':'#bdae93', 'border':'#665c54', 'border_strong':'#928374',
    'control':'#3c3836', 'hover':'#504945', 'accent':'#fabd2f', 'accent_hover':'#fe8019',
    'accent_light':'#504945', 'sidebar':'#1d2021', 'sidebar_surface':'#282828',
    'sidebar_hover':'#3c3836', 'nav':'#fabd2f', 'nav_border':'#fe8019',
    'sidebar_text':'#ebdbb2', 'sidebar_muted':'#bdae93', 'danger_bg':'#502d2d',
    'danger':'#fb4934', 'grid':'#3c3836', 'header':'#3c3836', 'header_text':'#ebdbb2',
    'header_hover':'#504945', 'separator':'#665c54', 'soft_border':'#a89984',
    'check_hover':'#504945', 'success':'#b8bb26', 'inactive':'#bdae93',
    'priority':'#fabd2f', 'button_text':'#ebdbb2',
}
# Additional original palettes, adapted to the same semantic role schema.
THEME_PALETTES['catppuccin_latte'] = {
    'canvas':'#eff1f5', 'surface':'#f8f9fc', 'subtle':'#e6e9ef', 'text':'#4c4f69',
    'heading':'#4c4f69', 'muted':'#5c5f77', 'border':'#ccd0da', 'border_strong':'#8c8fa1',
    'control':'#e6e9ef', 'hover':'#ccd0da', 'accent':'#8839ef', 'accent_hover':'#6e2cce',
    'accent_light':'#e3d8f4', 'sidebar':'#dce0e8', 'sidebar_surface':'#e6e9ef',
    'sidebar_hover':'#ccd0da', 'nav':'#8839ef', 'nav_border':'#7287fd',
    'sidebar_text':'#4c4f69', 'sidebar_muted':'#5c5f77', 'danger_bg':'#f9e2e8',
    'danger':'#d20f39', 'grid':'#dce0e8', 'header':'#e6e9ef', 'header_text':'#4c4f69',
    'header_hover':'#ccd0da', 'separator':'#bcc0cc', 'soft_border':'#7c7f93',
    'check_hover':'#e3d8f4', 'success':'#40a02b', 'inactive':'#6c6f85',
    'priority':'#df8e1d', 'button_text':'#4c4f69',
}
THEME_PALETTES['rose_pine_dawn'] = {
    'canvas':'#faf4ed', 'surface':'#fffaf3', 'subtle':'#f2e9e1', 'text':'#464261',
    'heading':'#464261', 'muted':'#797593', 'border':'#dfdad9', 'border_strong':'#9893a5',
    'control':'#f2e9e1', 'hover':'#e8ded8', 'accent':'#b4637a', 'accent_hover':'#a34f6a',
    'accent_light':'#eed9df', 'sidebar':'#f2e9e1', 'sidebar_surface':'#faf4ed',
    'sidebar_hover':'#e8ded8', 'nav':'#b4637a', 'nav_border':'#907aa9',
    'sidebar_text':'#464261', 'sidebar_muted':'#625e79', 'danger_bg':'#f7e2e7',
    'danger':'#b4637a', 'grid':'#f2e9e1', 'header':'#f2e9e1', 'header_text':'#464261',
    'header_hover':'#e8ded8', 'separator':'#dfdad9', 'soft_border':'#907aa9',
    'check_hover':'#eed9df', 'success':'#286983', 'inactive':'#797593',
    'priority':'#ea9d34', 'button_text':'#464261',
}
THEME_PALETTES['nord'] = {
    'canvas':'#2e3440', 'surface':'#353c4a', 'subtle':'#3b4252', 'text':'#eceff4',
    'heading':'#eceff4', 'muted':'#d8dee9', 'border':'#4c566a', 'border_strong':'#7b88a1',
    'control':'#434c5e', 'hover':'#4c566a', 'accent':'#88c0d0', 'accent_hover':'#8fbcbb',
    'accent_light':'#4c566a', 'sidebar':'#242933', 'sidebar_surface':'#2e3440',
    'sidebar_hover':'#3b4252', 'nav':'#88c0d0', 'nav_border':'#81a1c1',
    'sidebar_text':'#eceff4', 'sidebar_muted':'#d8dee9', 'danger_bg':'#513947',
    'danger':'#bf616a', 'grid':'#434c5e', 'header':'#3b4252', 'header_text':'#e5e9f0',
    'header_hover':'#434c5e', 'separator':'#4c566a', 'soft_border':'#81a1c1',
    'check_hover':'#434c5e', 'success':'#a3be8c', 'inactive':'#d8dee9',
    'priority':'#ebcb8b', 'button_text':'#eceff4',
}
THEME_LABELS = {'light':'Claro', 'dark':'Oscuro', 'dracula':'Dracula',
                'catppuccin_mocha':'Catppuccin Mocha', 'synthwave84':'SynthWave ’84',
                'tokyo_night':'Tokyo Night', 'gruvbox_dark':'Gruvbox Dark',
                'catppuccin_latte':'Catppuccin Latte', 'rose_pine_dawn':'Rosé Pine Dawn', 'nord':'Nord'}

_LIGHT_HEX_ROLES = {
    "#f5f7fb": "canvas", "#ffffff": "surface", "#f8fafc": "subtle",
    "#172033": "text", "#102a43": "heading", "#627d98": "muted", "#d9e2ec": "border",
    "#bcccdc": "border_strong", "#e8eef5": "control", "#1976d2": "accent", "#125ea7": "accent_hover",
    "#dbeafe": "accent_light", "#163854": "sidebar_surface", "#1e446b": "sidebar_hover",
    "#2f80ed": "nav", "#4d9cff": "nav_border", "#e6f0ff": "sidebar_text", "#9fb3c8": "sidebar_muted",
    "#fff1f0": "danger_bg", "#c53030": "danger", "#edf2f7": "grid", "#f0f4f8": "header",
    "#486581": "header_text", "#e2e8f0": "header_hover", "#cbd5e1": "separator",
    "#829ab1": "soft_border", "#eef5ff": "check_hover", "#2f855a": "success",
    "#718096": "inactive", "#b7791f": "priority", "#243b53": "button_text",
}

@dataclass(frozen=True)
class LegibilityProfile:
    label: str
    scale: float
    weight: int
    contrast: bool = False
    borders: bool = False
    row_height: int = 30


# Shared text-size trial. All existing 12px rules scale from this single base.
_BASE_TEXT_PX = 12
NORMAL_TEXT_PX = 13
VISIBLE_TEXT_PX = 15

PROFILES = {
    "normal": LegibilityProfile("Normal", NORMAL_TEXT_PX / _BASE_TEXT_PX, 400),
    "comfortable": LegibilityProfile("Mayor visibilidad", VISIBLE_TEXT_PX / _BASE_TEXT_PX, 600, row_height=36),
    "contrast": LegibilityProfile("Alto contraste", VISIBLE_TEXT_PX / _BASE_TEXT_PX, 600, True, borders=True, row_height=36),
    "custom": LegibilityProfile("Personalizado", NORMAL_TEXT_PX / _BASE_TEXT_PX, 400),
}


def default_custom_legibility():
    return {"text_size": NORMAL_TEXT_PX, "weight": 400, "contrast": False, "borders": False}


def normalize_custom_legibility(value):
    result = default_custom_legibility()
    if not isinstance(value, dict):
        return result
    try:
        if not isinstance(value.get("text_size"), bool):
            result["text_size"] = min(20, max(12, int(value.get("text_size", NORMAL_TEXT_PX))))
    except (TypeError, ValueError, OverflowError):
        pass
    if type(value.get("weight")) is int and value["weight"] in (400, 600, 700):
        result["weight"] = value["weight"]
    for key in ("contrast", "borders"):
        if isinstance(value.get(key), bool):
            result[key] = value[key]
    return result


def custom_legibility(value):
    options = normalize_custom_legibility(value)
    return LegibilityProfile("Personalizado", options["text_size"] / _BASE_TEXT_PX,
        options["weight"], options["contrast"], options["borders"],
        max(30, round(30 * options["text_size"] / NORMAL_TEXT_PX)))


def profile_for(name):
    return name if isinstance(name, LegibilityProfile) else PROFILES.get(name, PROFILES["normal"])


def luminance(color):
    rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))


def is_dark(colors):
    return luminance(colors["canvas"]) < .179


def contrast_ratio(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + .05) / (low + .05)


def readable_color(color, backgrounds, target=7):
    """Keep the hue when possible, darken/lighten only as much as necessary."""
    if min(contrast_ratio(color, bg) for bg in backgrounds) >= target:
        return color
    endpoint = max(("#000000", "#ffffff"),
                   key=lambda c: min(contrast_ratio(c, bg) for bg in backgrounds))
    original = [int(color[i:i+2], 16) for i in (1, 3, 5)]
    dest = [int(endpoint[i:i+2], 16) for i in (1, 3, 5)]
    # A bounded search is performed once per palette, never during cell painting.
    for step in range(1, 101):
        result = "#" + "".join(f"{round(v + (d-v)*step/100):02x}" for v, d in zip(original, dest))
        if min(contrast_ratio(result, bg) for bg in backgrounds) >= target:
            return result
    return endpoint


def effective_palette(base, profile="normal"):
    colors = dict(base)
    surfaces = [colors[k] for k in ("canvas", "surface", "subtle", "control", "header")]
    if not profile_for(profile).contrast:
        for role in ('text','muted','inactive','button_text','header_text'):
            colors[role] = readable_color(colors[role],surfaces,4.5)
        for role in ('sidebar_text','sidebar_muted'):
            colors[role] = readable_color(colors[role],[colors['sidebar'],colors['sidebar_surface'],colors['sidebar_hover']],4.5)
    if profile_for(profile).contrast:
        for role in ("text", "heading", "muted", "inactive", "header_text", "button_text", "success", "priority", "danger"):
            colors[role] = readable_color(colors[role], surfaces)
        for role in ("sidebar_text", "sidebar_muted"):
            colors[role] = readable_color(colors[role], [colors["sidebar"], colors["sidebar_surface"], colors["sidebar_hover"]])
    if profile_for(profile).borders:
        for role in ("border", "border_strong", "grid", "separator", "soft_border"):
            colors[role] = readable_color(colors[role], surfaces, 3)
    # Dedicated status tones keep their saturation even when the general palette
    # uses subdued accents. New themes can override any of these semantic roles.
    tones = ({"muted":"#c7a4ff", "accent":"#70b5ff", "success":"#4ee29a",
              "priority":"#ffc052", "danger":"#ff8397", "closed":"#22d3ee"} if is_dark(colors) else
             {"muted":"#6620ad", "accent":"#0049bd", "success":"#006b2c",
              "priority":"#963d00", "danger":"#b00025", "closed":"#00677f"})
    for role, tone in tones.items():
        colors.setdefault("tracking_"+role, tone)
    colors["on_accent"] = readable_color("#ffffff", [colors["accent"]], 4.5)
    colors["on_nav"] = readable_color("#ffffff", [colors["nav"]], 4.5)
    return colors


def legibility_css(css, profile="normal"):
    settings = profile_for(profile)
    if settings.scale != 1:
        css = re.sub(r"font-size:\s*(\d+)px", lambda m: f"font-size: {round(int(m[1])*settings.scale)}px", css)
    if settings.weight > 400:
        css = re.sub(r"font-weight:\s*400", f"font-weight: {settings.weight}", css)
    return css


def application_legibility_css(profile):
    settings = profile_for(profile)
    # Target readable text controls, not QWidget (* would reset all title weights).
    size = round(_BASE_TEXT_PX * settings.scale)
    return f"""
    QLabel, QLineEdit, QComboBox, QSpinBox, QAbstractSpinBox, QCheckBox,
    QRadioButton, QTextEdit, QPlainTextEdit, QTableView, QListView, QMenu,
    QPushButton, QStatusBar {{ font-size: {size}px; font-weight: {settings.weight}; }}
    """


def appearance_overrides(colors):
    return f"""
    QTableWidget {{ selection-background-color: {colors['accent_light']}; selection-color: {colors['text']}; }}
    QTableWidget::item:selected {{ background: {colors['accent_light']}; color: {colors['text']}; }}
    QPushButton#primary {{ color: {colors['on_accent']}; }}
    QListWidget#profileList::item:selected {{ color: {colors['on_nav']}; }}
    QPushButton#nav:checked {{ color: {colors['on_nav']}; }}
    QTableWidget {{ color: {colors['text']}; }}
    QMenu {{ background: {colors['surface']}; color: {colors['text']}; border: 1px solid {colors['border_strong']}; padding: 5px; }}
    QMenu::item {{ background: transparent; color: {colors['text']}; padding: 8px 26px 8px 14px; }}
    QMenu::item:selected:enabled {{ background: {colors['accent_light']}; color: {colors['text']}; }}
    QMenu::item:disabled {{ color: {colors['inactive']}; }}
    QMenu::separator {{ height: 1px; background: {colors['border']}; margin: 5px 8px; }}
    """


TRACKING_ROLES = {
    "WAPPR": "muted", "PDTE CONFIRMAR": "muted",
    "APPR": "accent", "EN TALLER": "accent", "INPRG": "accent",
    "ISSUE": "success", "DAR SALIDA": "success",
    "CLOSE": "closed", "CERRADA": "closed", "CERRADO": "closed",
    "RETENIDO": "priority", "SAT INT": "priority", "SAT EXT": "priority",
    "DESECHADO": "danger", "CANCELADA": "danger", "CAN": "danger",
}


def tracking_style(value, colors) -> tuple[str, bool]:
    """Return readable foreground and emphasis; cell backgrounds stay unchanged."""
    role = TRACKING_ROLES.get(" ".join(str(value).upper().split()))
    tone = colors.get('tracking_'+role, colors.get(role, colors['text'])) if role else colors['text']
    return readable_color(tone, [colors['surface'], colors['subtle']], 4.5), role is not None


def tracking_color(value, colors):
    return tracking_style(value, colors)[0]


def presence_style(active, priority, colors) -> tuple[str, bool]:
    role = 'priority' if active == 1 and priority else 'success' if active == 1 else 'danger' if active == 0 else 'muted'
    tone = colors.get('tracking_'+role, colors[role])
    return readable_color(tone, [colors['surface'], colors['subtle']], 4.5), True


def component_css(colors, assets_dir):
    """Shared Qt surfaces: never snapshot a palette into an individual dialog."""
    arrow = (assets_dir / ('chevron-down-light.svg' if is_dark(colors) else 'chevron-down-dark.svg')).as_posix()
    arrow_variant = 'light' if is_dark(colors) else 'dark'
    previous = (assets_dir / ('chevron-left-'+arrow_variant+'.svg')).as_posix()
    following = (assets_dir / ('chevron-right-'+arrow_variant+'.svg')).as_posix()
    upward = (assets_dir / ('chevron-up-'+arrow_variant+'.svg')).as_posix()
    ink = 'dark' if luminance(colors['on_accent']) < .179 else 'light'
    check = (assets_dir / ('check-'+ink+'.svg')).as_posix()
    dash = (assets_dir / ('dash-'+ink+'.svg')).as_posix()
    radio = (assets_dir / ('radio-'+ink+'.svg')).as_posix()
    disabled = readable_color(colors['inactive'], [colors['subtle'],colors['control'],colors['surface']],4.5)
    return f"""
    QFrame#roundedTableFrame {{ background: {colors['surface']}; border: 1px solid {colors['border']}; border-radius: 8px; }}
    QTableWidget#roundedTable {{ border: none; border-radius: 0px; }}
    QLabel#brand {{ color: {colors['sidebar_text']}; }}
    QFrame#sidebarExportSeparator {{ color: {colors['border_strong']}; }}
    QSplitter#sidebarSplitter::handle {{ background: {colors['canvas']}; }}
    QSplitter#sidebarSplitter::handle:hover {{ background: {colors['accent']}; }}
    QListWidget#profileList, QPushButton#sidebarAction {{ border-color: {colors['border_strong']}; }}
    QPushButton#sidebarAction:disabled {{ color: {colors['sidebar_muted']}; }}
    QPushButton#sidebarAction:hover {{ background: {colors['sidebar_surface']}; color: {colors['sidebar_text']}; }}
    QToolButton#navigationMenu {{ padding: 5px 23px 5px 5px; font-size: 14px; }}
    QToolButton#navigationMenu::menu-indicator {{
        image: url("{arrow}"); width: 12px; height: 12px;
        subcontrol-origin: padding; subcontrol-position: center right; right: 5px; }}
    QDialog, QMessageBox, QInputDialog, QProgressDialog, QFileDialog,
    QWidget#repairReviewPanel {{ background: {colors['canvas']}; color: {colors['text']}; }}
    QDialog QLabel, QDialog QCheckBox, QDialog QRadioButton {{ color: {colors['text']}; }}
    QDialogButtonBox {{ background: transparent; }}
    QScrollArea {{ background: {colors['canvas']}; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: {colors['canvas']}; }}
    QPlainTextEdit, QTextEdit, QTextBrowser, QDateTimeEdit {{
        background: {colors['surface']}; color: {colors['text']};
        border: 1px solid {colors['border_strong']}; border-radius: 6px; padding: 6px;
        selection-background-color: {colors['accent_light']}; selection-color: {colors['text']}; }}
    QPlainTextEdit:focus, QTextEdit:focus, QDateTimeEdit:focus {{ border: 2px solid {colors['accent']}; }}
    QDateTimeEdit {{ padding-right: 36px; min-height: 18px; }}
    QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{ image: url("{arrow}"); width: 14px; height: 14px; }}
    DecoratedComboBox::down-arrow, DecoratedDateEdit::down-arrow {{ image: none; }}
    QDateTimeEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right;
        width: 30px; border-left: 1px solid {colors['border']}; background: {colors['subtle']};
        border-top-right-radius: 6px; border-bottom-right-radius: 6px; }}
    QDateTimeEdit::drop-down:hover {{ background: {colors['control']}; }}
    QAbstractItemView {{ background: {colors['surface']}; alternate-background-color: {colors['subtle']};
        color: {colors['text']}; selection-background-color: {colors['accent_light']}; selection-color: {colors['text']}; }}
    QCalendarWidget QWidget {{ background: {colors['surface']}; color: {colors['text']}; }}
    QCalendarWidget QToolButton {{ background: {colors['control']}; color: {colors['text']}; padding: 6px; border: 0; }}
    QCalendarWidget QToolButton#qt_calendar_prevmonth {{ qproperty-icon: url("{previous}"); }}
    QCalendarWidget QToolButton#qt_calendar_nextmonth {{ qproperty-icon: url("{following}"); }}
    QCalendarWidget QAbstractItemView {{ background: {colors['surface']}; color: {colors['text']};
        selection-background-color: {colors['accent_light']}; selection-color: {colors['text']}; }}
    QProgressBar {{ background: {colors['control']}; color: {colors['text']};
        border: 1px solid {colors['border_strong']}; border-radius: 4px; min-height: 16px; text-align: center; }}
    QProgressBar::chunk {{ background: {colors['accent_light']}; border-radius: 3px; }}
    QScrollBar:vertical {{ background: {colors['control']}; width: 14px; margin: 2px; border-radius: 6px; }}
    QScrollBar::handle:vertical {{ background: {colors['muted']}; min-height: 32px; border-radius: 5px; }}
    QScrollBar::handle:vertical:hover {{ background: {colors['accent']}; }}
    QScrollBar:horizontal {{ background: {colors['control']}; height: 14px; margin: 2px; border-radius: 6px; }}
    QScrollBar::handle:horizontal {{ background: {colors['muted']}; min-width: 32px; border-radius: 5px; }}
    QScrollBar::handle:horizontal:hover {{ background: {colors['accent']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QFileDialog QToolButton#backButton {{ qproperty-icon: url("{previous}"); }}
    QFileDialog QToolButton#forwardButton {{ qproperty-icon: url("{following}"); }}
    QFileDialog QToolButton#toParentButton {{ qproperty-icon: url("{upward}"); }}
    QToolTip {{ background: {colors['surface']}; color: {colors['text']}; border: 1px solid {colors['border_strong']}; padding: 6px; }}
    QPushButton:disabled, QPushButton#primary:disabled, QPushButton#dialogPrimary:disabled {{
        background: {colors['subtle']}; color: {disabled}; border: 1px solid {colors['border']}; }}
    QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{
        background: {colors['subtle']}; color: {disabled}; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {colors['border_strong']}; background: {colors['surface']}; }}
    QCheckBox::indicator {{ border-radius: 3px; }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {colors['accent']}; }}
    QCheckBox::indicator:checked, QCheckBox::indicator:indeterminate, QRadioButton::indicator:checked {{ background: {colors['accent']}; border-color: {colors['accent']}; }}
    QCheckBox::indicator:checked {{ image: url("{check}"); }}
    QCheckBox::indicator:indeterminate {{ image: url("{dash}"); }}
    QRadioButton::indicator:checked {{ image: url("{radio}"); }}
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {colors['border']}; }}
    QCheckBox:disabled, QRadioButton:disabled, QDialog QLabel:disabled {{ color: {disabled}; }}
    QLabel#dialogTitle {{ font-size: 20px; font-weight: 700; color: {colors['heading']}; }}
    QLabel#releaseNotesTitle {{ font-size: 22px; font-weight: 700; color: {colors['heading']}; }}
    QLabel#sectionTitle {{ font-size: 13px; font-weight: 700; color: {colors['heading']}; }}
    QLabel#muted {{ color: {colors['muted']}; }}
    QFrame#priorityReport {{ background: {colors['subtle']}; border: 1px solid {colors['border']}; border-radius: 7px; }}
    QPushButton#priorityFilter, QPushButton#advancedFilter {{ border: 1px solid {colors['border_strong']}; padding: 7px 12px; }}
    QPushButton#priorityFilter:checked, QPushButton#advancedFilter[filtersActive="true"] {{ background: {colors['accent']};
        color: {colors['on_accent']}; border-color: {colors['accent']}; }}
    QPushButton#priorityFilter:checked:hover, QPushButton#advancedFilter[filtersActive="true"]:hover {{ background: {colors['accent']}; }}
    QPushButton#dialogPrimary {{ background: {colors['accent']}; color: {colors['on_accent']}; }}
    QPushButton#dialogPrimary:hover {{ background: {colors['accent_hover']}; }}
    QDialog#activityDialog {{ background: transparent; border: none; }}
    QFrame#activityCard {{ background: {colors['surface']}; border: 1px solid {colors['border']}; border-radius: 10px; }}
    QLabel#activityTitle {{ background: transparent; border: none; color: {colors['heading']}; font-size: 13px; font-weight: 700; }}
    QLabel#activityMessage {{ background: transparent; border: none; color: {colors['text']}; font-size: 11px; }}
    QProgressBar#activityProgress {{ border: none; border-radius: 2px; background: {colors['subtle']}; min-height: 5px; max-height: 5px; }}
    QProgressBar#activityProgress::chunk {{ background: {colors['accent']}; border-radius: 2px; }}
    QMenu#clientSelectionMenu QCheckBox {{ color: {colors['text']}; background: transparent;
        border: 0; border-radius: 6px; padding: 7px 10px; spacing: 9px; min-width: 190px; font-size: 12px; }}
    QMenu#clientSelectionMenu QCheckBox:hover {{ color: {colors['heading']}; background: {colors['header']}; }}
    """
