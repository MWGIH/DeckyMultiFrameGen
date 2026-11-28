"""Ultimate ASI Loader (ThirteenAG, MIT) for OptiScaler installed as OptiScaler.asi.

Some games only take OptiScaler when an ASI loader starts it, such as Red Dead Redemption 2 on Vulkan (OptiScaler's
wiki: OptiScaler.asi + Ultimate ASI Loader as dinput8.dll + OptiPatcher). The loader's x64 release is downloaded from
https://github.com/ThirteenAG/Ultimate-ASI-Loader on the device and checked by SHA-256; nothing is re-hosted here.

The loader goes into the game as dinput8.dll only when the game has no dinput8.dll of its own (a mod loader such as
ScriptHookRDR2 V2's already loads .asi files), and only the plugin's copy is ever removed.
"""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from .fsr4overrides import OverridesError, _curl, sha256_file

PROXY = "dinput8.dll"
RELEASE = {
    "version": "v10.0.5",
    "name": "Ultimate-ASI-Loader_x64.zip",
    "url": "https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases/download/v10.0.5/Ultimate-ASI-Loader_x64.zip",
    "sha256": "0da70825976f4b051e45de10adffcea35e952b8ac58bfda4f5b9e4bef1d9ba4b",
    "dll_sha256": "0fe291f24e3a15ea942fab8756e1fa89b4a8860ace1db604cfbfad5401a51e05",
}


class LoaderError(Exception):
    pass


def loader_dll(cache: Path) -> Path:
    """The loader's dinput8.dll in cache, downloaded and checked when missing."""
    cache.mkdir(parents=True, exist_ok=True)
    dll = cache / f"dinput8-{RELEASE['version']}.dll"
    if dll.is_file() and sha256_file(dll) == RELEASE["dll_sha256"]:
        return dll
    archive = cache / RELEASE["name"]
    if not (archive.is_file() and sha256_file(archive) == RELEASE["sha256"]):
        part = archive.with_name(archive.name + ".part")
        try:
            _curl(RELEASE["url"], part, timeout=600)
        except OverridesError as exc:
            raise LoaderError(f"Ultimate ASI Loader: {exc}") from exc
        if sha256_file(part) != RELEASE["sha256"]:
            part.unlink(missing_ok=True)
            raise LoaderError("Ultimate ASI Loader's download doesn't match its checksum")
        part.replace(archive)
    with tempfile.TemporaryDirectory(dir=cache) as tmp, zipfile.ZipFile(archive) as z:
        if PROXY not in z.namelist():
            raise LoaderError(f"{PROXY} missing from {RELEASE['name']}")
        z.extract(PROXY, tmp)
        found = Path(tmp) / PROXY
        if sha256_file(found) != RELEASE["dll_sha256"]:
            raise LoaderError(f"{PROXY} in {RELEASE['name']} doesn't match its checksum")
        shutil.move(str(found), dll)
    return dll


def is_ours(path: Path) -> bool:
    try:
        return path.is_file() and sha256_file(path) == RELEASE["dll_sha256"]
    except OSError:
        return False


def install(directory: Path, cache: Path) -> str:
    """The loader into directory as dinput8.dll. Returns "installed", "kept" (already ours) or "game" (the game
    has a dinput8.dll of its own, left in place and expected to load .asi files)."""
    dest = Path(directory) / PROXY
    if dest.exists():
        return "kept" if is_ours(dest) else "game"
    shutil.copy2(loader_dll(cache), dest)
    return "installed"


def remove(directory: Path) -> bool:
    """The plugin's loader out of directory (never a dinput8.dll the game or a mod put there)."""
    dest = Path(directory) / PROXY
    if is_ours(dest):
        dest.unlink()
        return True
    return False
