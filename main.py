import asyncio
import inspect
import re
import shlex
from pathlib import Path

import decky

from mako_plugin.plugin import Plugin as MakoPlugin

from multifg import backends, game_files, helix_opti, leftovers, mako_payload, steam_library, updates
from multifg.fsr4injector import FSR4Injector
from multifg.helixsr import OPTI_RELEASE, HelixSR
from multifg.opti_job import OptiInstallJob
from multifg.optiscaler import OPTISCALER_ARCHIVE_ASSET, OptiScaler
from multifg.settings import Settings

HOME = Path(decky.DECKY_USER_HOME)
SETTINGS = Settings(Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json")
HELIXSR = HelixSR(HOME, Path(decky.DECKY_PLUGIN_RUNTIME_DIR), Path(decky.DECKY_PLUGIN_LOG_DIR), decky.DECKY_USER)
OPTISCALER = OptiScaler()
OPTI_JOB = OptiInstallJob(OPTISCALER)
# The Steam Deck's GPU is RDNA2: always Valve's FSR 4.1.1 build with RDNA2 settings, no choice offered
FSR4_VARIANT = "rdna2-valve-411-pre10"
MAKO = MakoPlugin()  # MAKO Decky's backend (vendored); its methods are exposed below as mako_<name>
FSR4 = FSR4Injector(Path(decky.DECKY_PLUGIN_RUNTIME_DIR), Path(decky.DECKY_PLUGIN_SETTINGS_DIR))
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


_OVERRIDES = re.compile(r'\bWINEDLLOVERRIDES=("[^"]*"|\S*)\s*')


_MAKO_RUNNER = re.compile(r"""(?:'[^']*mako-(?:run|launch)'|"[^"]*mako-(?:run|launch)"|\S*mako-(?:run|launch))\s+""")


def _tidy(rest: str) -> str:
    rest = rest.strip()
    if rest == "%command%":
        return ""
    # "%command% -dx12" means the same to Steam as "-dx12"
    return rest[len("%command% "):] if rest.startswith("%command% ") and "%command%" not in rest[10:] else rest


def _without_overrides(options: str) -> str:
    """Launch options without a WINEDLLOVERRIDES=... (like withoutOverrides in src/launchOptions.ts)."""
    return _tidy(_OVERRIDES.sub("", options))


def _with_overrides(options: str, wanted: str) -> str:
    """Launch options with wanted's WINEDLLOVERRIDES=... in front (like withOverrides in src/launchOptions.ts)."""
    m = _OVERRIDES.search(wanted or "")
    if not m:
        return options
    rest = _OVERRIDES.sub("", options or "").strip()
    return f"{m.group(0).strip()} {rest if '%command%' in rest else f'%command% {rest}'.strip()}"


def _without_mako(options: str) -> str:
    """Launch options without MAKO's launcher (~/.local/bin/mako-run) in front of %command%."""
    return _tidy(_MAKO_RUNNER.sub("", options))


def _mako_runner() -> str:
    return MAKO.installation_service.get_launch_script_path()


def _with_mako(options: str) -> str:
    """MAKO's launcher put in front of %command%, keeping everything else the game had."""
    runner = shlex.quote(_mako_runner())
    base = _without_mako(options)
    if "%command%" in base:
        return base.replace("%command%", f"{runner} %command%", 1)
    return f"{runner} %command% {base}".strip()


async def _clear_game(appid: str, folder: str, keep: str, launch: str) -> dict:
    """Removes every backend not in keep (a game choice, e.g. "optiscaler+mako") from the game, since they would
    conflict (OptiScaler and HelixSR use the same DLL slot), and puts MAKO's launcher in the launch options when keep
    has MAKO. Returns {ok, removed: [names], launch_options: what they become, or None if unchanged} or {ok: False}."""
    keeps = set(keep.split("+"))
    removed, new_launch = [], launch
    # FSR4 Injector's DLLs sit next to the game's FSR 3.1 DLL, which HelixSR's drop-in replaces
    if "fsr4injector" not in keeps and await asyncio.to_thread(FSR4.enabled, int(appid)):
        r = await asyncio.to_thread(FSR4.disable, int(appid), new_launch)
        removed.append("FSR4 Injector")
        new_launch = r["launch_options"] if r["launch_options"] is not None else new_launch
    in_opti = {"optiscaler", "helixsr"} <= keeps
    if not in_opti:
        target = await _opti_target(appid)
        if target and (await asyncio.to_thread(helix_opti.status, target))["installed"]:
            await asyncio.to_thread(helix_opti.uninstall, target)
            removed.append("HelixSR (in OptiScaler)")
    # also a patch whose OptiScaler DLL has gone (target_dir comes with any Framegen marker)
    if "optiscaler" not in keeps and (await OPTISCALER.get_game_status(appid)).get("target_dir"):
        r = await OPTISCALER.unpatch_game(appid)
        if r.get("status") != "success":
            return {"ok": False, "error": f"Couldn't remove OptiScaler: {r.get('message')}"}
        removed.append("OptiScaler")
        new_launch = r.get("launch_options") or ""
    # HelixSR's own install (FSR drop-in or HelixSR Scaler) goes when HelixSR runs inside OptiScaler instead
    if ("helixsr" not in keeps or in_opti) and HELIXSR.active():
        helix = await asyncio.to_thread(HELIXSR.game_status, folder)
        if helix.get("installed"):
            r = await asyncio.to_thread(HELIXSR.uninstall_game, folder)
            if not r.get("ok"):
                return {"ok": False, "error": f"Couldn't remove HelixSR: {r.get('error')}"}
            removed.append("HelixSR")
            if helix.get("current") == "scaler":
                new_launch = _without_overrides(new_launch)
    if not keeps & {"optiscaler", "helixsr"}:
        left = await asyncio.to_thread(_sweep_leftovers, appid)
        if left:
            decky.logger.info(f"Leftovers cleaned in {appid}: {left}")
            removed.append("leftover OptiScaler/HelixSR files")
    if "mako" not in keeps and _MAKO_RUNNER.search(new_launch + " "):
        new_launch = _without_mako(new_launch)
        removed.append("MAKO")
    elif "mako" in keeps and Path(_mako_runner()).is_file():
        new_launch = _with_mako(new_launch)
    return {"ok": True, "removed": removed,
            "launch_options": new_launch if new_launch != launch else None}


async def _auto_install_helix(appid: str, folder: str, launch: str) -> dict | None:
    """Puts HelixSR in a game just set to HelixSR: HelixSR Scaler where the game can take it, else HelixSR's own pick.
    None when it's already in or the game needs a decision first (anti-cheat, no way in): the panel then offers it."""
    try:
        status = game_files.helix_ways(appid, await asyncio.to_thread(HELIXSR.game_status, folder))
    except Exception:
        decky.logger.exception("HelixSR status")
        return None
    if not status.get("ok") or not status.get("found") or status.get("installed") or status.get("anticheat"):
        return None
    ways = status.get("ways") or []
    route = "scaler" if "scaler" in ways else status.get("route")
    if route not in ways:
        return None
    try:
        result = await asyncio.to_thread(HELIXSR.install_game, folder, route)
    except Exception as exc:
        decky.logger.exception("HelixSR install")
        result = {"ok": False, "error": str(exc)}
    return {**result, "route": result.get("route") or route}


def _fsr4_backend() -> dict:
    """FSR4 Injector's line in Backends: installed once its release is unpacked and AMD's library is fetched."""
    st = FSR4.status()
    notes = []
    gpu = st["gpu"]
    if st["unpacked"] and gpu:
        model = gpu.get("model_name") or "none: games stay on FSR 3"
        notes.append(f"GPU {gpu.get('arch')}: FSR 4 model {model}"
                     + ("" if gpu.get("verified") or not gpu.get("model") else " (beta: not yet confirmed by FSR4 Injector's author)"))
    elif st["unpacked"]:
        notes.append("No AMD GPU found: FSR 4 can't run here")
    if st["unpacked"] and not st["dll_ready"]:
        notes.append("AMD's FSR 4 library isn't downloaded yet")
    if st["recipe"] and st["dll_ready"]:
        notes.append(f"AMD FSR {st['recipe']['fsr']} from {st['recipe']['driver']}")
    return {"installed": st["ready"], "version": st["version"], "path": str(FSR4.base), "notes": notes}


def _sweep_leftovers(appid: str) -> list[str]:
    """leftovers.sweep in the folder OptiScaler and HelixSR go into (the game's .exe folder)."""
    game = OPTISCALER._game_record(appid)
    if not game or not Path(game["install_path"]).is_dir():
        return []
    target, _ = OPTISCALER._guess_patch_target(game)
    return leftovers.sweep(target, Path(HOME) / "fgmod")


async def _opti_target(appid: str) -> str | None:
    """The folder OptiScaler is patched into in this game, or None."""
    st = await OPTISCALER.get_game_status(appid)
    return st.get("target_dir") if st.get("patched") else None


async def _opti_frame_generation_off(appid: str, helix: dict | None = None) -> None:
    """With MAKO in the game, OptiScaler's frame generation goes off: in the OptiScaler Decky Framegen put in, and in
    HelixSR Scaler (an OptiScaler build next to the game's .exe)."""
    try:
        target = await _opti_target(appid)
        if target:
            await asyncio.to_thread(helix_opti.frame_generation_off, target)
        if helix is None:
            try:
                helix = await _for_game(appid, HELIXSR.game_status)
            except Exception:
                helix = {}
        if helix.get("current") == "scaler" and helix.get("exe_folder"):
            await asyncio.to_thread(helix_opti.frame_generation_off, helix["exe_folder"])
    except Exception:
        decky.logger.exception("OptiScaler frame generation off")


async def _add_helix_to_opti(appid: str) -> dict:
    target = await _opti_target(appid)
    if not target:
        return {"ok": False, "error": "Patch the game with OptiScaler first."}
    tag = await asyncio.to_thread(HELIXSR.opti_release)
    if not tag:
        return {"ok": False, "needs": OPTI_RELEASE,
                "error": f"OptiScaler needs HelixSR {OPTI_RELEASE}: HelixSR 2.0 and newer only run in their own HelixSR Scaler."}
    return await asyncio.to_thread(helix_opti.install, HELIXSR.release_dir(tag), target, tag)


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
        out = backends.all_status(HOME)
        # the release games get (the newest whose setup finished), not just the newest folder that looks like one
        active = await asyncio.to_thread(HELIXSR.active)
        for b in out:
            if b["id"] == backends.HELIXSR and active:
                b.update(installed=True, version=active)
            # MAKO's frame generation needs Lossless Scaling's DLL: found the way MAKO looks for it (any Steam library)
            if b["id"] == backends.MAKO:
                try:
                    found = (await MAKO.check_lossless_scaling_dll("")).get("detected")
                    b["lossless_scaling"] = bool(found) or b.get("lossless_scaling", False)
                except Exception:
                    decky.logger.exception("Lossless Scaling check")
            # MAKO's launcher can be there without the MAKO Renderer it starts (removed, or a partial install)
            if b["id"] == backends.MAKO and b.get("installed"):
                b["version"] = updates.MAKO_VENDORED   # MAKO Decky's controls this plugin carries
                try:
                    r = await MAKO.check_mako_installed()
                    b["renderer_installed"] = bool(r.get("installed"))
                    have, want = r.get("installed_engine_version"), r.get("expected_engine_version")
                    if r.get("installed"):
                        line = f"MAKO Renderer {have or 'installed (version unknown)'}"
                        if r.get("engine_update_required") and want:
                            line += f": {want} is available, update it under Check for updates"
                        b["notes"] = [line, *(b.get("notes") or [])]
                except Exception:
                    decky.logger.exception("MAKO Renderer check")
        out.append({"id": backends.FSR4INJECTOR, **backends.UPSTREAM[backends.FSR4INJECTOR],
                    **await asyncio.to_thread(_fsr4_backend)})
        return out

    async def plugin_version(self) -> str:
        """This plugin's version as Decky loaded it (a test build reads e.g. 0.9.0-test.64)."""
        return decky.DECKY_PLUGIN_VERSION

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
        installed = bool(game and game["install_found"])
        current = SETTINGS.game_choice(appid)
        # only the choices that can work with the upscalers the game ships (and whatever it is set to now)
        found = None
        if installed:
            try:
                found = await asyncio.to_thread(game_files.detect, game["install_path"])
            except Exception:
                decky.logger.exception("game_files.detect")
        choices = [c for c in backends.GAME_CHOICES
                   if c == current or (game_files.fits(c, found) and not game_files.not_working(appid, c))]
        hidden = [{"choice": c, "needs": game_files.labels(set(game_files.needs(c))),
                   "reason": game_files.not_working(appid, c)}
                  for c in backends.GAME_CHOICES if c not in choices]
        return {
            "ok": True,
            "appid": appid,
            "name": game["name"] if game else None,
            "installed": installed,
            "install_path": game["install_path"] if game else None,
            "backend": current,
            "choices": choices,
            "all_choices": list(backends.GAME_CHOICES),   # for the panel's "Show all Use options"
            "upscalers": game_files.labels(found) if found is not None else None,
            "hidden": hidden,
        }

    async def set_game_backend(self, appid: str, backend: str, current_launch_options: str | None = None) -> dict:
        """Saves the game's choice and, given its launch options, takes the other backends out of the game."""
        try:
            appid = _valid_appid(appid)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        if backend not in backends.GAME_CHOICES:
            return {"ok": False, "message": f"Unknown backend: {backend}"}
        cleared = {"removed": [], "launch_options": None}
        folder = None
        if current_launch_options is not None:
            try:
                folder = _game_folder(appid)
            except ValueError:
                folder = None
            if folder:
                cleared = await _clear_game(appid, folder, backend, current_launch_options)
                if not cleared["ok"]:
                    return {"ok": False, "message": cleared["error"]}
        SETTINGS.set_game_choice(appid, backend)
        # FSR4 Injector has nothing to pick per game: it goes in as soon as the game is set to it
        fsr4 = None
        if "fsr4injector" in backend.split("+") and folder and await asyncio.to_thread(FSR4.ready) \
                and not await asyncio.to_thread(FSR4.enabled, int(appid)):
            launch = cleared["launch_options"] if cleared["launch_options"] is not None else current_launch_options
            fsr4 = await asyncio.to_thread(FSR4.enable, int(appid), folder, launch or "",
                                           SETTINGS.game_value(appid, "fsr4_watermark", False))
            if fsr4.get("ok"):
                cleared["launch_options"] = fsr4["launch_options"]
        # HelixSR (on its own or with MAKO) goes in as HelixSR Scaler as soon as the game is set to it
        helix = None
        if backend in ("helixsr", "helixsr+mako") and folder and HELIXSR.active() \
                and await asyncio.to_thread(HELIXSR.ready, HELIXSR.active()):
            launch = cleared["launch_options"] if cleared["launch_options"] is not None else current_launch_options
            helix = await _auto_install_helix(appid, folder, launch or "")
            if helix and helix.get("ok") and helix.get("launch_options"):
                cleared["launch_options"] = _with_overrides(launch or "", helix["launch_options"])
        added = None
        if {"optiscaler", "helixsr"} <= set(backend.split("+")) and await _opti_target(appid):
            added = await _add_helix_to_opti(appid)
        if "mako" in backend.split("+"):
            await _opti_frame_generation_off(appid, None if "helixsr" in backend.split("+") else {})
        return {"ok": True, "appid": appid, "backend": backend, "helix_in_opti": added, "fsr4": fsr4, "helix": helix,
                "removed": cleared["removed"],
                "launch_options": cleared["launch_options"]}

    # --- MAKO (its own controls are the mako_* methods at the end) ---

    async def mako_games(self) -> list[str]:
        """Games set to a choice with MAKO (their launch options carry MAKO's launcher)."""
        return SETTINGS.games_using("mako")

    async def mako_game_launch_options(self, current_launch_options: str, enable: bool) -> dict:
        """The launch options with MAKO's launcher added or taken out."""
        installed = Path(_mako_runner()).is_file()
        if enable and not installed:
            return {"ok": False, "error": "Install MAKO first", "installed": False}
        new = _with_mako(current_launch_options) if enable else _without_mako(current_launch_options)
        return {"ok": True, "installed": installed, "launch_options": new,
                "enabled": bool(_MAKO_RUNNER.search(new + " ")), "runner": _mako_runner()}

    # --- HelixSR ---

    async def helixsr_status(self) -> dict:
        return await asyncio.to_thread(HELIXSR.status)

    async def helixsr_log(self, lines: int = 80) -> dict:
        return await asyncio.to_thread(HELIXSR.setup_log, lines)

    async def helixsr_install(self, tag: str = "") -> dict:
        return await asyncio.to_thread(HELIXSR.start_install, tag or None)

    async def helixsr_set_prereleases(self, on: bool) -> dict:
        """Whether HelixSR's pre-releases are offered as updates (HelixSR 3.0.0 came out as one)."""
        return await asyncio.to_thread(HELIXSR.set_prereleases, bool(on))

    async def helixsr_remove(self) -> dict:
        """HelixSR out of every game, then its files deleted."""
        try:
            games = [g for g in steam_library.installed_games(HOME) if g["install_found"]]
            for g in games:
                target = await _opti_target(g["appid"])
                if target:
                    await asyncio.to_thread(helix_opti.uninstall, target)
            return await asyncio.to_thread(HELIXSR.remove, [g["install_path"] for g in games])
        except Exception as exc:
            decky.logger.exception("helixsr_remove")
            return {"ok": False, "error": str(exc)}

    async def helixsr_game_status(self, appid: str) -> dict:
        return game_files.helix_ways(appid, await _for_game(appid, HELIXSR.game_status))

    async def helixsr_install_game(self, appid: str, route: str = "", current_launch_options: str = "") -> dict:
        """Installs HelixSR into the game, taking OptiScaler out first if it's there. base_launch_options, when set, are
        the launch options to apply before HelixSR's own (OptiScaler's were removed)."""
        try:
            folder = _game_folder(appid)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        # nothing is taken out of the game when the way asked for would break it
        banned = game_files.NO_HELIX_WAYS.get(str(appid), {})
        if route in banned:
            return {"ok": False, "error": banned[route]}
        if not route and banned:
            # HelixSR's automatic pick could be a way that breaks this game
            status = game_files.helix_ways(appid, await _for_game(appid, HELIXSR.game_status))
            route = status.get("route") if status.get("route") in ("direct", "scaler") else ""
            if not route:
                return {"ok": False, "error": next(iter(banned.values()))}
        # with HelixSR + MAKO chosen, MAKO stays and its launcher stays in the launch options
        choice = SETTINGS.game_choice(str(appid)).split("+")
        keep = "helixsr+mako" if "mako" in choice and "optiscaler" not in choice else "helixsr"
        cleared = await _clear_game(str(appid), folder, keep, current_launch_options or "")
        if not cleared["ok"]:
            return cleared
        result = await _for_game(appid, lambda folder: HELIXSR.install_game(folder, route or None))
        if result.get("ok") and keep == "helixsr+mako":
            await _opti_frame_generation_off(str(appid), result)
        return {**result, "removed": cleared["removed"], "base_launch_options": cleared["launch_options"]}

    async def optiscaler_logging(self, appid: str, on: bool | None = None) -> dict:
        """OptiScaler's log file (off by default) in the game's OptiScaler.ini: switched when on is given."""
        try:
            target = await _opti_target(_valid_appid(appid))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if not target:
            return {"ok": False, "error": "Patch the game with OptiScaler first"}
        logging = await asyncio.to_thread(helix_opti.opti_logging, target, None if on is None else bool(on))
        return {"ok": logging is not None, "logging": logging, "path": str(Path(target) / "OptiScaler.log")}

    async def helixsr_scaler_logging(self, appid: str, on: bool) -> dict:
        """OptiScaler's log file on or off for HelixSR Scaler in the game (off by default: without it a game that stops
        before HelixSR loads leaves no log at all)."""
        game = await _for_game(appid, HELIXSR.game_status)
        if game.get("current") != "scaler" or not game.get("exe_folder"):
            return {"ok": False, "error": "HelixSR Scaler isn't installed in this game"}
        logging = await asyncio.to_thread(helix_opti.opti_logging, game["exe_folder"], bool(on))
        return {"ok": logging is not None, "logging": logging}

    async def helixsr_uninstall_game(self, appid: str) -> dict:
        return await _for_game(appid, HELIXSR.uninstall_game)

    # HelixSR inside OptiScaler (game choice optiscaler+helixsr)

    async def helixsr_opti_status(self, appid: str) -> dict:
        try:
            target = await _opti_target(_valid_appid(appid))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if not target:
            return {"ok": True, "patched": False, "installed": False}
        tag = await asyncio.to_thread(HELIXSR.opti_release)
        return {**await asyncio.to_thread(helix_opti.status, target), "patched": True, "active": tag,
                "needs": None if tag else OPTI_RELEASE}

    async def helixsr_opti_add(self, appid: str) -> dict:
        try:
            return await _add_helix_to_opti(_valid_appid(appid))
        except Exception as exc:
            decky.logger.exception("helixsr_opti_add")
            return {"ok": False, "error": str(exc)}

    async def helixsr_opti_remove(self, appid: str) -> dict:
        try:
            target = await _opti_target(_valid_appid(appid))
            return await asyncio.to_thread(helix_opti.uninstall, target) if target else {"ok": True, "removed": False}
        except Exception as exc:
            decky.logger.exception("helixsr_opti_remove")
            return {"ok": False, "error": str(exc)}

    # --- FSR4 Injector ---

    async def fsr4_status(self) -> dict:
        return await asyncio.to_thread(FSR4.status)

    async def fsr4_install(self) -> dict:
        """Downloads (or updates to) FSR4 Injector's latest release, then AMD's library; fsr4_status shows progress."""
        return FSR4.start_install()

    async def fsr4_remove(self) -> dict:
        return await asyncio.to_thread(FSR4.remove)

    async def fsr4_game_status(self, appid: str) -> dict:
        try:
            appid = _valid_appid(appid)
            folder = _game_folder(appid)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        watermark = SETTINGS.game_value(appid, "fsr4_watermark", False)
        try:
            return await asyncio.to_thread(FSR4.game_status, int(appid), folder, watermark)
        except Exception as exc:
            decky.logger.exception("fsr4_game_status")
            return {"ok": False, "error": str(exc)}

    async def fsr4_game_on(self, appid: str, current_launch_options: str) -> dict:
        """FSR4 Injector into the game; launch_options are the game's new ones."""
        try:
            appid = _valid_appid(appid)
            folder = _game_folder(appid)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            return await asyncio.to_thread(FSR4.enable, int(appid), folder, current_launch_options or "",
                                           SETTINGS.game_value(appid, "fsr4_watermark", False))
        except Exception as exc:
            decky.logger.exception("fsr4_game_on")
            return {"ok": False, "error": str(exc)}

    async def fsr4_game_off(self, appid: str, current_launch_options: str) -> dict:
        """FSR4 Injector out of the game; launch_options are the game's own again (None when unchanged)."""
        try:
            return await asyncio.to_thread(FSR4.disable, int(_valid_appid(appid)), current_launch_options or "")
        except Exception as exc:
            decky.logger.exception("fsr4_game_off")
            return {"ok": False, "error": str(exc)}

    async def fsr4_watermark(self, appid: str, on: bool, current_launch_options: str) -> dict:
        """AMD's FSR 4 watermark for the game: remembered, and in its launch options when FSR4 Injector is in it."""
        try:
            appid = _valid_appid(appid)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        SETTINGS.set_game_value(appid, "fsr4_watermark", bool(on))
        new = await asyncio.to_thread(FSR4.set_watermark, int(appid), current_launch_options or "", bool(on))
        return {"ok": True, "watermark": bool(on), "launch_options": new}

    async def fsr4_details(self) -> dict:
        """Everything FSR4 Injector's own panel shows (the full view under Backends)."""
        try:
            names = {g["appid"]: g["name"] for g in steam_library.installed_games(HOME)}
            return await asyncio.to_thread(FSR4.details, names)
        except Exception as exc:
            decky.logger.exception("fsr4_details")
            return {"ok": False, "error": str(exc)}

    async def fsr4_compatible_games(self) -> dict:
        """Installed games FSR4 Injector can go in (they ship FSR 3.1 or newer)."""
        try:
            steam = HOME / ".local" / "share" / "Steam"
            return {"ok": True, "games": await asyncio.to_thread(FSR4.compatible, str(steam))}
        except Exception as exc:
            decky.logger.exception("fsr4_compatible_games")
            return {"ok": False, "error": str(exc), "games": []}

    async def fsr4_games(self) -> list[str]:
        """Games FSR4 Injector is in (to take it out of all of them before it's removed)."""
        return (await asyncio.to_thread(FSR4.status))["games"]

    # --- OptiScaler (Decky Framegen) ---

    async def optiscaler_status(self) -> dict:
        status = await OPTISCALER.check_fgmod_path()
        status["job"] = OPTI_JOB.status()
        # an install from an earlier Decky Framegen: the files it needs now aren't all there
        status["legacy"] = not status.get("exists") and backends.optiscaler_status(HOME)["installed"]
        return status

    async def optiscaler_install(self, fsr4_variant: str = "") -> dict:
        """Starts the install; optiscaler_status reports its progress and result."""
        return OPTI_JOB.start(FSR4_VARIANT)

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
        # with OptiScaler + MAKO chosen, MAKO stays and its launcher goes into OptiScaler's launch options
        choice = SETTINGS.game_choice(str(appid))
        keep = choice if "optiscaler" in choice.split("+") else "optiscaler"
        cleared = await _clear_game(str(appid), folder, keep, current_launch_options or "")
        if not cleared["ok"]:
            return {"status": "error", "message": cleared["error"]}
        launch = cleared["launch_options"] if cleared["launch_options"] is not None else current_launch_options or ""
        result = await OPTISCALER.patch_game(str(appid), dll_name, launch, FSR4_VARIANT)
        if result.get("launch_options") and "mako" in keep.split("+") and Path(_mako_runner()).is_file():
            result["launch_options"] = _with_mako(result["launch_options"])
        if result.get("status") == "success" and "mako" in keep.split("+"):
            await _opti_frame_generation_off(str(appid), {})
        if result.get("status") == "success" and {"optiscaler", "helixsr"} <= set(keep.split("+")):
            result["helix_in_opti"] = await _add_helix_to_opti(str(appid))
        return {**result, "removed": cleared["removed"]}

    async def optiscaler_unpatch_game(self, appid: str) -> dict:
        try:
            target = await _opti_target(_valid_appid(appid))
            if target:
                await asyncio.to_thread(helix_opti.uninstall, target)
            result = await OPTISCALER.unpatch_game(_valid_appid(appid))
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        if result.get("status") == "success" and "mako" in SETTINGS.game_choice(str(appid)).split("+") \
                and Path(_mako_runner()).is_file():
            result["launch_options"] = _with_mako(result.get("launch_options") or "")
        return result

    # --- updates ---

    async def check_updates(self) -> dict:
        """What can be updated: this plugin (a new release), and each installed backend (the version this plugin
        brings, or for HelixSR its newest release). Upstream releases of Decky Framegen and MAKO newer than the ones
        vendored here are reported too: they reach the plugin through its own next release."""
        async def guard(work):
            try:
                return await work()
            except Exception as exc:
                decky.logger.warning(f"update check: {exc}")
                return {"error": str(exc)}

        async def plugin():
            return await asyncio.to_thread(updates.self_update, decky.DECKY_PLUGIN_VERSION)

        async def optiscaler():
            installed = backends.optiscaler_status(HOME)["version"]
            bundled = OPTISCALER_ARCHIVE_ASSET["version"]
            up = await asyncio.to_thread(updates.upstream, updates.FRAMEGEN_REPO, updates.FRAMEGEN_VENDORED)
            return {"installed": installed, "available": bundled,
                    "update_available": bool(installed) and installed != bundled, **up}

        async def helixsr():
            await asyncio.to_thread(HELIXSR.releases, True)
            st = await asyncio.to_thread(HELIXSR.status)
            return {"installed": st["active"], "available": (st["latest"] or {}).get("tag"),
                    "update_available": bool(st["active"]) and st["update_available"]}

        async def mako():
            check = await MAKO.check_mako_installed()
            up = await asyncio.to_thread(updates.upstream, updates.MAKO_REPO, updates.MAKO_VENDORED, "plugin-v")
            return {"installed": check.get("installed_engine_version") if check.get("installed") else None,
                    "available": check.get("expected_engine_version"),
                    "update_available": bool(check.get("installed")) and bool(check.get("engine_update_required")),
                    **up}

        async def fsr4injector():
            installed = FSR4.version()
            rel = await asyncio.to_thread(FSR4.latest, True)
            available = rel["version"] if rel else None
            return {"installed": installed, "available": available,
                    "update_available": bool(installed) and updates.newer(available, installed)}

        results = await asyncio.gather(guard(plugin), guard(optiscaler), guard(helixsr), guard(mako),
                                       guard(fsr4injector))
        return dict(zip(("plugin", "optiscaler", "helixsr", "mako", "fsr4injector"), results))

    async def log_error(self, message: str) -> None:
        decky.logger.error(f"frontend: {message}")

    async def _main(self):
        decky.logger.info("DeckyMultiFrameGen loaded")
        try:
            await MAKO._main()
        except Exception:
            decky.logger.exception("MAKO startup")

    async def _unload(self):
        try:
            await MAKO._unload()
        except Exception:
            decky.logger.exception("MAKO unload")
        decky.logger.info("DeckyMultiFrameGen unloaded")


async def _mako_install_mako():
    try:
        await asyncio.to_thread(mako_payload.ensure_renderer)
    except Exception as exc:
        decky.logger.exception("MAKO Renderer download")
        return {"success": False, "error": str(exc), "message": ""}
    return await MAKO.install_mako()


async def _mako_install_flatpak_extension(version: str):
    try:
        await asyncio.to_thread(mako_payload.ensure_flatpaks)
    except Exception as exc:
        decky.logger.exception("MAKO Flatpak download")
        return {"success": False, "error": str(exc)}
    return await MAKO.install_flatpak_extension(version)


# The frontend calls MAKO's methods as mako_<name> (src/mako/api/makoApi.ts), so they can't collide with ours.
# Two of them first download the MAKO Renderer files they install.
_MAKO_OVERRIDES = {"install_mako": _mako_install_mako, "install_flatpak_extension": _mako_install_flatpak_extension}


def _mako_method(name):
    target = _MAKO_OVERRIDES.get(name) or getattr(MAKO, name)

    async def call(self, *args, **kwargs):
        return await target(*args, **kwargs)

    call.__name__ = f"mako_{name}"
    return call


for _name, _method in inspect.getmembers(MakoPlugin, inspect.iscoroutinefunction):
    if not _name.startswith("_"):
        setattr(Plugin, f"mako_{_name}", _mako_method(_name))
