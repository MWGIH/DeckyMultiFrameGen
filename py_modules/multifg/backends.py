"""Detects which frame generation / upscaling backends are installed on this device.

Each backend is looked for where its own upstream plugin installs it, so an install made by
Decky Framegen, HelixSR Manager or MAKO Decky is picked up as-is and nothing is installed twice.
"""

import re
from pathlib import Path

from . import steam_library

OPTISCALER = "optiscaler"
HELIXSR = "helixsr"
MAKO = "mako"

# What a game can use. HelixSR picks its own way per game: the FSR drop-in, or HelixSR Scaler (its OptiScaler build).
GAME_CHOICES = ("none", OPTISCALER, HELIXSR, MAKO)

UPSTREAM = {
    OPTISCALER: {
        "name": "OptiScaler",
        "plugin": "Decky Framegen",
        "repo": "xXJSONDeruloXx/Decky-Framegen",
        "kind": "Upscaling and frame generation (DirectX 12)",
    },
    HELIXSR: {
        "name": "HelixSR",
        "plugin": "HelixSR Manager",
        "repo": "PeroTuncay/DeckyHelixSRManager",
        "kind": "DLSS-style upscaling on AMD GPUs",
    },
    MAKO: {
        "name": "MAKO",
        "plugin": "MAKO Decky",
        "repo": "eugeniosegala/MAKO",
        "kind": "Frame generation, scaling and shaders (Vulkan layer)",
    },
}

# Files Decky Framegen's installer leaves in ~/fgmod; enough of them to tell a finished install apart
_OPTISCALER_REQUIRED = ("OptiScaler.dll", "OptiScaler.ini", "fgmod")
# HelixSR 1.5+ ships nvngx.dll, older releases amd_fidelityfx_dx12.dll
_HELIXSR_DLLS = ("nvngx.dll", "amd_fidelityfx_dx12.dll")
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,40}")


def optiscaler_status(home: Path) -> dict:
    path = home / "fgmod"
    installed = path.is_dir() and all((path / f).exists() for f in _OPTISCALER_REQUIRED)
    version = None
    if installed:
        try:
            version = (path / "version.txt").read_text().strip() or None
        except OSError:
            pass
    return {"installed": installed, "version": version, "path": str(path)}


def helixsr_releases(base: Path) -> list[str]:
    """Release tags downloaded into HelixSR Manager's folder (~/HelixSR/<tag>/), newest first."""
    tags = []
    try:
        for d in base.iterdir():
            if d.is_dir() and _TAG.fullmatch(d.name) and any((d / n).exists() for n in _HELIXSR_DLLS):
                tags.append(d.name)
    except OSError:
        pass
    return sorted(tags, key=_version_key, reverse=True)


def _version_key(tag: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", tag)[:4])


def helixsr_status(home: Path) -> dict:
    base = home / "HelixSR"
    tags = helixsr_releases(base)
    return {"installed": bool(tags), "version": tags[0] if tags else None, "path": str(base), "releases": tags}


def mako_status(home: Path) -> dict:
    wrapper = home / ".local" / "bin" / "mako-run"
    lossless = steam_library.is_installed(home, steam_library.LOSSLESS_SCALING_APPID)
    notes = []
    if not lossless:
        notes.append("Lossless Scaling isn't installed in Steam: MAKO's scaler and shaders work, frame generation needs it.")
    return {
        "installed": wrapper.exists(),
        "version": None,
        "path": str(wrapper),
        "lossless_scaling": lossless,
        "notes": notes,
    }


def all_status(home: Path) -> list[dict]:
    checks = {OPTISCALER: optiscaler_status, HELIXSR: helixsr_status, MAKO: mako_status}
    out = []
    for key, check in checks.items():
        try:
            status = check(home)
        except Exception as exc:  # one broken check shouldn't hide the others
            status = {"installed": False, "version": None, "error": str(exc)}
        out.append({"id": key, **UPSTREAM[key], **status})
    return out
