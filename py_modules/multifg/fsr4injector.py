"""FSR4 Injector (Rayekkk/FSR4Injector): AMD's own FSR 4.1 library in games that ship FSR 3.1 or newer, with a small
shim DLL that tells it the GPU family Wine can't report. Nothing of it is bundled.

Its release ZIP is downloaded from GitHub (checked against GitHub's SHA-256) and unpacked into the plugin's runtime
folder. Its own Python modules (BSD-3-Clause) then do the work, loaded from that copy, so an update follows upstream:
fsr4_dll fetches AMD's amdxcffx64.dll from AMD's servers and checks it, fsr4_install puts the shim and AMD's DLL next to
a game's FidelityFX DLL and takes them out again (with the launch options), fsr4_gpu reads the GPU.
"""

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import updates
from .helixsr import _extract

REPO = "Rayekkk/FSR4Injector"
ARCHIVE = "FSR4Injector-{version}.zip"
EULA_URL = "https://www.amd.com/en/legal/eula/amd-software-eula.html"
# Upstream modules used here, in import order (fsr4_install imports fsr4_dll)
MODULES = ("fsr4_dll", "fsr4_gpu", "fsr4_install", "fsr4_games")
MAX_DEPTH = 5


class FSR4Injector:
    def __init__(self, state_dir: Path, settings_dir: Path):
        self.base = state_dir / "fsr4injector"
        self.plugin_dir = self.base / "plugin"      # the unpacked upstream release
        self.ffx = self.base / "amdxcffx64.dll"      # AMD's library, fetched from AMD
        self.manifest_path = settings_dir / "fsr4injector-manifest.json"
        self.lock = threading.RLock()
        self.job: dict | None = None
        self._mods = None          # (version, namespace of modules)
        self._manifest = None
        self._gpu = None
        self._dll_ok = None        # (size, mtime, valid)
        self._latest = None        # (checked, release)

    # --- the upstream copy ---------------------------------------------------------------------------------------

    def version(self) -> str | None:
        try:
            return json.loads((self.plugin_dir / "plugin.json").read_text())["version"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def mods(self):
        """The upstream modules of the unpacked release, reloaded after an update; None when it isn't unpacked."""
        version = self.version()
        if not version or not all((self.plugin_dir / f"{m}.py").is_file() for m in MODULES):
            return None
        with self.lock:
            if self._mods and self._mods[0] == version:
                return self._mods[1]
            for name in MODULES + ("fsr4_env",):
                sys.modules.pop(name, None)
            path = str(self.plugin_dir)
            if path not in sys.path:
                sys.path.append(path)  # appended: nothing else is looked up there first
            mods = type("Upstream", (), {})()
            for name in MODULES:
                setattr(mods, name.removeprefix("fsr4_"), importlib.import_module(name))
            self._mods = (version, mods)
            self._manifest = None
            return mods

    def shim(self) -> Path:
        return self.plugin_dir / "bin" / "amdxc64.dll"

    def manifest(self):
        m = self.mods()
        if not m:
            return None
        if self._manifest is None:
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            self._manifest = m.install.Manifest(str(self.manifest_path))
        return self._manifest

    def gpu(self) -> dict | None:
        m = self.mods()
        if m and self._gpu is None:
            try:
                self._gpu = m.gpu.detect() or {}
            except Exception:
                self._gpu = {}
        return self._gpu or None

    def dll_ready(self) -> bool:
        """AMD's library is there and matches the release's recipe (its 85 MB hash is checked once per change)."""
        m = self.mods()
        try:
            st = self.ffx.stat()
        except OSError:
            return False
        if not m:
            return False
        key = (st.st_size, st.st_mtime, m.dll.RECIPE["sha256"])
        if not self._dll_ok or self._dll_ok[0] != key:
            self._dll_ok = (key, bool(m.dll.is_valid(str(self.ffx))))
        return self._dll_ok[1]

    def ready(self) -> bool:
        return bool(self.mods() and self.shim().is_file() and self.dll_ready())

    # --- releases ------------------------------------------------------------------------------------------------

    def latest(self, refresh: bool = False) -> dict | None:
        """FSR4 Injector's newest stable release with its ZIP: {version, tag, name, url, size, sha256}."""
        if not refresh and self._latest and self._latest[0] > time.time() - 3600:
            return self._latest[1]
        rel = updates.latest_release(REPO)
        tag = rel.get("tag_name") or ""
        version = tag.removeprefix("v")
        name = ARCHIVE.format(version=version)
        asset = next((a for a in rel.get("assets", []) if a.get("name") == name), None)
        out = None
        if asset and not rel.get("draft") and not rel.get("prerelease"):
            digest = asset.get("digest") or ""
            out = {"version": version, "tag": tag, "name": name, "url": asset["browser_download_url"],
                   "size": asset.get("size"), "sha256": digest[7:].lower() if digest.startswith("sha256:") else None}
        self._latest = (time.time(), out)
        return out

    # --- install job: the release ZIP, then AMD's library --------------------------------------------------------

    def status(self) -> dict:
        m = self.mods()
        gpu = self.gpu()
        recipe = {k: m.dll.RECIPE.get(k) for k in ("driver", "fsr", "dll_size")} if m else None
        manifest = self.manifest()
        return {
            "version": self.version(),
            "unpacked": bool(m and self.shim().is_file()),
            "dll_ready": self.dll_ready(),
            "ready": self.ready(),
            "gpu": gpu,
            "recipe": recipe,
            "eula_url": EULA_URL,
            "games": sorted(str(a) for a in manifest.entries) if manifest else [],
            "job": dict(self.job) if self.job else None,
        }

    def running(self) -> bool:
        return bool(self.job and self.job["state"] == "running")

    def start_install(self) -> dict:
        with self.lock:
            if self.running():
                return {"ok": False, "error": "FSR4 Injector is already being installed."}
            self.job = {"state": "running", "phase": "release", "done": 0, "total": 0, "error": None,
                        "version": None, "started": time.time()}
            threading.Thread(target=self._run, daemon=True).start()
            return {"ok": True}

    def _run(self) -> None:
        job = self.job
        try:
            try:
                rel = self.latest(refresh=True)
            except Exception as exc:
                if not self.mods():
                    raise RuntimeError(f"Couldn't reach FSR4 Injector's releases on GitHub: {exc}") from exc
                rel = None   # offline with a copy unpacked: only AMD's library is fetched
            if rel is None and not self.mods():
                raise RuntimeError("FSR4 Injector's latest release has no plugin ZIP to download.")
            if rel and rel["version"] != self.version():
                job.update(version=rel["version"], total=rel.get("size") or 0)
                self._unpack(rel)
                m = self.mods()
                refreshed = m.install.refresh_shim(self.manifest(), str(self.shim())) if m else 0
                job["refreshed"] = refreshed
            job["version"] = self.version()
            m = self.mods()
            if not m:
                raise RuntimeError("The FSR4 Injector release is incomplete.")
            if not self.dll_ready():
                job.update(phase="amd", done=0, total=m.dll.RECIPE["dll_size"])
                self.base.mkdir(parents=True, exist_ok=True)
                m.dll.fetch(str(self.ffx), progress=lambda done, total: job.update(done=done, total=total),
                            cancelled=lambda: job.get("cancel", False))
                self._dll_ok = None
                if not self.dll_ready():
                    raise RuntimeError("AMD's FSR 4 library didn't pass its check.")
            job.update(state="done", phase="done")
        except Exception as exc:  # shown in the panel
            job.update(state="failed", error=str(exc))

    def _unpack(self, rel: dict) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        zip_path = self.base / rel["name"]
        p = subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(zip_path), rel["url"]], env=_env(),
                           capture_output=True, timeout=600)
        try:
            if p.returncode:
                raise RuntimeError("Download failed: " + p.stderr.decode(errors="replace")[-300:])
            if rel.get("sha256") and _sha256(zip_path) != rel["sha256"]:
                raise RuntimeError("The download doesn't match GitHub's checksum. Try again.")
            tmp = self.base / "plugin.partial"
            shutil.rmtree(tmp, ignore_errors=True)
            _extract(zip_path, tmp)
            if not (tmp / "bin" / "amdxc64.dll").is_file() or not (tmp / "plugin.json").is_file():
                shutil.rmtree(tmp, ignore_errors=True)
                raise RuntimeError("The FSR4 Injector release is missing its files.")
            with self.lock:
                shutil.rmtree(self.plugin_dir, ignore_errors=True)
                tmp.rename(self.plugin_dir)
                self._mods = None
        finally:
            zip_path.unlink(missing_ok=True)

    def remove(self) -> dict:
        """Deletes the unpacked release and AMD's library; games have to be turned off first."""
        if self.running():
            return {"ok": False, "error": "Wait for the install to finish."}
        manifest = self.manifest()
        if manifest and manifest.entries:
            return {"ok": False, "error": "Turn FSR4 Injector off in your games first.",
                    "games": sorted(str(a) for a in manifest.entries)}
        with self.lock:
            shutil.rmtree(self.base, ignore_errors=True)
            self._mods = self._manifest = self._dll_ok = None
            self.job = None
        return {"ok": True}

    # --- games ---------------------------------------------------------------------------------------------------

    def find(self, install_dir: str) -> dict:
        """Where the game's FidelityFX DLL is (FSR 3.1+), and whether anti-cheat files are there."""
        m = self.mods()
        names = tuple(getattr(m.games, "FFX_DLLS", ())) if m else ()
        markers = tuple(getattr(m.games, "ANTICHEAT", ())) if m else ()
        found, anticheat = None, False
        base_depth = install_dir.rstrip("/").count("/")
        for root, dirs, files in os.walk(install_dir):
            lower = [n.lower() for n in dirs + files]
            if any(mark in n for n in lower for mark in markers):
                anticheat = True
            if not found:
                hit = next((f for f in files if f.lower() in names), None)
                if hit:
                    found = (root, hit)
            if root.count("/") - base_depth >= MAX_DEPTH:
                dirs[:] = []
        return {"target_dir": found[0] if found else None, "ffx_dll": found[1] if found else None,
                "anticheat": anticheat}

    def game_status(self, appid: int, install_dir: str, watermark: bool) -> dict:
        m = self.mods()
        if not m:
            return {"ok": True, "unpacked": False}
        manifest = self.manifest()
        entry = manifest.entries.get(appid)
        where = self.find(install_dir)
        verdict, reason = m.install.verdict(m.install.read_status(manifest, appid))
        applied = (entry or {}).get("launch_applied") or ""
        return {"ok": True, "unpacked": True, "ready": self.ready(), "found": bool(where["target_dir"]),
                "ffx_dll": where["ffx_dll"], "anticheat": where["anticheat"], "enabled": entry is not None,
                "target_dir": (entry or {}).get("target_dir") or where["target_dir"],
                "verdict": verdict if entry else None, "reason": reason if entry else None,
                "watermark": (m.install.WATERMARK in applied.split()) if entry else watermark,
                "gpu_supported": bool((self.gpu() or {}).get("model"))}

    def enable(self, appid: int, install_dir: str, launch_options: str, watermark: bool) -> dict:
        """Puts the two DLLs next to the game's FidelityFX DLL; returns the launch options to apply."""
        m = self.mods()
        if not self.ready():
            return {"ok": False, "error": "Install FSR4 Injector under Backends first."}
        gpu = self.gpu()
        if not (gpu and gpu.get("model")):
            return {"ok": False, "error": "AMD's FSR 4 has no model for this GPU, so games would stay on FSR 3."}
        where = self.find(install_dir)
        if not where["target_dir"]:
            return {"ok": False, "error": "This game has no FSR 3.1 DLL (amd_fidelityfx_*_dx12.dll): FSR4 Injector "
                                          "only works in DirectX 12 games with FSR 3.1 or newer."}
        game = {"appid": appid, "target_dir": where["target_dir"]}
        with self.lock:
            try:
                options = m.install.enable(self.manifest(), game, str(self.shim()), str(self.ffx), launch_options,
                                           gpu, True, watermark)
            except m.install.InstallError as exc:
                return {"ok": False, "error": str(exc)}
        return {"ok": True, "launch_options": options}

    def disable(self, appid: int, launch_options: str) -> dict:
        """Takes our files out of the game; returns the launch options with ours taken out."""
        manifest = self.manifest()
        if not manifest or appid not in manifest.entries:
            return {"ok": True, "launch_options": None, "kept": [], "was_on": False}
        with self.lock:
            r = self.mods().install.disable(manifest, appid, launch_options)
        return {"ok": True, "launch_options": r["launch_options"], "kept": r["kept"], "was_on": True}

    def enabled(self, appid: int) -> bool:
        manifest = self.manifest()
        return bool(manifest and appid in manifest.entries)

    def set_watermark(self, appid: int, launch_options: str, on: bool) -> str | None:
        """The launch options with AMD's watermark added or taken out, in a game that has FSR4 Injector; else None."""
        manifest = self.manifest()
        if not manifest:
            return None
        with self.lock:
            return self.mods().install.set_watermark(manifest, appid, launch_options, on)


    # --- everything, for the full panel -------------------------------------------------------------------------

    def details(self, names: dict) -> dict:
        """What FSR4 Injector's own panel shows: version, GPU, AMD's library, launch options to copy, and the games it
        is in with their last session. names: app id -> game name."""
        m = self.mods()
        if not m:
            return {"ok": True, "unpacked": False}
        manifest = self.manifest()
        gpu = self.gpu()
        recipe = m.dll.RECIPE
        games = []
        for appid, entry in sorted(manifest.entries.items()):
            verdict, reason = m.install.verdict(m.install.read_status(manifest, appid))
            applied = entry.get("launch_applied") or ""
            games.append({"appid": str(appid), "name": names.get(str(appid), f"App {appid}"),
                          "target_dir": entry.get("target_dir"), "verdict": verdict, "reason": reason,
                          "watermark": m.install.WATERMARK in applied.split(), "enabled_at": entry.get("enabled_at")})
        return {
            "ok": True, "unpacked": True, "version": self.version(), "folder": str(self.base),
            "gpu": {**gpu, "pci": f"1002:{gpu['device']:04x}"} if gpu and "device" in gpu else gpu,
            "amd": {"driver": recipe.get("driver"), "fsr": recipe.get("fsr"), "file_version": recipe.get("file_version"),
                    "size_mb": round(recipe.get("dll_size", 0) / (1 << 20)), "ready": self.dll_ready(),
                    "path": str(self.ffx)},
            "launch_options": {"plain": f"{m.install.launch_prefix(False)} %command%",
                               "watermark": f"{m.install.launch_prefix(True)} %command%"},
            "games": games,
        }

    def compatible(self, steam_root: str) -> list[dict]:
        """Installed games with an FSR 3.1+ DLL (FSR4 Injector's own library scan), and whether it is in each."""
        m = self.mods()
        if not m:
            return []
        manifest = self.manifest()
        return [{"appid": str(g["appid"]), "name": g["name"], "ffx_dll": g["ffx_dll"], "anticheat": g["anticheat"],
                 "enabled": g["appid"] in manifest.entries} for g in m.games.scan(steam_root)]


def _env() -> dict:
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG", "")
    return env


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
