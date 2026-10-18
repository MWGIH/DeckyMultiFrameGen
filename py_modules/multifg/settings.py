"""Per-game choices, stored as JSON in the plugin's settings folder."""

import json
from pathlib import Path


class Settings:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
        tmp.replace(self.path)

    def game_choice(self, appid: str) -> str:
        return self.load().get("games", {}).get(appid, {}).get("backend", "none")

    def set_game_choice(self, appid: str, backend: str) -> None:
        data = self.load()
        games = data.setdefault("games", {})
        if backend == "none":
            games.pop(appid, None)
        else:
            games.setdefault(appid, {})["backend"] = backend
        self.save(data)
