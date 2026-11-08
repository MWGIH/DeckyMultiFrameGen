"""Digital Extremes' games (Soulframe; Warframe has the same launcher) started without their launcher.

Their launcher (Downloaded/Public/Tools/Launcher.exe) deletes every DLL it doesn't know from the game's folder each
time it starts the game, so OptiScaler's and HelixSR Scaler's proxy DLLs never load (Martin's Soulframe, 2026-11-08).
With a backend that puts DLLs into the game, a small wrapper in front of %command% swaps Launcher.exe in the command
Steam runs for the game's own <Game>.x64.exe, with the arguments the launcher gives it. Game updates then need one
start with Use set to Off or MAKO (the launcher downloads them).
"""

import os
import re
import shlex
from pathlib import Path

# what the launcher passed Soulframe.x64.exe on Martin's Deck (2026-11-08), less its -relaunch:<launcher command>
DEFAULT_ARGS = "-windowMode:1 -shaderCache:1 -graphicsDriver:dx11 -gpuPreference:2 -cluster:public -language:en"
WRAPPER_NAME = "multifg-direct"
_WRAPPER = re.compile(r"""(?:'[^']*multifg-direct'|"[^"]*multifg-direct"|\S*multifg-direct)\s+('[^']*'|"[^"]*"|\S+)\s+('[^']*'|"[^"]*"|\S+)\s+""")
_RELAUNCH = re.compile(r"(^|\s)-relaunch:\S*")

SCRIPT = r"""#!/bin/bash
# Written by Decky MultiFrameGen. Starts a Digital Extremes game (Soulframe) without its launcher, which deletes
# DLLs it doesn't know (OptiScaler's, HelixSR Scaler's) from the game's folder before starting it.
# Usage: multifg-direct <Game.x64.exe> <game arguments> <Steam's command, which runs ...\Tools\Launcher.exe>
exe="$1"; game_args="$2"; shift 2
read -r -a extra <<< "$game_args"
cmd=(); swapped=0
for a in "$@"; do
    low="${a,,}"
    if [[ $swapped == 0 && ( "$low" == */tools/launcher.exe || "$low" == *\\tools\\launcher.exe ) && -f "$exe" ]]; then
        cmd+=("$exe" "${extra[@]}")
        swapped=1
    else
        cmd+=("$a")
    fi
done
[[ $swapped == 1 ]] && cd "$(dirname "$exe")"
exec "${cmd[@]}"
"""


def launcher_shortcut(sc: dict | None) -> bool:
    """Whether a non-Steam shortcut starts a Digital Extremes launcher (...Downloaded/Public/Tools/Launcher.exe)."""
    if not sc:
        return False
    parts = [p.lower() for p in Path(sc.get("exe") or "").parts]
    return parts[-4:] == ["downloaded", "public", "tools", "launcher.exe"]


def game_exe(folder: str) -> str | None:
    """The game's <Game>.x64.exe in its Public folder."""
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".x64.exe"))
    except OSError:
        return None
    return os.path.join(folder, names[0]) if names else None


def args_from_running(entry: str) -> str:
    """A running game's arguments (from game_files.running_exes) without -relaunch: (the launcher's own command)."""
    m = re.search(r"\.x64\.exe\b", entry, re.IGNORECASE)
    rest = entry[m.end():] if m else ""
    return re.sub(r"\s+", " ", _RELAUNCH.sub(" ", rest)).strip()


def write_wrapper(home: Path) -> Path:
    path = home / ".local" / "bin" / WRAPPER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_text() != SCRIPT:
        path.write_text(SCRIPT)
    path.chmod(0o755)
    return path


def has_wrapper(options: str) -> bool:
    return bool(_WRAPPER.search((options or "") + " "))


def without_wrapper(options: str) -> str:
    rest = _WRAPPER.sub("", (options or "") + " ").strip()
    if rest == "%command%":
        return ""
    return rest[len("%command% "):] if rest.startswith("%command% ") and "%command%" not in rest[10:] else rest


def with_wrapper(options: str, wrapper: Path, exe: str, args: str) -> str:
    base = without_wrapper(options)
    w = f"{shlex.quote(str(wrapper))} {shlex.quote(exe)} {shlex.quote(args or DEFAULT_ARGS)}"
    if "%command%" in base:
        return base.replace("%command%", f"{w} %command%", 1)
    return f"{w} %command% {base}".strip()
