import json
from pathlib import Path


class ConfigManager:

    def __init__(self, config_dir: str | Path):
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "config.json"
        self.groups_file = self.config_dir / "groups.json"
        self._data = self._defaults()
        self._groups = []
        self.load()

    def _defaults(self):
        return {
            "hotkey_modifiers": ["Ctrl", "Alt"],
            "hotkey_key": "Space",
            "auto_start": False,
            "theme": "dark",
            "window_x": None,
            "window_y": None,
            "window_width": 640,
            "window_height": 520,
        }

    def load(self):
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text("utf-8"))
                self._data = self._defaults() | data
            except Exception:
                self._data = self._defaults()
        if self.groups_file.exists():
            try:
                self._groups = json.loads(self.groups_file.read_text("utf-8"))
            except Exception:
                self._groups = []

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), "utf-8"
        )
        self.groups_file.write_text(
            json.dumps(self._groups, indent=2, ensure_ascii=False), "utf-8"
        )

    @property
    def groups(self):
        return self._groups

    def add_group(self, name: str, apps: list | None = None):
        group = {"name": name, "apps": apps or []}
        self._groups.append(group)
        self.save()
        return group

    def remove_group(self, index: int):
        if 0 <= index < len(self._groups):
            del self._groups[index]
            self.save()

    def update_group(self, index: int, data: dict):
        if 0 <= index < len(self._groups):
            self._groups[index] |= data
            self.save()

    def add_app_to_group(self, group_index: int, app: dict):
        if 0 <= group_index < len(self._groups):
            self._groups[group_index]["apps"].append(app)
            self.save()

    def remove_app_from_group(self, group_index: int, app_index: int):
        if 0 <= group_index < len(self._groups):
            apps = self._groups[group_index]["apps"]
            if 0 <= app_index < len(apps):
                del apps[app_index]
                self.save()

    def set_auto_start(self, enabled: bool):
        self._data["auto_start"] = enabled
        self.save()

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()
