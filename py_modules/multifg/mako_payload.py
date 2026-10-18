"""MAKO Renderer's release assets, downloaded from MAKO's GitHub releases at run time instead of shipping inside this
plugin (MAKO Decky's own release ZIP bundles them in bin/). The vendored mako_plugin reads them from PAYLOAD_ROOT/bin."""
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

import decky

from mako_plugin.constants import BIN_DIR, FLATPAK_RUNTIME_BUNDLES
from mako_plugin.package_paths import PAYLOAD_ROOT, RENDERER_MANIFEST


def renderer_asset() -> dict:
    return json.loads(RENDERER_MANIFEST.read_text())["remote_binary"][0]


def bin_dir() -> Path:
    return PAYLOAD_ROOT / BIN_DIR


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, sha256: str, dest: Path) -> None:
    """dest from url unless it's there already with this SHA-256."""
    if dest.exists() and _sha256(dest) == sha256.lower():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG", "")
    result = subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(tmp), url],
                            capture_output=True, text=True, env=env, timeout=1800)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Download of {dest.name} failed: {result.stderr[-300:]}")
    if _sha256(tmp) != sha256.lower():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name} doesn't match its expected checksum")
    tmp.replace(dest)
    decky.logger.info(f"[MAKO] downloaded {dest.name}")


def ensure_renderer() -> None:
    """The MAKO Renderer archive (a few MB) that MAKO's installer unpacks."""
    asset = renderer_asset()
    _download(asset["url"], asset["sha256hash"], bin_dir() / asset["name"])


def flatpaks_ready() -> bool:
    return all((bin_dir() / b.filename).is_file() for b in FLATPAK_RUNTIME_BUNDLES.values())


def ensure_flatpaks() -> None:
    """The Flatpak runtime extensions (a ~110 MB download), only fetched when one is installed for Flatpak games."""
    if flatpaks_ready():
        return
    bundle = renderer_asset()["flatpak_bundle"]
    archive = bin_dir() / bundle["name"]
    _download(bundle["url"], bundle["sha256hash"], archive)
    wanted = {b.filename for b in FLATPAK_RUNTIME_BUNDLES.values()}
    with tarfile.open(archive, "r:xz") as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            if member.isfile() and name in wanted:
                with tar.extractfile(member) as src, open(bin_dir() / (name + ".part"), "wb") as dst:
                    while chunk := src.read(1024 * 1024):
                        dst.write(chunk)
                (bin_dir() / (name + ".part")).replace(bin_dir() / name)
    archive.unlink(missing_ok=True)
    if not flatpaks_ready():
        raise RuntimeError("MAKO's Flatpak download didn't contain every runtime extension")
