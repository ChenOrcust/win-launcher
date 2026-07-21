import os

import pythoncom
from win32com.client import Dispatch


def parse_lnk_file(lnk_path: str) -> dict | None:
    try:
        pythoncom.CoInitialize()
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        target = shortcut.TargetPath or ""
        if not target or not os.path.isfile(target):
            return None
        name = os.path.splitext(os.path.basename(lnk_path))[0]
        icon_loc = shortcut.IconLocation or ""
        icon_parts = icon_loc.split(",", 1) if icon_loc else []
        icon_index = int(icon_parts[1]) if len(icon_parts) == 2 and icon_parts[1].strip() else 0
        return {
            "name": name,
            "target": target,
            "args": shortcut.Arguments or "",
            "icon_path": os.path.expandvars(icon_parts[0] or target),
            "icon_index": icon_index,
            "lnk_path": lnk_path,
            "working_dir": shortcut.WorkingDirectory or "",
            "folder": "",
        }
    except Exception:
        return None
    finally:
        pythoncom.CoUninitialize()


class StartMenuScanner:

    def __init__(self):
        appdata = os.environ.get("APPDATA", "")
        progdata = os.environ.get("PROGRAMDATA", "")
        user_profile = os.environ.get("USERPROFILE", "")
        self._roots = [
            os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(progdata, "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(
                user_profile,
                "AppData",
                "Roaming",
                "Microsoft",
                "Windows",
                "Start Menu",
                "Programs",
            ),
        ]
        self._apps = []

    @property
    def apps(self):
        return self._apps

    def scan(self):
        self._apps = []
        for directory in self._roots:
            if os.path.exists(directory):
                self._scan_tree(directory)
        seen = set()
        unique = []
        for app in self._apps:
            key = app["name"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(app)
        self._apps = unique
        return self._apps

    def _scan_tree(self, root_dir: str):
        pythoncom.CoInitialize()
        try:
            shell = Dispatch("WScript.Shell")
            for root, _dirs, files in os.walk(root_dir):
                rel = os.path.relpath(root, root_dir)
                folder = "" if rel == "." else rel
                for file in files:
                    if not file.lower().endswith(".lnk"):
                        continue
                    lnk_path = os.path.join(root, file)
                    try:
                        shortcut = shell.CreateShortCut(lnk_path)
                        target = shortcut.TargetPath or ""
                        if not target or not os.path.isfile(target):
                            continue
                        name = os.path.splitext(file)[0]
                        icon_loc = shortcut.IconLocation or ""
                        icon_parts = icon_loc.split(",", 1) if icon_loc else []
                        icon_index = int(icon_parts[1]) if len(icon_parts) == 2 and icon_parts[1].strip() else 0
                        self._apps.append({
                            "name": name,
                            "target": target,
                            "args": shortcut.Arguments or "",
                            "icon_path": os.path.expandvars(icon_parts[0] or target),
                            "icon_index": icon_index,
                            "lnk_path": lnk_path,
                            "working_dir": shortcut.WorkingDirectory or "",
                            "folder": folder,
                        })
                    except Exception:
                        pass
        finally:
            pythoncom.CoUninitialize()

    def get_folder_index(self) -> dict[str, list[dict]]:
        idx = {}
        for a in self._apps:
            f = a.get("folder", "") or "(Root)"
            idx.setdefault(f, []).append(a)
        return idx

    def search(self, query: str, limit: int = 30):
        if not query:
            return []
        q = query.lower()
        results = [app for app in self._apps if q in app["name"].lower()]
        results.sort(key=lambda x: (not x["name"].lower().startswith(q), x["name"]))
        return results[:limit]
