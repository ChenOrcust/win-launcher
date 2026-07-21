import os
from pathlib import Path

import pythoncom
from win32com.client import Dispatch
try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # Keep source runs usable before dependencies are installed.
    Style = None
    lazy_pinyin = None


_PINYIN_BOUNDARIES = (
    (b"\xb0\xa1", "A"), (b"\xb2\xc1", "B"), (b"\xb4\xee", "C"),
    (b"\xb6\xe9", "D"), (b"\xb7\xa2", "E"), (b"\xb8\xc1", "F"),
    (b"\xb9\xfe", "G"), (b"\xbb\xf7", "H"), (b"\xbf\xa6", "J"),
    (b"\xc0\xac", "K"), (b"\xc2\xc1", "L"), (b"\xc4\xea", "M"),
    (b"\xc5\xb2", "N"), (b"\xc5\xb4", "O"), (b"\xc5\xb6", "P"),
    (b"\xc5\xbe", "Q"), (b"\xc6\xda", "R"), (b"\xc8\xbb", "S"),
    (b"\xc8\xf6", "T"), (b"\xcb\xfa", "W"), (b"\xcd\xd9", "X"),
    (b"\xce\xf3", "Y"), (b"\xd1\xbb", "Z"),
)


def get_sort_initial(text: str) -> str:
    """Return the A-Z section for Latin or common Chinese leading text."""
    text = (text or "").strip()
    if not text:
        return "#"
    if lazy_pinyin is not None:
        first = lazy_pinyin(text[0], style=Style.FIRST_LETTER, errors="default")[0]
        first = (first or "").upper()
        return first if "A" <= first <= "Z" else "#"
    first = text[0].upper()
    if "A" <= first <= "Z":
        return first
    try:
        encoded = text[0].encode("gbk")
    except (UnicodeEncodeError, AttributeError):
        return "#"
    if len(encoded) != 2 or encoded < _PINYIN_BOUNDARIES[0][0]:
        return "#"
    result = "#"
    for boundary, initial in _PINYIN_BOUNDARIES:
        if encoded < boundary:
            break
        result = initial
    return result


def get_sort_key(text: str) -> tuple:
    value = (text or "").strip()
    if lazy_pinyin is not None:
        pinyin = "".join(lazy_pinyin(value, style=Style.NORMAL, errors="default"))
        return get_sort_initial(value), pinyin.casefold(), value.casefold()
    try:
        encoded = value.encode("gbk", errors="replace")
    except LookupError:
        encoded = value.casefold().encode("utf-8")
    return get_sort_initial(value), encoded


def _split_icon_location(value: str, fallback: str) -> tuple[str, int]:
    value = (value or "").strip()
    if not value:
        return fallback, 0
    path, separator, index_text = value.rpartition(",")
    if separator:
        try:
            return os.path.expandvars(path.strip().strip('"')), int(index_text.strip())
        except ValueError:
            pass
    return os.path.expandvars(value.strip('"')), 0


def _shortcut_to_app(shell, lnk_path: str, folder: str = "") -> dict | None:
    try:
        shortcut = shell.CreateShortCut(lnk_path)
        target = os.path.expandvars((shortcut.TargetPath or "").strip().strip('"'))
        icon_path, icon_index = _split_icon_location(shortcut.IconLocation, target)
        return {
            "name": Path(lnk_path).stem,
            "target": target,
            "args": shortcut.Arguments or "",
            "icon_path": icon_path,
            "icon_index": icon_index,
            "lnk_path": lnk_path,
            "working_dir": os.path.expandvars(shortcut.WorkingDirectory or ""),
            "folder": folder,
        }
    except Exception:
        return None


def parse_lnk_file(lnk_path: str) -> dict | None:
    pythoncom.CoInitialize()
    try:
        return _shortcut_to_app(Dispatch("WScript.Shell"), lnk_path)
    finally:
        pythoncom.CoUninitialize()


class StartMenuScanner:

    def __init__(self):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        programdata = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        candidates = [
            Path(appdata) / "Microsoft" / "Windows" / "Start Menu",
            Path(programdata) / "Microsoft" / "Windows" / "Start Menu",
        ]
        # Preserve order while removing the duplicated APPDATA/USERPROFILE root.
        self._roots = list(dict.fromkeys(str(path.resolve()) for path in candidates))
        self._apps: list[dict] = []

    @property
    def apps(self):
        return self._apps

    def scan(self):
        self._apps = []
        for directory in self._roots:
            if os.path.isdir(directory):
                self._scan_tree(directory)
        self._scan_shell_apps()

        seen = set()
        unique = []
        for app in self._apps:
            key = (
                app.get("name", "").casefold(),
                app.get("target", "").casefold(),
                app.get("args", "").casefold(),
                app.get("app_id", "").casefold(),
            )
            if key not in seen:
                seen.add(key)
                unique.append(app)
        unique.sort(key=lambda app: get_sort_key(app.get("name", "")))
        self._apps = unique
        return self._apps

    def _scan_tree(self, root_dir: str):
        pythoncom.CoInitialize()
        try:
            shell = Dispatch("WScript.Shell")
            for root, _dirs, files in os.walk(root_dir):
                rel = os.path.relpath(root, root_dir)
                folder = "" if rel == "." else rel
                for filename in files:
                    path = os.path.join(root, filename)
                    suffix = Path(filename).suffix.casefold()
                    if suffix == ".lnk":
                        app = _shortcut_to_app(shell, path, folder)
                    elif suffix in {".url", ".appref-ms"}:
                        app = {
                            "name": Path(filename).stem,
                            "target": path,
                            "args": "",
                            "icon_path": "",
                            "icon_index": 0,
                            "lnk_path": path,
                            "working_dir": "",
                            "folder": folder,
                        }
                    else:
                        continue
                    if app:
                        self._apps.append(app)
        finally:
            pythoncom.CoUninitialize()

    def _scan_shell_apps(self):
        """Include Store/UWP apps exposed by the Windows AppsFolder shell."""
        pythoncom.CoInitialize()
        folder = None
        items = None
        shell_app = None
        try:
            shell_app = Dispatch("Shell.Application")
            folder = shell_app.NameSpace("shell:AppsFolder")
            if folder is None:
                return
            existing_names = {app.get("name", "").casefold() for app in self._apps}
            items = folder.Items()
            for item in items:
                name = str(item.Name or "").strip()
                app_id = str(item.Path or "").strip()
                if not name or not app_id or name.casefold() in existing_names:
                    continue
                self._apps.append({
                    "name": name,
                    "target": "explorer.exe",
                    "args": f"shell:AppsFolder\\{app_id}",
                    "app_id": app_id,
                    "icon_path": "",
                    "icon_index": 0,
                    "lnk_path": "",
                    "working_dir": "",
                    "folder": "Windows Apps",
                })
                existing_names.add(name.casefold())
        except Exception:
            # AppsFolder availability varies between Windows editions.
            return
        finally:
            items = None
            folder = None
            shell_app = None
            pythoncom.CoUninitialize()

    def get_folder_index(self) -> dict[str, list[dict]]:
        index = {}
        for app in self._apps:
            folder = app.get("folder", "") or "(Root)"
            index.setdefault(folder, []).append(app)
        return index

    def search(self, query: str, limit: int = 100):
        query = query.strip().casefold()
        if not query:
            return []

        def searchable(app: dict) -> str:
            return " ".join((
                app.get("name", ""),
                app.get("folder", ""),
                Path(app.get("target", "")).stem,
            )).casefold()

        results = [app for app in self._apps if query in searchable(app)]
        results.sort(key=lambda app: (
            not app.get("name", "").casefold().startswith(query),
            get_sort_key(app.get("name", "")),
        ))
        return results[:limit]
