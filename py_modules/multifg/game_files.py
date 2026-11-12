"""Which upscalers a game ships, read from its files, and which Use choices can work with them.

The game's own files count, not ones a backend put there: in a folder OptiScaler is patched into, its support files
(libxess.dll, amd_fidelityfx_dx12.dll, ...) are the game's only when the game's copy was kept aside as <name>.b, and
HelixSR keeps the game's FSR DLL as <name>.original.dll or in HelixSR-Scaler-backup/.
"""

import os
import re
import subprocess

from . import optiscaler as opti

UPSCALERS = {
    # FSR 3.1+ through AMD's FidelityFX API: the DLL FSR4 Injector goes next to (DirectX 12 only)
    "fsr31": ("FSR 3.1+ (DirectX 12)", ("amd_fidelityfx_dx12.dll", "amd_fidelityfx_upscaler_dx12.dll",
                           "amd_fidelityfx_loader_dx12.dll")),
    "fsr31_vk": ("FSR 3.1 (Vulkan)", ("amd_fidelityfx_vk.dll",)),
    "fsr2": ("FSR 2 / 3.0", ("ffx_fsr2_api_dx12_x64.dll", "ffx_fsr2_api_x64.dll", "ffx_fsr2_api_vk_x64.dll",
                             "ffx_fsr3upscaler_x64.dll", "ffx_fsr3_x64.dll")),
    "dlss": ("DLSS", ("nvngx_dlss.dll",)),
    "xess": ("XeSS", ("libxess.dll",)),
    # DLSS frame generation (Streamline's plugin, NVIDIA's DLL): what ANR FG takes the place of
    "dlssg": ("DLSS frame generation", ("nvngx_dlssg.dll", "sl.dlss_g.dll")),
}
MAX_DEPTH = 8   # Unreal games keep plugin DLLs deep (Engine/Plugins/.../Binaries/ThirdParty/Win64); FSR4 Injector uses it too
SCALER_BACKUP = "HelixSR-Scaler-backup"
_OPTI_COPIES = {n.lower() for n in opti.SUPPORT_FILES}
_NAMES = {name: key for key, (_, names) in UPSCALERS.items() for name in names}

# What a choice needs from the game (any one of the listed upscalers); choices not listed work without (OptiScaler
# hooks the game itself, MAKO works on the game's output).
NEEDS = {
    "fsr4injector": ("fsr31",),
    "helixsr": ("fsr31", "fsr2", "dlss", "xess"),   # HelixSR replaces or bridges one of them (DirectX 12)
    "optiscaler+helixsr": ("fsr31", "fsr2", "dlss", "xess"),   # OptiScaler hands HelixSR the game's upscaler input
    "anrfg": ("dlssg",),   # ANR FG runs when the game turns on DLSS frame generation
}


def detect(install_dir: str) -> set[str] | None:
    """The upscalers the game ships (keys of UPSCALERS), or None when its folder can't be read."""
    if not install_dir or not os.path.isdir(install_dir):
        return None
    found: set[str] = set()
    base_depth = install_dir.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(install_dir):
        lower = {f.lower() for f in files}
        patched = opti.MARKER_FILENAME.lower() in lower or "optiscaler.ini" in lower
        for name in lower:
            own = name
            if name.endswith(".b"):
                own = name[:-2]
            elif name.endswith(".original.dll"):
                own = name[: -len(".original.dll")] + ".dll"
            elif patched and name in _OPTI_COPIES and f"{name}.b" not in lower:
                continue   # OptiScaler's copy, not the game's
            if own in _NAMES:
                found.add(_NAMES[own])
        if os.path.basename(root) == SCALER_BACKUP:
            dirs[:] = []
        elif os.path.basename(root) == "OptiScaler" and "custom" in dirs:
            dirs.remove("custom")   # ANR FG's nvngx_dlssg.dll (OptiScaler/custom/<provider>/dlssg), not the game's
        if root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
    return found


LISTED = {*_NAMES, "amdxc64.dll", "amdxcffx64.dll", "nvngx.dll", "dxgi.dll", "winmm.dll", "version.dll",
          "helixsr.dll", "optiscaler.ini"}


def listing(install_dir: str, limit: int = 40) -> list[str] | None:
    """The game's .exe files and upscaler-related files (with backups), relative to its folder: shown in the panel so
    where a game keeps them can be seen on the Deck. None when its folder can't be read."""
    if not install_dir or not os.path.isdir(install_dir):
        return None
    out: list[str] = []
    base_depth = install_dir.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(install_dir):
        dirs.sort()
        for f in sorted(files):
            name = f.lower()
            own = name[:-2] if name.endswith(".b") else name.replace(".original.dll", ".dll")
            if (name.endswith(".exe") and "crash" not in name) or own in LISTED:
                out.append(os.path.relpath(os.path.join(root, f), install_dir))
        if os.path.basename(root) == SCALER_BACKUP or root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
        if len(out) >= limit:
            return out[:limit]
    return out


# Choices testing found don't work in a game, whatever its files say (Steam app id -> part -> why); "Show all Use
# options" still offers them
NOT_WORKING = {
    # its FSR 3 option is gone (the game moved on to FSR 4 / DLSS / XeSS), so FSR4 Injector has nothing to upgrade, and
    # with it in, the game's FSR 4 option disappears (seen on the Deck)
    "1091500": {"fsr4injector": "takes away Cyberpunk 2077's FSR 4 option"},
    # non-Steam games (their app id differs per user) by their .exe: Soulframe quits right after OptiScaler (stock 0.9.4
    # too) hooks its input, with any proxy DLL, even when started without its launcher (Martin's Deck, 2026-11-08)
    "soulframe.x64.exe": {"optiscaler": "Soulframe quits as soon as OptiScaler loads",
                          "helixsr": "Soulframe quits as soon as HelixSR Scaler (an OptiScaler build) loads",
                          "fsr4injector": "Soulframe has no FSR 3.1 DLL"},
}

# HelixSR ways into a game (direct = FSR drop-in, scaler = HelixSR Scaler) that testing found break it: not offered
NO_HELIX_WAYS = {
    # the drop-in replaces the game's FidelityFX DLL, and the game's FSR 4 option disappears with it (seen on the Deck)
    "1091500": {"direct": "HelixSR's FSR drop-in takes away Cyberpunk 2077's FSR 4 option: use HelixSR Scaler here."},
}


def helix_ways(appid: str, status: dict) -> dict:
    """HelixSR's status for a game without the ways that break it; the automatic way moves to one that's left."""
    banned = NO_HELIX_WAYS.get(str(appid), {})
    if not banned or not status.get("ok"):
        return status
    ways = [w for w in status.get("ways") or [] if w not in banned]
    route = status.get("route")
    if route in banned:
        route = ways[0] if ways else "blocked"
    return {**status, "ways": ways, "route": route, "hidden_ways": banned}


def exe_key(folder: str | None) -> str | None:
    """The NOT_WORKING / GAME_NOTES key of a non-Steam game known by its .exe in its folder, or None."""
    if not folder:
        return None
    try:
        names = {n.lower() for n in os.listdir(folder)}
    except OSError:
        return None
    return next((k for k in NOT_WORKING if not k.isdigit() and k in names), None)


def not_working(appid: str, choice: str, key: str | None = None) -> str | None:
    """Why a choice is known not to work in this game (by app id, or key from exe_key), or None."""
    parts = NOT_WORKING.get(str(appid)) or NOT_WORKING.get(key or "", {})
    return next((why for part, why in parts.items() if part in choice.split("+")), None)


def needs(choice: str) -> tuple[str, ...]:
    """What a choice needs from the game: its most demanding part decides (e.g. fsr4injector+mako needs FSR 3.1+)."""
    if choice.startswith("optiscaler+helixsr"):
        return NEEDS["optiscaler+helixsr"]
    for part in choice.split("+"):
        if part in NEEDS:
            return NEEDS[part]
    return ()


def fits(choice: str, found: set[str] | None) -> bool:
    """Whether a choice can work with what the game ships; unknown (None) never hides anything."""
    want = needs(choice)
    return found is None or not want or bool(found & set(want))


# FSR 4.1.2 Lite through OptiScaler (fsr4lite): OptiScaler needs an upscaler of the game's to take over, and the plugin's
# OptiScaler layout only has the Lite files for DirectX 12 (AMD's amdxcffx64.dll)
LITE_NEEDS = ("fsr31", "fsr2", "dlss", "xess")
# files only a DirectX 12 game ships (the game's own, or kept aside as .b): FidelityFX DX12 DLLs, Agility SDK's core
DX12_FILES = {"amd_fidelityfx_dx12.dll", "amd_fidelityfx_upscaler_dx12.dll", "amd_fidelityfx_loader_dx12.dll",
              "ffx_fsr2_api_dx12_x64.dll", "d3d12core.dll"}
_DX12_NAME = re.compile(rb"d3d12\.dll", re.IGNORECASE)
_dx12_cache: dict[tuple[str, int, float], bool] = {}


def exe_uses_dx12(exe: str | None) -> bool | None:
    """Whether a game .exe names d3d12.dll (imported, delay-loaded or loaded by name); None when it can't be read."""
    if not exe:
        return None
    try:
        st = os.stat(exe)
        key = (exe, st.st_size, st.st_mtime)
        if key not in _dx12_cache:
            import mmap
            with open(exe, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
                _dx12_cache[key] = _DX12_NAME.search(m) is not None
        return _dx12_cache[key]
    except (OSError, ValueError):
        return None


def uses_dx12(install_dir: str, exe: str | None = None) -> bool | None:
    """Whether the game runs DirectX 12: it ships a DX12-only file, else its .exe names d3d12.dll. None: unknown."""
    if not install_dir or not os.path.isdir(install_dir):
        return None
    base_depth = install_dir.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(install_dir):
        for f in files:
            name = f.lower()
            name = name[:-2] if name.endswith(".b") else name.replace(".original.dll", ".dll")
            if name in DX12_FILES:
                return True
        if os.path.basename(root) == SCALER_BACKUP or root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
    return exe_uses_dx12(exe)


def lite_unfit(found: set[str] | None, dx12: bool | None) -> str | None:
    """Why FSR 4.1.2 Lite can't work in a game (from detect and uses_dx12), or None when it can or that's unknown."""
    if found is not None and not found & set(LITE_NEEDS):
        return "needs a game with FSR 2, FSR 3.1, DLSS or XeSS for OptiScaler to take over"
    if dx12 is False:
        return "works in DirectX 12 games only, and this game doesn't use DirectX 12"
    return None


def labels(found: set[str] | None) -> list[str]:
    return [label for key, (label, _) in UPSCALERS.items() if found and key in found]


# Wine/Proton's own processes and Steam's, left out of running_exes
_SYSTEM_EXES = {"steam.exe", "explorer.exe", "services.exe", "winedevice.exe", "plugplay.exe", "rpcss.exe",
                "svchost.exe", "tabtip.exe", "conhost.exe", "start.exe", "wineboot.exe", "winemenubuilder.exe",
                "rundll32.exe", "msiexec.exe", "steamwebhelper.exe", "cmd.exe", "mscorsvw.exe", "xalia.exe"}
_WIN_EXE = re.compile(r"[A-Za-z]:[\\/][^\n\"]*?\.exe\b", re.IGNORECASE)


def running_exes(ps_lines: list[str] | None = None) -> list[str]:
    """The Windows programs running now with their arguments (their paths as Wine sees them, e.g.
    C:\\users\\steamuser\\...\\Game.exe -arg), leaving out Wine's and Steam's own: shown in the panel so a game whose
    .exe isn't in its folder can be found, and what its launcher passes it can be seen (Soulframe)."""
    if ps_lines is None:
        try:
            ps_lines = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True,
                                      check=False, timeout=5).stdout.splitlines()
        except Exception:
            return []
    out: list[str] = []
    for line in ps_lines:
        m = _WIN_EXE.search(line)
        if not m:
            continue
        path = m.group(0).replace("/", "\\")
        low = path.lower()
        name = low.rsplit("\\", 1)[-1]
        if name in _SYSTEM_EXES or "\\windows\\" in low or "\\proton" in low:
            continue
        args = line[m.end():].strip()[:400]
        entry = f"{path} {args}".strip()
        if entry not in out:
            out.append(entry)
    return out[:10]


def exe_path(entry: str) -> str | None:
    """The .exe path of a running_exes entry (without its arguments)."""
    m = _WIN_EXE.search(entry or "")
    return m.group(0) if m else None
