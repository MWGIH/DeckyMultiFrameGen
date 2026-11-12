"""FSR 4.1.2 shader-performance overrides (Cyboman) for OptiScaler on the Steam Deck / RDNA2 iGPU.

Downloads the official igpu-rdna2 release archive from
https://github.com/zgauthier2000/fsr4-shader-performance-overrides and stages each folder's
`amd_fidelityfx_upscaler_dx12.dll` into ~/fgmod for OptiScaler to patch into games.

Nothing is re-hosted in this plugin: the archive is fetched on the device and checked by SHA-256.
Never use these in online / anti-cheat games (modified game files).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CHUNK = 1 << 20
USER_AGENT = "Mozilla/5.0"
UPSCALER = "amd_fidelityfx_upscaler_dx12.dll"

# Steam Deck / RDNA2 iGPU archive (dll-2026-11-05). The .7z (about 9 MB) holds the same DLLs as the 100 MB .zip;
# 7z is already needed for OptiScaler's own archives.
RELEASE = {
    "tag": "dll-2026-11-05",
    "name": "fsr4.1.2-igpu-cyboman-rdna2-2026-11-05.7z",
    "url": (
        "https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download/"
        "dll-2026-11-05/fsr4.1.2-igpu-cyboman-rdna2-2026-11-05.7z"
    ),
    "sha256": "da7c7681bffe7ac60a01e859d5b107900d963557793ef67ddcfd03a832e1c03f",
    "project": "https://github.com/zgauthier2000/fsr4-shader-performance-overrides",
}

# The archive's exact builds are left out: on the Steam Deck they're only a few percent faster than the Deck build and
# AMD Lite they match. folder inside the archive -> OptiScaler variant id, UI key, label, whether it is a Lite network
VARIANTS = {
    "lossy": {
        "id": "cyboman-lossy",
        "files": "lossy",
        "archive_folder": "lossy",
        "label": "FSR 4.1.2 Lossy (Cyboman)",
        "dir_name": "fsr4-cyboman-lossy",
        "sha256": "d34dd6c9841e290ccb29f4cc129a3b6fd3ba5a9d3c5a0379119311bdf66534ff",
        "size": 56302080,
        "lite": False,
        "hint": (
            "Cyboman's lossy FSR 4.1.2 build for Steam Deck / RDNA2 iGPUs: about 30% faster on the Deck than the Valve Deck build, by skipping "
            "the network on some frames; picture is close to AMD's, not identical. Single-player only."
        ),
    },
    "lite-lossy": {
        "id": "cyboman-lite-lossy",
        "files": "lite-lossy",
        "label": "FSR 4.1.2 Lite Lossy (Cyboman)",
        "dir_name": "fsr4-cyboman-lite-lossy",
        "archive_folder": "4.1.2l-lossy",
        "sha256": "06b55e8d3a588b15b5ec93d52a306473f5d78cb899b4699f6f63ed9d6f88a71a",
        "size": 51491328,
        "lite": True,
        "hint": (
            "Cyboman's lossy FSR 4.1.2 Lite build for Steam Deck / RDNA2 iGPUs: about 13–22% faster than "
            "AMD Lite; picture is close to Lite's, not identical. Single-player only."
        ),
    },
}

BY_ID = {v["id"]: v for v in VARIANTS.values()}
BY_FILES = {v["files"]: v for v in VARIANTS.values()}


class OverridesError(Exception):
    pass


def _env() -> dict:
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG", "")
    return env


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid(path: Path, size: int, sha256: str) -> bool:
    try:
        return path.is_file() and path.stat().st_size == size and sha256_file(path) == sha256
    except OSError:
        return False


def _curl(url: str, dest: Path, timeout: int = 1800) -> None:
    result = subprocess.run(
        ["curl", "-fL", "--retry", "3", "-A", USER_AGENT, "-o", str(dest), url],
        capture_output=True,
        text=True,
        env=_env(),
        timeout=timeout,
    )
    if result.returncode != 0:
        dest.unlink(missing_ok=True)
        raise OverridesError(f"Download failed: {(result.stderr or '').strip()[-200:]}")


def fetch_archive(cache: Path) -> Path:
    """The igpu-rdna2 release .7z in cache, downloaded and SHA-256 checked when missing."""
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / RELEASE["name"]
    if archive.is_file() and sha256_file(archive) == RELEASE["sha256"]:
        return archive
    part = archive.with_name(archive.name + ".part")
    _curl(RELEASE["url"], part)
    if sha256_file(part) != RELEASE["sha256"]:
        part.unlink(missing_ok=True)
        raise OverridesError(f"{RELEASE['name']} doesn't match its checksum")
    part.replace(archive)
    return archive


def extract_upscaler(archive: Path, folder_name: str, dest: Path, sha256: str, size: int) -> None:
    """One variant's amd_fidelityfx_upscaler_dx12.dll from the .7z into dest."""
    member = f"{folder_name}/{UPSCALER}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        result = subprocess.run(
            ["7z", "x", "-y", f"-o{tmp}", str(archive), member],
            capture_output=True,
            text=True,
            env={**_env(), "LD_LIBRARY_PATH": ""},
        )
        found = Path(tmp) / folder_name / UPSCALER
        if result.returncode != 0 or not found.is_file():
            raise OverridesError(
                f"Couldn't unpack {member} from {RELEASE['name']}: "
                f"{(result.stderr or result.stdout or '').strip()[-200:]}"
            )
        if found.stat().st_size != size or sha256_file(found) != sha256:
            raise OverridesError(f"{member} doesn't match its checksum")
        found.replace(dest)


def _archive_folder(files_key: str) -> str:
    info = BY_FILES[files_key]
    return str(info.get("archive_folder") or files_key)


def dll_path(cache: Path, files_key: str) -> Path:
    """Cached upscaler DLL for a UI files key (lossy / lite-lossy)."""
    variant = BY_FILES[files_key]
    folder = _archive_folder(files_key)
    dest = cache / folder / UPSCALER
    if _valid(dest, variant["size"], variant["sha256"]):
        return dest
    archive = fetch_archive(cache)
    extract_upscaler(archive, folder, dest, variant["sha256"], variant["size"])
    return dest


def prepared(fgmod: Path, variant_id: str) -> bool:
    """True only when the Cyboman folder has the upscaler and the OptiScaler injector/extras it needs."""
    info = BY_ID[variant_id]
    folder = fgmod / info["dir_name"]
    if not _valid(folder / UPSCALER, info["size"], info["sha256"]):
        return False
    if not (folder / "OptiScaler.dll").is_file() or not (folder / "renames").is_dir():
        return False
    if not (folder / "amdxcffx64.dll").is_file():
        return False
    if not info["lite"] and not (folder / "amdxc64.dll").is_file():
        return False
    return True


def prepare_from(
    fgmod: Path,
    cache: Path,
    files_key: str,
    *,
    base_dir: Path,
    make_renames,
) -> Path:
    """Build ~/fgmod/<dir_name> from an already-prepared OptiScaler variant folder (injector + extras),
    swapping in the Cyboman upscaler DLL. Returns the new variant folder."""
    info = BY_FILES[files_key]
    if not base_dir.is_dir():
        raise OverridesError(f"OptiScaler base files missing at {base_dir}: reinstall OptiScaler")
    required = ["OptiScaler.dll", "amdxcffx64.dll"]
    if not info["lite"]:
        required.append("amdxc64.dll")
    missing = [name for name in required if not (base_dir / name).is_file()]
    if missing:
        raise OverridesError(
            f"OptiScaler base files missing {', '.join(missing)} in {base_dir}: reinstall OptiScaler"
        )
    upscaler = dll_path(cache, files_key)
    folder = fgmod / info["dir_name"]
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    try:
        for name in required:
            shutil.copy2(base_dir / name, folder / name)
        renames_src = base_dir / "renames"
        if renames_src.is_dir():
            shutil.copytree(renames_src, folder / "renames")
        elif not make_renames(folder / "OptiScaler.dll", folder / "renames"):
            raise OverridesError("Couldn't prepare OptiScaler's proxy DLL copies")
        shutil.copy2(upscaler, folder / UPSCALER)
        (folder / "source.txt").write_text(
            f"{info['label']}\n{RELEASE['project']}/releases/tag/{RELEASE['tag']}\n"
            f"{RELEASE['name']} / {_archive_folder(files_key)}\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder
