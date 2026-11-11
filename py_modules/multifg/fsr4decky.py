"""DeckyUpscaler (doodlum) "shipped" FSR 4.1.2 Lite assets from the FSR4 timing kit.

The DeckyUpscaler GitHub repo is not public; its author allowed the timing kit to ship the
v0.2.1 drop-in (unmodified AMD Vulkan FSR 4 Lite DLL + shader packs). This module fetches that
folder from the Linux timing-kit release and stages it for OptiScaler.

DeckyUpscaler's speedup comes from SPIR-V shader packs on the Vulkan FSR path under Proton.
OptiScaler's usual path is DirectX 12, so this variant still prepares the AMD Lite OptiScaler
stack (nightly + amdxcffx64) for DX12, and also deploys the Decky Vulkan upscaler and shader
packs next to the game for the Vulkan path.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from . import fsr4lite

CHUNK = 1 << 20
USER_AGENT = "Mozilla/5.0"

VARIANT = "decky-steamdeck"
DIR_NAME = "fsr4-decky-steamdeck"
FILES_KEY = "decky"
LABEL = "Decky (Steamdeck Optimised)"

KIT = {
    "tag": "timing-kit-2026-11-11",
    "name": "fsr4-timing-kit-linux-2026-11-11.tar.gz",
    "url": (
        "https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download/"
        "timing-kit-2026-11-11/fsr4-timing-kit-linux-2026-11-11.tar.gz"
    ),
    "sha256": "3a840985e50cec005734996c4acb9f3cf702efaa18923a7ce1283ccb6f6dec92",
    "project": "https://github.com/zgauthier2000/fsr4-shader-performance-overrides",
    "folder": "fsr4-timing-kit-linux/deckyupscaler",
}

# Files taken from deckyupscaler/ in the timing kit (du-shipped).
ASSETS = {
    "amd_fidelityfx_upscaler_vk.dll": {
        "dest": "amd_fidelityfx_vk.dll",  # OptiScaler's Vulkan FidelityFX name
        "sha256": "4a7e895af6e0b615d40a84d59eb8c2b1054ad91cdd0c739567940270d51bdab7",
        "size": 36135696,
    },
    "fsr4_shaders.bin": {
        "dest": "fsr4_shaders.bin",
        "sha256": "1d9ac843ca253ce044568b28d19fc233eddbfe05a389bed7017560df8962dad8",
        "size": 994084,
    },
    "fsr4_shaders_dot2.bin": {
        "dest": "fsr4_shaders_dot2.bin",
        "sha256": "f72b73b0b7a9bfbd8cf1ee779bb922d64a50befe4fbb22986f663a1b0d3c00b1",
        "size": 347436,
    },
}

HINT = (
    "DeckyUpscaler's Steam Deck-optimised FSR 4.1.2 Lite (timing-kit du-shipped). "
    "Deploys its Vulkan upscaler and shader packs; DirectX 12 still uses AMD Lite through OptiScaler. "
    "Up to ~28% faster than stock Lite at Deck resolutions in the timing kit. Single-player only."
)


class DeckyError(Exception):
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
        raise DeckyError(f"Download failed: {(result.stderr or '').strip()[-200:]}")


def fetch_kit(cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / KIT["name"]
    if archive.is_file() and sha256_file(archive) == KIT["sha256"]:
        return archive
    part = archive.with_name(archive.name + ".part")
    _curl(KIT["url"], part)
    if sha256_file(part) != KIT["sha256"]:
        part.unlink(missing_ok=True)
        raise DeckyError(f"{KIT['name']} doesn't match its checksum")
    part.replace(archive)
    return archive


def extract_assets(cache: Path) -> Path:
    """Extract deckyupscaler/ assets into cache/deckyupscaler/, returning that folder."""
    out = cache / "deckyupscaler"
    if out.is_dir() and all(
        _valid(out / meta["dest"], meta["size"], meta["sha256"]) for meta in ASSETS.values()
    ):
        return out

    archive = fetch_kit(cache)
    out.mkdir(parents=True, exist_ok=True)
    prefix = KIT["folder"].rstrip("/") + "/"
    with tarfile.open(archive, "r:gz") as tar:
        for src, meta in ASSETS.items():
            member_name = prefix + src
            try:
                member = tar.getmember(member_name)
            except KeyError as exc:
                raise DeckyError(f"{KIT['name']} has no {member_name}") from exc
            dest = out / meta["dest"]
            tmp = dest.with_name(dest.name + ".part")
            extracted = tar.extractfile(member)
            if extracted is None:
                raise DeckyError(f"Couldn't read {member_name}")
            with extracted, open(tmp, "wb") as fh:
                shutil.copyfileobj(extracted, fh, CHUNK)
            if tmp.stat().st_size != meta["size"] or sha256_file(tmp) != meta["sha256"]:
                tmp.unlink(missing_ok=True)
                raise DeckyError(f"{member_name} doesn't match its checksum")
            tmp.replace(dest)
        for license_name in ("LICENSE", "shaders-LICENSE-AMD.md", "amd_fidelityfx-LICENSE.md"):
            member_name = prefix + license_name
            try:
                member = tar.getmember(member_name)
            except KeyError:
                continue
            dest = out / license_name
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with extracted, open(dest, "wb") as fh:
                shutil.copyfileobj(extracted, fh, CHUNK)
    return out


def prepared(fgmod: Path) -> bool:
    folder = fgmod / DIR_NAME
    if not (folder / "OptiScaler.dll").is_file() or not (folder / "renames").is_dir():
        return False
    if not fsr4lite.amd_dll_valid(folder / fsr4lite.AMD_DLL["name"]):
        return False
    if not (folder / "amd_fidelityfx_upscaler_dx12.dll").is_file():
        return False
    for meta in ASSETS.values():
        if not _valid(folder / meta["dest"], meta["size"], meta["sha256"]):
            return False
    return True


def prepare(fgmod: Path, cache: Path, native_upscaler: Path, make_renames, reuse_amd: Path | None = None) -> dict:
    """~/fgmod/fsr4-decky-steamdeck with Lite OptiScaler files plus DeckyUpscaler Vulkan assets."""
    if not native_upscaler.is_file():
        raise DeckyError("OptiScaler isn't fully installed: reinstall it in Backends")
    assets = extract_assets(cache)
    # Share the fsr4-lite download cache with fsr4lite.prepare when possible
    amd_cache_dir = cache.parent / "fsr4-lite"
    amd_cache_dir.mkdir(parents=True, exist_ok=True)
    amd_source = fsr4lite.fetch_amd_dll(amd_cache_dir / fsr4lite.AMD_DLL["name"], reuse_amd)
    archive = fsr4lite.fetch_nightly(amd_cache_dir)
    folder = fgmod / DIR_NAME
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    try:
        fsr4lite.extract_optiscaler_dll(archive, folder / "OptiScaler.dll")
        if not make_renames(folder / "OptiScaler.dll", folder / "renames"):
            raise DeckyError("Couldn't prepare OptiScaler's proxy DLL copies")
        shutil.copy2(amd_cache_dir / fsr4lite.AMD_DLL["name"], folder / fsr4lite.AMD_DLL["name"])
        shutil.copy2(native_upscaler, folder / "amd_fidelityfx_upscaler_dx12.dll")
        for meta in ASSETS.values():
            shutil.copy2(assets / meta["dest"], folder / meta["dest"])
        for license_name in ("LICENSE", "shaders-LICENSE-AMD.md", "amd_fidelityfx-LICENSE.md"):
            src = assets / license_name
            if src.is_file():
                shutil.copy2(src, folder / license_name)
        (folder / "source.txt").write_text(
            f"{LABEL}\nDeckyUpscaler v0.2.1 shipped set from {KIT['project']}\n"
            f"{KIT['name']} ({KIT['tag']}) / deckyupscaler/\n"
            f"OptiScaler {archive.name}\nAMD FSR {fsr4lite.AMD_DLL['fsr']} from {fsr4lite.AMD_DLL['driver']}\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return {"amd_source": amd_source, "optiscaler": archive.name, "kit": KIT["name"]}
