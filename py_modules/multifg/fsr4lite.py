"""FSR 4.1.2 Lite for OptiScaler: AMD's FSR 4.1.2 library with OptiScaler told to run its INT8 Lite model, the small
model AMD made for handheld chips (the Steam Deck's Van Gogh is one of the GPUs AMD's own library picks it for).

Nothing here is re-hosted. The two pieces come from their makers:
- AMD's amdxcffx64.dll (FSR 4.1.2, FidelityFX 2.4.0.4370) is cut out of AMD's own Adrenalin 26.10.1 installer on
  drivers.amd.com: only the ~43 MB packed range holding it is downloaded, decoded and kept when its SHA-256 matches.
  This is FSR4 Injector's method (github.com/Rayekkk/FSR4Injector, BSD-3-Clause, fsr4_dll.py), and its recipe. When
  FSR4 Injector already fetched the file, that copy is used. Using AMD's file means accepting AMD's EULA.
- OptiScaler.dll comes from OptiScaler's official nightly releases (github.com/optiscaler/OptiScaler-nightly, GPL-3.0):
  older builds can't pick the Lite model (Fsr4GpuSupport/Fsr4Model). A known nightly is pinned with its SHA-256;
  nightlies are deleted after about three months, so when it's gone the newest nightly is used.

prepare() puts both into ~/fgmod/fsr4-lite-412/ (wiped by an OptiScaler reinstall, so it is redone before patching);
the downloads are kept in the runtime folder so that costs nothing.
"""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import updates

VARIANT = "deck-lite-412"
DIR_NAME = "fsr4-lite-412"

AMD_DLL = {
    "name": "amdxcffx64.dll",
    "driver": "Adrenalin 26.10.1",
    "fsr": "4.1.2",
    "url": "https://drivers.amd.com/drivers/whql-amd-software-adrenalin-edition-26.10.1-win11-c.exe",
    "referer": "https://www.amd.com/",
    "packed_offset": 857273233,  # an LZMA2 dictionary-reset chunk in the installer's 7z, absolute file offset
    "packed_size": 44843008,  # bytes from that chunk until the DLL is decoded completely
    "packed_sha256": "820aeb5ad7e077e5a380551d9e604d0cae413c08c3576fa9002dfedf33b84be7",
    "unpacked_offset": 1610612736,  # the chunk's position in the block's decoded stream (the BCJ filter needs it)
    "dict_size": 2 ** 24,
    "dll_offset": 124861144,  # where the DLL starts, counted from the chunk
    "dll_size": 85684104,
    "sha256": "c33a287f3048bf02311cae430b6a977500b94ca7b315cd7bff751e6b03e483e3",
}
EULA_URL = "https://www.amd.com/en/legal/eula/amd-software-eula.html"

NIGHTLY_REPO = "optiscaler/OptiScaler-nightly"
NIGHTLY = {
    "tag": "nightly-20261108",
    "name": "OptiScaler_v10.0.0-pre1_20261108.7z",
    "url": "https://github.com/optiscaler/OptiScaler-nightly/releases/download/nightly-20261108/"
           "OptiScaler_v10.0.0-pre1_20261108.7z",
    "size": 72359584,
    "sha256": "e068504b84c892507602688bba357f7f66fad6a43c661ad60c15bb4947ac6417",
}
_NIGHTLY_NAME = re.compile(r"^OptiScaler_[^/]*\.7z$", re.I)

# What OptiScaler.ini gets for Lite: FSR 4 support forced to INT8 Lite and the Lite model picked (Proton doesn't let
# OptiScaler read the GPU's family, so it can't tell by itself), the Valve 4.1.1 build's settings switched back off
CONFIG = {
    "FSR.Fsr4GpuSupport": "4",
    "FSR.Fsr4Model": "3",
    "FSR.Fsr4ForceModel": "auto",
    "Plugins.LoadCustomAmdxc64OnRdna2": "false",
}

USER_AGENT = "Mozilla/5.0"
CHUNK = 1 << 20


class LiteError(Exception):
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


def amd_dll_valid(path: Path) -> bool:
    return _valid(path, AMD_DLL["dll_size"], AMD_DLL["sha256"])


def _curl(url: str, dest: Path, extra: list[str], timeout: int = 1800) -> None:
    result = subprocess.run(["curl", "-fL", "--retry", "3", "-A", USER_AGENT, *extra, "-o", str(dest), url],
                            capture_output=True, text=True, env=_env(), timeout=timeout)
    if result.returncode != 0:
        dest.unlink(missing_ok=True)
        raise LiteError(f"Download failed: {(result.stderr or '').strip()[-200:]}")


def decode_amd_dll(packed: Path, dest: Path, recipe: dict = AMD_DLL) -> None:
    """The DLL decoded out of the packed range into dest; dest only appears when its SHA-256 matches."""
    try:
        import lzma
    except ImportError as exc:
        raise LiteError("This Decky Loader's Python has no lzma module, so AMD's file can't be decoded") from exc
    decoder = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[
        {"id": lzma.FILTER_X86, "start_offset": recipe["unpacked_offset"] % 2 ** 32},
        {"id": lzma.FILTER_LZMA2, "dict_size": recipe["dict_size"]},
    ])
    skip, size, got, digest = recipe["dll_offset"], recipe["dll_size"], 0, hashlib.sha256()
    tmp = dest.with_name(dest.name + ".part")
    try:
        with open(packed, "rb") as src, open(tmp, "wb") as out:
            while got < size:
                chunk = src.read(CHUNK)
                if not chunk:
                    raise LiteError("AMD's download ended before the file was complete")
                try:
                    data = decoder.decompress(chunk)
                except lzma.LZMAError as exc:
                    raise LiteError("AMD's installer doesn't match what was expected") from exc
                if skip:
                    cut = min(skip, len(data))
                    skip -= cut
                    data = data[cut:]
                data = data[:size - got]
                got += len(data)
                digest.update(data)
                out.write(data)
        if digest.hexdigest() != recipe["sha256"]:
            raise LiteError("AMD's file doesn't match its checksum (AMD changed the installer)")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)


def fetch_amd_dll(dest: Path, reuse: Path | None = None) -> str:
    """AMD's FSR 4.1.2 DLL at dest: kept if already right, copied from reuse (FSR4 Injector's copy) when that one is
    right, otherwise fetched from AMD. Returns where it came from."""
    if amd_dll_valid(dest):
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if reuse and amd_dll_valid(reuse):
        tmp = dest.with_name(dest.name + ".part")
        shutil.copyfile(reuse, tmp)
        tmp.replace(dest)
        return "fsr4injector"
    first, size = AMD_DLL["packed_offset"], AMD_DLL["packed_size"]
    packed = dest.with_name(dest.name + ".packed")
    try:
        _curl(AMD_DLL["url"], packed, ["-r", f"{first}-{first + size - 1}", "-e", AMD_DLL["referer"]])
        if packed.stat().st_size != size or sha256_file(packed) != AMD_DLL["packed_sha256"]:
            raise LiteError("AMD's download doesn't match its checksum (AMD changed the installer)")
        decode_amd_dll(packed, dest)
    finally:
        packed.unlink(missing_ok=True)
    return "amd"


def _newest_nightly() -> dict:
    """The newest OptiScaler nightly's archive: {tag, name, url, sha256 (from GitHub's page, may be None)}."""
    for rel in updates.release_list(NIGHTLY_REPO):
        for asset in updates.release_assets(NIGHTLY_REPO, rel["tag"]):
            if _NIGHTLY_NAME.match(asset["name"]):
                digest = asset.get("digest") or ""
                return {"tag": rel["tag"], "name": asset["name"], "url": asset["browser_download_url"],
                        "sha256": digest.removeprefix("sha256:") or None}
    raise LiteError("No OptiScaler nightly found on GitHub")


def fetch_nightly(cache: Path) -> Path:
    """The OptiScaler nightly archive in cache: the pinned one, or the newest when the pinned one is gone."""
    cache.mkdir(parents=True, exist_ok=True)
    pinned = cache / NIGHTLY["name"]
    if _valid(pinned, NIGHTLY["size"], NIGHTLY["sha256"]):
        return pinned
    part = pinned.with_name(pinned.name + ".part")
    try:
        _curl(NIGHTLY["url"], part, [])
        if sha256_file(part) == NIGHTLY["sha256"]:
            part.replace(pinned)
            return pinned
    except LiteError:
        pass
    part.unlink(missing_ok=True)
    newest = _newest_nightly()
    archive = cache / newest["name"]
    if archive.is_file() and (not newest["sha256"] or sha256_file(archive) == newest["sha256"]):
        return archive
    part = archive.with_name(archive.name + ".part")
    _curl(newest["url"], part, [])
    if newest["sha256"] and sha256_file(part) != newest["sha256"]:
        part.unlink(missing_ok=True)
        raise LiteError(f"{newest['name']} doesn't match GitHub's checksum")
    part.replace(archive)
    return archive


def extract_optiscaler_dll(archive: Path, dest: Path) -> None:
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        result = subprocess.run(["7z", "e", "-y", f"-o{tmp}", str(archive), "OptiScaler.dll"],
                                capture_output=True, text=True, env={**_env(), "LD_LIBRARY_PATH": ""})
        found = Path(tmp) / "OptiScaler.dll"
        if result.returncode != 0 or not found.is_file():
            raise LiteError(f"Couldn't unpack OptiScaler.dll from {archive.name}: "
                            f"{(result.stderr or result.stdout or '').strip()[-200:]}")
        found.replace(dest)


def prepared(fgmod: Path) -> bool:
    folder = fgmod / DIR_NAME
    return (folder / "OptiScaler.dll").is_file() and (folder / "renames").is_dir() \
        and amd_dll_valid(folder / AMD_DLL["name"]) and (folder / "amd_fidelityfx_upscaler_dx12.dll").is_file()


def prepare(fgmod: Path, cache: Path, native_upscaler: Path, make_renames, reuse_amd: Path | None = None) -> dict:
    """~/fgmod/fsr4-lite-412 with OptiScaler.dll (+ its renamed copies, made by make_renames(src, dir)), AMD's
    amdxcffx64.dll and the FidelityFX upscaler the other Deck build uses. Returns {amd_source, optiscaler}."""
    if not native_upscaler.is_file():
        raise LiteError("OptiScaler isn't fully installed: reinstall it in Backends")
    cache.mkdir(parents=True, exist_ok=True)
    amd_source = fetch_amd_dll(cache / AMD_DLL["name"], reuse_amd)
    archive = fetch_nightly(cache)
    folder = fgmod / DIR_NAME
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    try:
        extract_optiscaler_dll(archive, folder / "OptiScaler.dll")
        if not make_renames(folder / "OptiScaler.dll", folder / "renames"):
            raise LiteError("Couldn't prepare OptiScaler's proxy DLL copies")
        shutil.copy2(cache / AMD_DLL["name"], folder / AMD_DLL["name"])
        shutil.copy2(native_upscaler, folder / "amd_fidelityfx_upscaler_dx12.dll")
        (folder / "source.txt").write_text(f"OptiScaler {archive.name}\nAMD FSR {AMD_DLL['fsr']} from "
                                           f"{AMD_DLL['driver']}\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return {"amd_source": amd_source, "optiscaler": archive.name}
