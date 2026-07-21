_current_setting = "dark"

DARK = {
    "bg": "#202020",
    "bg_widget": "#2b2b2b",
    "bg_hover": "#363636",
    "bg_search": "#1b1b1b",
    "bg_active": "#0078d4",
    "border": "#3f3f46",
    "border_light": "#505050",
    "text": "#f5f5f5",
    "text_secondary": "#e1e1e1",
    "text_muted": "#b8b8b8",
    "text_disabled": "#777777",
    "text_danger": "#ff99a4",
    "danger_bg": "#44272b",
    "scrollbar": "#5a5a5a",
    "scrollbar_hover": "#60cdff",
}

LIGHT = {
    "bg": "#f3f3f3",
    "bg_widget": "#ffffff",
    "bg_hover": "#e5f1fb",
    "bg_search": "#ffffff",
    "bg_active": "#0078d4",
    "border": "#d1d1d1",
    "border_light": "#e5e5e5",
    "text": "#1f1f1f",
    "text_secondary": "#333333",
    "text_muted": "#616161",
    "text_disabled": "#a0a0a0",
    "text_danger": "#c42b1c",
    "danger_bg": "#fde7e9",
    "scrollbar": "#b5b5b5",
    "scrollbar_hover": "#0078d4",
}


def detect_system_theme() -> str:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        val = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
        winreg.CloseKey(key)
        return "light" if val == 1 else "dark"
    except Exception:
        return "dark"


def resolve(setting: str) -> str:
    if setting == "auto":
        return detect_system_theme()
    return setting


def colors(setting: str) -> dict:
    return LIGHT if resolve(setting) == "light" else DARK


def current() -> dict:
    return colors(_current_setting)


def set_setting(setting: str):
    global _current_setting
    _current_setting = setting
