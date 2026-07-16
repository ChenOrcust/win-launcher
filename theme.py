_current_setting = "dark"

DARK = {
    "bg": "#18181b",
    "bg_widget": "#222226",
    "bg_hover": "#2c2c30",
    "bg_search": "#27272a",
    "bg_active": "#6366f1",
    "border": "#333338",
    "border_light": "#3f3f46",
    "text": "#fafafa",
    "text_secondary": "#e4e4e7",
    "text_muted": "#a1a1aa",
    "text_disabled": "#52525b",
    "text_danger": "#f87171",
    "danger_bg": "#3b1f1f",
    "scrollbar": "#52525b",
    "scrollbar_hover": "#71717a",
}

LIGHT = {
    "bg": "#f4f4f5",
    "bg_widget": "#ffffff",
    "bg_hover": "#e4e4e7",
    "bg_search": "#fafafa",
    "bg_active": "#6366f1",
    "border": "#d4d4d8",
    "border_light": "#e4e4e7",
    "text": "#18181b",
    "text_secondary": "#27272a",
    "text_muted": "#52525b",
    "text_disabled": "#a1a1aa",
    "text_danger": "#dc2626",
    "danger_bg": "#fef2f2",
    "scrollbar": "#a1a1aa",
    "scrollbar_hover": "#71717a",
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
