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
import zipfile
from pathlib import Path

CHUNK = 1 << 20
USER_AGENT = "Mozilla/5.0"
UPSCALER = "amd_fidelityfx_upscaler_dx12.dll"

# Steam Deck / RDNA2 iGPU archive (dll-2026-11-05). The .zip is used so extraction needs no 7z.
RELEASE = {
    "tag": "dll-2026-11-05",
    "name": "fsr4.1.2-igpu-cyboman-rdna2-2026-11-05.zip",
    "url": (
        "https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download/"
        "dll-2026-11-05/fsr4.1.2-igpu-cyboman-rdna2-2026-11-05.zip"
    ),
    "sha256": "2e5777b1190c59710da7224468142eb1734a8e9daf2b77b7b6d410441054e293",
    "project": "https://github.com/zgauthier2000/fsr4-shader-performance-overrides",
}

# folder inside the archive -> OptiScaler variant id, UI key, label, whether it is a Lite network
VARIANTS = {
    "exact": {
        "id": "cyboman-exact",
        "files": "exact",
        "label": "FSR 4.1.2 Exact (Cyboman)",
        "dir_name": "fsr4-cyboman-exact",
        "sha256": "1312fdca3bb13f0e66a0c3678151d61d3e1f8c6b9f1d80a805254f4e00db3c69",
        "size": 44400640,
        "lite": False,
        "hint": (
            "Cyboman's exact FSR 4.1.2 build for Steam Deck / RDNA2 iGPUs: AMD's picture byte for byte, "
            "faster shaders. From fsr4-shader-performance-overrides. Single-player only."
        ),
    },
    "lossy": {
        "id": "cyboman-lossy",
        "files": "lossy",
        "label": "FSR 4.1.2 Lossy (Cyboman)",
        "dir_name": "fsr4-cyboman-lossy",
        "sha256": "d34dd6c9841e290ccb29f4cc129a3b6fd3ba5a9d3c5a0379119311bdf66534ff",
        "size": 56302080,
        "lite": False,
        "hint": (
            "Cyboman's lossy FSR 4.1.2 build for Steam Deck / RDNA2 iGPUs: faster than Exact by skipping "
            "the network on some frames; picture is close to AMD's, not identical. Single-player only."
        ),
    },
    "lite-exact": {
        "id": "cyboman-lite-exact",
        "files": "lite-exact",
        "label": "FSR 4.1.2 Lite Exact (Cyboman)",
        "dir_name": "fsr4-cyboman-lite-exact",
        "archive_folder": "4.1.2l-exact",
        "sha256": "f991d06a8b800ed3e01b95696333c842c3de590aec7d2e6b2340c4e583d84ef4",
        "size": 39608832,
        "lite": True,
        "hint": (
            "Cyboman's exact FSR 4.1.2 Lite build for Steam Deck / RDNA2 iGPUs: AMD Lite's picture byte for "
            "byte, a little faster. Single-player only."
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
    """The igpu-rdna2 release zip in cache, downloaded and SHA-256 checked when missing."""
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
    """One variant's amd_fidelityfx_upscaler_dx12.dll from the zip into dest."""
    member = f"{folder_name}/{UPSCALER}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        with zipfile.ZipFile(archive) as zf:
            try:
                info = zf.getinfo(member)
            except KeyError as exc:
                raise OverridesError(f"{RELEASE['name']} has no {member}") from exc
            with zf.open(info) as src, open(tmp, "wb") as out:
                shutil.copyfileobj(src, out, CHUNK)
        if tmp.stat().st_size != size or sha256_file(tmp) != sha256:
            raise OverridesError(f"{member} doesn't match its checksum")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)


_ARCHIVE_FOLDER = {
    "exact": "exact",
    "lossy": "lossy",
    "lite-exact": "4.1.2l-exact",
    "lite-lossy": "4.1.2l-lossy",
}


def dll_path(cache: Path, files_key: str) -> Path:
    """Cached upscaler DLL for a UI files key (exact / lossy / lite-exact / lite-lossy)."""
    variant = BY_FILES[files_key]
    folder = _ARCHIVE_FOLDER[files_key]
    dest = cache / folder / UPSCALER
    if _valid(dest, variant["size"], variant["sha256"]):
        return dest
    archive = fetch_archive(cache)
    extract_upscaler(archive, folder, dest, variant["sha256"], variant["size"])
    return dest


def prepared(fgmod: Path, variant_id: str) -> bool:
    info = BY_ID[variant_id]
    folder = fgmod / info["dir_name"]
    return _valid(folder / UPSCALER, info["size"], info["sha256"])


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
    upscaler = dll_path(cache, files_key)
    folder = fgmod / info["dir_name"]
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    try:
        # OptiScaler.dll (+ renames) and amdxcffx64 / amdxc64 when the base has them
        for name in ("OptiScaler.dll", "amdxcffx64.dll", "amdxc64.dll"):
            src = base_dir / name
            if src.is_file():
                shutil.copy2(src, folder / name)
        renames_src = base_dir / "renames"
        if (folder / "OptiScaler.dll").is_file():
            if renames_src.is_dir():
                shutil.copytree(renames_src, folder / "renames")
            elif not make_renames(folder / "OptiScaler.dll", folder / "renames"):
                raise OverridesError("Couldn't prepare OptiScaler's proxy DLL copies")
        shutil.copy2(upscaler, folder / UPSCALER)
        (folder / "source.txt").write_text(
            f"{info['label']}\n{RELEASE['project']}/releases/tag/{RELEASE['tag']}\n"
            f"{RELEASE['name']} / {info.get('archive_folder', files_key)}\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder
