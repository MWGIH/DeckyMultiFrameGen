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

    def test_builds(self, current_version: str) -> bool:
        """Whether this plugin updates from the "test" prerelease. Until it's set, a test build keeps to test builds
        and a release to releases."""
        value = self.load().get("test_builds")
        return bool(value) if value is not None else "-test." in (current_version or "")

    def set_test_builds(self, on: bool) -> None:
        data = self.load()
        data["test_builds"] = bool(on)
        self.save(data)

    def game_choice(self, appid: str) -> str:
        return self.load().get("games", {}).get(appid, {}).get("backend", "none")

    def game_value(self, appid: str, key: str, default=None):
        """Another per-game setting kept next to the choice (e.g. "fsr4_watermark")."""
        return self.load().get("games", {}).get(appid, {}).get(key, default)

    def set_game_value(self, appid: str, key: str, value) -> None:
        data = self.load()
        data.setdefault("games", {}).setdefault(appid, {})[key] = value
        self.save(data)

    def games_using(self, part: str) -> list[str]:
        """App ids of the games whose choice includes part (e.g. "mako")."""
        games = self.load().get("games", {})
        return [a for a, g in games.items() if part in str(g.get("backend", "")).split("+")]

    def set_game_choice(self, appid: str, backend: str) -> None:
        data = self.load()
        games = data.setdefault("games", {})
        if backend == "none":
            # the game's other settings (e.g. its OptiScaler proxy DLL) stay for the next time it's set up
            game = games.get(appid, {})
            game.pop("backend", None)
            if not game:
                games.pop(appid, None)
        else:
            games.setdefault(appid, {})["backend"] = backend
        self.save(data)
