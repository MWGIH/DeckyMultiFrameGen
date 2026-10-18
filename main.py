import asyncio
import re
from pathlib import Path

import decky

from multifg import backends, steam_library
from multifg.helixsr import HelixSR
from multifg.settings import Settings

HOME = Path(decky.DECKY_USER_HOME)
SETTINGS = Settings(Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json")
HELIXSR = HelixSR(HOME, Path(decky.DECKY_PLUGIN_RUNTIME_DIR), Path(decky.DECKY_PLUGIN_LOG_DIR), decky.DECKY_USER)
_APPID = re.compile(r"\d{1,10}")


def _valid_appid(appid) -> str:
    appid = str(appid)
    if not _APPID.fullmatch(appid):
        raise ValueError(f"Invalid app id: {appid!r}")
    return appid


def _game_folder(appid) -> str:
    """The install folder of an installed Steam game, or ValueError."""
    appid = _valid_appid(appid)
    matches = steam_library.installed_games(HOME, appid)
    if not matches or not matches[0]["install_found"]:
        raise ValueError("This game isn't installed")
    return matches[0]["install_path"]


async def _for_game(appid, work):
    """Runs work(folder) off the event loop for an installed game; errors come back as {ok: False, error}."""
    try:
        folder = _game_folder(appid)
        return await asyncio.to_thread(work, folder)
    except Exception as exc:
        decky.logger.exception("game action")
        return {"ok": False, "error": str(exc)}


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

    # --- HelixSR ---

    async def helixsr_status(self) -> dict:
        return await asyncio.to_thread(HELIXSR.status)

    async def helixsr_install(self, tag: str = "") -> dict:
        return await asyncio.to_thread(HELIXSR.start_install, tag or None)

    async def helixsr_game_status(self, appid: str) -> dict:
        return await _for_game(appid, HELIXSR.game_status)

    async def helixsr_install_game(self, appid: str, route: str = "") -> dict:
        return await _for_game(appid, lambda folder: HELIXSR.install_game(folder, route or None))

    async def helixsr_uninstall_game(self, appid: str) -> dict:
        return await _for_game(appid, HELIXSR.uninstall_game)

    async def log_error(self, message: str) -> None:
        decky.logger.error(f"frontend: {message}")

    async def _main(self):
        decky.logger.info("DeckyMultiFrameGen loaded")

    async def _unload(self):
        decky.logger.info("DeckyMultiFrameGen unloaded")
