import re
from pathlib import Path

import decky

from multifg import backends, steam_library
from multifg.settings import Settings

HOME = Path(decky.DECKY_USER_HOME)
SETTINGS = Settings(Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json")
_APPID = re.compile(r"\d{1,10}")


def _valid_appid(appid) -> str:
    appid = str(appid)
    if not _APPID.fullmatch(appid):
        raise ValueError(f"Invalid app id: {appid!r}")
    return appid


class Plugin:
    async def get_backends(self) -> list[dict]:
        return backends.all_status(HOME)

    async def list_installed_games(self) -> dict:
        try:
            games = steam_library.installed_games(HOME)
            return {"ok": True, "games": [{"appid": g["appid"], "name": g["name"]} for g in games if g["install_found"]]}
        except Exception as exc:
            decky.logger.error(f"list_installed_games: {exc}")
            return {"ok": False, "message": str(exc), "games": []}

    async def get_game(self, appid: str) -> dict:
        try:
            appid = _valid_appid(appid)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        matches = steam_library.installed_games(HOME, appid)
        game = matches[0] if matches else None
        return {
            "ok": True,
            "appid": appid,
            "name": game["name"] if game else None,
            "installed": bool(game and game["install_found"]),
            "install_path": game["install_path"] if game else None,
            "backend": SETTINGS.game_choice(appid),
            "choices": list(backends.GAME_CHOICES),
        }

    async def set_game_backend(self, appid: str, backend: str) -> dict:
        try:
            appid = _valid_appid(appid)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        if backend not in backends.GAME_CHOICES:
            return {"ok": False, "message": f"Unknown backend: {backend}"}
        SETTINGS.set_game_choice(appid, backend)
        return {"ok": True, "appid": appid, "backend": backend}

    async def log_error(self, message: str) -> None:
        decky.logger.error(f"frontend: {message}")

    async def _main(self):
        decky.logger.info("DeckyMultiFrameGen loaded")

    async def _unload(self):
        decky.logger.info("DeckyMultiFrameGen unloaded")
