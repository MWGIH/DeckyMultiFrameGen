"""Runs HelixSR's own game installer (setup/helixsr_install.py of an official release) for one game folder.

Started as a separate process with HelixSR's Python (or the system's): helixsr_install.py uses only the standard
library. HelixSR's files are imported and called as they are, never changed. Prints one JSON object on the last line.

    helix_bridge.py HELIXSR_FOLDER status GAME_FOLDER
    helix_bridge.py HELIXSR_FOLDER install GAME_FOLDER [direct|scaler]
    helix_bridge.py HELIXSR_FOLDER uninstall GAME_FOLDER
    helix_bridge.py HELIXSR_FOLDER ready
"""
import contextlib
import io
import json
import sys
from pathlib import Path


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
        "scaler_name": (h.scaler_record(g.target) or {}).get("name") if g.scaler_installed and g.target else None,
    }


def main():
    here = Path(sys.argv[1]).resolve()
    cmd = sys.argv[2]
    sys.path.insert(0, str(here / "setup"))
    log = io.StringIO()
    result = {}
    with contextlib.redirect_stdout(log):
        try:
            import helixsr_install as h

            if cmd == "ready":
                result = {"ok": True, "ready": h.network_ready(here), "version": h.version_of(here / h.DLL)}
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
