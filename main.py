import asyncio
import re
from pathlib import Path

import decky

from multifg import backends, steam_library
from multifg.helixsr import HelixSR
from multifg.opti_job import OptiInstallJob
from multifg.optiscaler import DEFAULT_FSR4_VARIANT as OPTISCALER_DEFAULT_VARIANT, OptiScaler
from multifg.settings import Settings

HOME = Path(decky.DECKY_USER_HOME)
SETTINGS = Settings(Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json")
HELIXSR = HelixSR(HOME, Path(decky.DECKY_PLUGIN_RUNTIME_DIR), Path(decky.DECKY_PLUGIN_LOG_DIR), decky.DECKY_USER)
OPTISCALER = OptiScaler()
OPTI_JOB = OptiInstallJob(OPTISCALER)
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
        try:
            if (await OPTISCALER.get_game_status(_valid_appid(appid))).get("patched"):
                return {"ok": False, "error": "OptiScaler is in this game. Remove it first: both use the same DLL slot."}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return await _for_game(appid, lambda folder: HELIXSR.install_game(folder, route or None))

    async def helixsr_uninstall_game(self, appid: str) -> dict:
        return await _for_game(appid, HELIXSR.uninstall_game)

    # --- OptiScaler (Decky Framegen) ---

    async def optiscaler_status(self) -> dict:
        status = await OPTISCALER.check_fgmod_path()
        status["job"] = OPTI_JOB.status()
        # an install from an earlier Decky Framegen: the files it needs now aren't all there
        status["legacy"] = not status.get("exists") and backends.optiscaler_status(HOME)["installed"]
        return status

    async def optiscaler_install(self, fsr4_variant: str = "") -> dict:
        """Starts the install; optiscaler_status reports its progress and result."""
        return OPTI_JOB.start(fsr4_variant or None)

    async def optiscaler_uninstall(self) -> dict:
        if OPTI_JOB.running():
            return {"status": "error", "message": "Wait for the install to finish"}
        return await OPTISCALER.run_uninstall_fgmod()

    async def optiscaler_game_status(self, appid: str) -> dict:
        try:
            return await OPTISCALER.get_game_status(_valid_appid(appid))
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}

    async def optiscaler_patch_game(self, appid: str, dll_name: str, current_launch_options: str,
                                    fsr4_variant: str = "") -> dict:
        try:
            folder = _game_folder(appid)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        if HELIXSR.active():
            helix = await asyncio.to_thread(HELIXSR.game_status, folder)
            if helix.get("installed"):
                return {"status": "error",
                        "message": "HelixSR is in this game. Remove it first: both use the same DLL slot."}
        return await OPTISCALER.patch_game(str(appid), dll_name, current_launch_options or "",
                                           fsr4_variant or OPTISCALER_DEFAULT_VARIANT)

    async def optiscaler_unpatch_game(self, appid: str) -> dict:
        try:
            return await OPTISCALER.unpatch_game(_valid_appid(appid))
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}

    async def log_error(self, message: str) -> None:
        decky.logger.error(f"frontend: {message}")

    async def _main(self):
        decky.logger.info("DeckyMultiFrameGen loaded")

    async def _unload(self):
        decky.logger.info("DeckyMultiFrameGen unloaded")
