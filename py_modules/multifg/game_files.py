"""Which upscalers a game ships, read from its files, and which Use choices can work with them.

The game's own files count, not ones a backend put there: in a folder OptiScaler is patched into, its support files
(libxess.dll, amd_fidelityfx_dx12.dll, ...) are the game's only when the game's copy was kept aside as <name>.b, and
HelixSR keeps the game's FSR DLL as <name>.original.dll or in HelixSR-Scaler-backup/.
"""

import os

from . import optiscaler as opti

UPSCALERS = {
    # FSR 3.1+ through AMD's FidelityFX API: the DLL FSR4 Injector goes next to (DirectX 12 only)
    "fsr31": ("FSR 3.1+", ("amd_fidelityfx_dx12.dll", "amd_fidelityfx_upscaler_dx12.dll",
                           "amd_fidelityfx_loader_dx12.dll")),
    "fsr31_vk": ("FSR 3.1 (Vulkan)", ("amd_fidelityfx_vk.dll",)),
    "fsr2": ("FSR 2 / 3.0", ("ffx_fsr2_api_dx12_x64.dll", "ffx_fsr2_api_x64.dll", "ffx_fsr2_api_vk_x64.dll",
                             "ffx_fsr3upscaler_x64.dll", "ffx_fsr3_x64.dll")),
    "dlss": ("DLSS", ("nvngx_dlss.dll",)),
    "xess": ("XeSS", ("libxess.dll",)),
}
MAX_DEPTH = 6
SCALER_BACKUP = "HelixSR-Scaler-backup"
_OPTI_COPIES = {n.lower() for n in opti.SUPPORT_FILES}
_NAMES = {name: key for key, (_, names) in UPSCALERS.items() for name in names}

# What a choice needs from the game (any one of the listed upscalers); choices not listed work without (OptiScaler
# hooks the game itself, MAKO works on the game's output).
NEEDS = {
    "fsr4injector": ("fsr31",),
    "helixsr": ("fsr31", "fsr2", "dlss", "xess"),   # HelixSR replaces or bridges one of them (DirectX 12)
    "optiscaler+helixsr": ("fsr31", "fsr2", "dlss", "xess"),   # OptiScaler hands HelixSR the game's upscaler input
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
        if root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
    return found


# Choices testing found don't work in a game, whatever its files say (Steam app id -> part -> why); "Show all Use
# options" still offers them
NOT_WORKING = {
    # its FSR 3 option is gone (the game moved on to FSR 4 / DLSS / XeSS), so FSR4 Injector has nothing to upgrade
    "1091500": {"fsr4injector": "doesn't work in Cyberpunk 2077"},
}


def not_working(appid: str, choice: str) -> str | None:
    """Why a choice is known not to work in this game, or None."""
    parts = NOT_WORKING.get(str(appid), {})
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


def labels(found: set[str] | None) -> list[str]:
    return [label for key, (label, _) in UPSCALERS.items() if found and key in found]
