"""Runs HelixSR's own game installer (setup/helixsr_install.py of an official release) for one game folder.

Started as a separate process with HelixSR's Python (or the system's): helixsr_install.py uses only the standard
library. HelixSR's files are imported and called as they are, never changed. Prints one JSON object on the last line.

    helix_bridge.py HELIXSR_FOLDER status GAME_FOLDER
    helix_bridge.py HELIXSR_FOLDER install GAME_FOLDER [direct|scaler]
    helix_bridge.py HELIXSR_FOLDER uninstall GAME_FOLDER
    helix_bridge.py HELIXSR_FOLDER ready
    helix_bridge.py HELIXSR_FOLDER remove_all [GAME_FOLDER]..   (every game HelixSR's scan finds, plus these)

HelixSR 2.0 on carries its own JSON bridge for its desktop app (setup/helixsr_bridge.py, over helixsr_games.py) and
its setup/helixsr_install.py is only a text front end: for those releases the commands go to that bridge (main20).
"""
import contextlib
import io
import json
import sys
from pathlib import Path


def graphics_api(h, folder):
    """"vulkan" when the game's main .exe (the largest in its folder) links Vulkan and not Direct3D 12, else None.
    HelixSR only works in Direct3D 12 games; a Vulkan game can still ship FSR's DX12 DLL, which HelixSR then offers to
    replace. Games that load Direct3D 12 at run time don't list it, so nothing else is concluded from the imports."""
    try:
        exes = [f for f in Path(folder).iterdir() if f.suffix.lower() == ".exe" and f.is_file()]
    except OSError:
        return None
    if not exes:
        return None
    imports = h.exe_imports(max(exes, key=lambda f: f.stat().st_size))
    return "vulkan" if "vulkan-1.dll" in imports and "d3d12.dll" not in imports else None


def runtime_log(g):
    """The end of helixsr.log, which HelixSR writes while the game runs (next to the game's FSR DLL for the drop-in, in
    the HelixSR folder next to the .exe for HelixSR Scaler); None when HelixSR hasn't run in the game."""
    current = g.current()
    if current == "direct":
        candidates = [Path(t).parent / "helixsr.log" for t in g.fsr_targets]
    elif current == "scaler" and g.target:
        candidates = [Path(g.target) / "HelixSR" / "helixsr.log"]
    else:
        return None
    for log in candidates:
        try:
            text = log.read_text(errors="replace")
            return {"path": str(log), "modified": log.stat().st_mtime, "lines": text.splitlines()[-12:]}
        except OSError:
            continue
    return None


def describe(h, g):
    return {
        "found": True,
        "name": g.name,
        "folder": str(g.folder),
        "route": g.route,              # the way HelixSR's installer picks: direct, scaler, blocked, ...
        "ways": g.ways(),              # the ways this game can get: direct (FSR drop-in), scaler (HelixSR Scaler)
        "current": g.current(),        # the way HelixSR is in the game now, or None
        "installed": g.installed(),
        "label": g.label(),
        "inputs": g.inputs,
        "anticheat": g.anticheat,
        "fsr_targets": [str(t) for t in g.fsr_targets],
        "exe_folder": str(g.target) if g.target else None,
        "graphics": graphics_api(h, g.target) if g.target else None,
        "runtime_log": runtime_log(g),
        "scaler_name": (h.scaler_record(g.target) or {}).get("name") if g.scaler_installed and g.target else None,
    }


# HelixSR 2.0's names for the ways into a game, and this plugin's (from the 1.x installer)
WAY_IN = {"fsr": "direct", "scaler": "scaler"}
WAY_OUT = {"direct": "fsr", "scaler": "scaler"}
IN_GAME = {"scaler": "Select DLSS in the game.", "fsr": "Select AMD FSR in the game."}


def call20(b, here, *args):
    """One command of HelixSR's own bridge; its JSON answer (raises with its error)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        b._messages.clear()
        b.main([str(here), *args])
    r = json.loads(out.getvalue().strip().splitlines()[-1])
    if not r.get("ok"):
        raise SystemExit(r.get("error") or "HelixSR's installer failed")
    return r


def describe20(b, j):
    way = j.get("installed")
    log = None
    # helixsr.log; for HelixSR Scaler also OptiScaler's own log, which is there even when the game stops before
    # HelixSR loads
    candidates = [j.get("log_path")]
    if way == "scaler" and j.get("exe_folder"):
        candidates.append(str(Path(j["exe_folder"]) / "OptiScaler.log"))
    for c in filter(None, candidates):
        p = Path(c)
        try:
            log = {"path": str(p), "modified": p.stat().st_mtime,
                   "lines": p.read_text(errors="replace").splitlines()[-12:]}
            break
        except OSError:
            continue
    graphics = None
    if j.get("exe_folder"):
        with contextlib.suppress(Exception):
            exes = [f for f in Path(j["exe_folder"]).iterdir() if f.suffix.lower() == ".exe" and f.is_file()]
            imports = b.exe_imports(max(exes, key=lambda f: f.stat().st_size)) if exes else set()
            graphics = "vulkan" if "vulkan-1.dll" in imports and "d3d12.dll" not in imports else None
    rec = j.get("recommended")
    if j.get("blocked"):
        label = f"{' / '.join(j.get('inputs') or [])} only: HelixSR Scaler isn't offered in games with anti-cheat"
    elif rec == "scaler":
        label = f"{' / '.join(j.get('inputs') or ['FSR 3.1'])}: HelixSR Scaler (select DLSS in the game)"
    elif rec == "fsr":
        label = "FSR 3.1: FSR drop-in (HelixSR replaces the game's FSR DLL: select AMD FSR in the game)"
    else:
        label = "HelixSR found no upscaler it can take over in this game"
    return {
        "found": True,
        "name": j.get("name"),
        "folder": j.get("folder"),
        "route": WAY_IN.get(rec, "blocked" if j.get("blocked") else None),
        "ways": [WAY_IN[w] for w in j.get("ways", []) if w in WAY_IN],
        "current": WAY_IN.get(way, way),
        "installed": bool(way),
        "label": label,
        "inputs": j.get("inputs", []),
        "anticheat": j.get("anticheat") or [],
        "exe_folder": j.get("exe_folder"),
        "graphics": graphics,
        "runtime_log": log,
        "scaler_name": j.get("scaler_dll"),
        "launch_options_now": j.get("launch_options"),
    }


def main20(here, cmd, args):
    sys.path.insert(0, str(here / "setup"))
    import helixsr_bridge as b

    if cmd == "ready":
        st = call20(b, here, "status")
        return {"ok": True, "ready": bool(st.get("network_ready")), "version": st.get("version")}
    if cmd == "remove_all":
        extra = [x for f in args for x in ("--folder", f)]
        games = call20(b, here, "games", *extra)["games"]
        removed, left = [], []
        for j in games:
            if not j.get("installed"):
                continue
            try:
                call20(b, here, "remove", "--game", j["folder"])
                removed.append(j["name"])
            except SystemExit:
                left.append(j["name"])
        return {"ok": True, "removed": removed, "left": left}
    folder = args[0]
    if cmd == "status":
        try:
            j = call20(b, here, "games", "--folder", folder)
        except SystemExit:
            return {"ok": True, "found": False}
        want = Path(folder).resolve()
        game = next((g for g in j["games"] if Path(g["folder"]).resolve() == want), None)
        return {"ok": True, **(describe20(b, game) if game else {"found": False})}
    if cmd == "install":
        route = args[1] if len(args) > 1 else None
        way = WAY_OUT.get(route, "auto")
        extra = ["--scaler", str(here / "helixsr-scaler")]
        # a way picked in the plugin: the user confirmed it (anti-cheat warning included)
        if way == "scaler":
            extra += ["--anticheat-ok", "yes"]
        j = call20(b, here, "install", "--game", folder, "--way", way, *extra)["game"]
        d = describe20(b, j)
        return {"ok": True, **d, "route": d["current"], "in_game": IN_GAME.get(j.get("installed"), ""),
                "launch_options": j.get("launch_options")}
    if cmd == "uninstall":
        try:
            j = call20(b, here, "remove", "--game", folder)["game"]
        except SystemExit as e:
            if "not installed" in str(e.code):
                return {"ok": True, "installed": False, "current": None}
            raise
        return {"ok": True, **describe20(b, j)}
    return {"ok": False, "error": f"unknown command {cmd}"}


def main():
    here = Path(sys.argv[1]).resolve()
    cmd = sys.argv[2]
    if (here / "setup" / "helixsr_bridge.py").is_file():
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            try:
                result = main20(here, cmd, sys.argv[3:])
            except SystemExit as e:
                result = {"ok": False, "error": str(e.code) if e.code is not None else "stopped"}
            except Exception as e:  # noqa: BLE001 (reported to the plugin, which shows it)
                result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        result["log"] = log.getvalue().splitlines()[-40:]
        print(json.dumps(result))
        return
    sys.path.insert(0, str(here / "setup"))
    log = io.StringIO()
    result = {}
    with contextlib.redirect_stdout(log):
        try:
            import helixsr_install as h

            if cmd == "ready":
                result = {"ok": True, "ready": bool(h.network_ready(here))}
                with contextlib.suppress(Exception):
                    result["version"] = h.version_of(here / h.DLL)
            elif cmd == "remove_all":
                # what helixsr-uninstall does without its questions: HelixSR out of every game, originals put back
                found = h.games([])
                found += h.games_from(sys.argv[3:], found)
                removed = []
                for g in found:
                    if g.installed():
                        h.uninstall_safe(g)
                        removed.append(g.name)
                result = {"ok": True, "removed": removed, "left": [g.name for g in found if g.installed()]}
            else:
                folder = sys.argv[3]
                found = h.games_from([folder])
                g = found[0] if found else None
                if cmd == "status":
                    result = {"ok": True, **(describe(h, g) if g else {"found": False})}
                elif g is None:
                    result = {"ok": False, "error": "HelixSR found no DLSS, XeSS or FSR files in this game"}
                elif cmd == "install":
                    if not h.network_ready(here):
                        raise SystemExit("HelixSR's setup hasn't finished: run it first")
                    route = sys.argv[4] if len(sys.argv) > 4 else None
                    if route:
                        if route not in g.ways():
                            raise SystemExit(f"{g.name} can't use the {h.way(route)}")
                        g.route = route
                    name = h.install(g, here)
                    launch = h.launch_options(name) if g.route == "scaler" and name else None
                    result = {"ok": True, "route": g.route, "in_game": h.in_game(g.route),
                              "launch_options": launch, **describe(h, g)}
                elif cmd == "uninstall":
                    h.uninstall(g)
                    result = {"ok": True, **describe(h, g)}
                else:
                    result = {"ok": False, "error": f"unknown command {cmd}"}
        except SystemExit as e:
            result = {"ok": False, "error": str(e.code) if e.code is not None else "stopped"}
        except Exception as e:  # noqa: BLE001 (reported to the plugin, which shows it)
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    result["log"] = log.getvalue().splitlines()[-40:]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
