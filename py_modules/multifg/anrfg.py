"""ANR FG (Apex Neural Rendering, apex-compute/ANR): neural frame generation that takes the place of DLSS frame
generation. It comes as an OptiScaler build of Apex's (custom frame generation providers, which Decky Framegen's
OptiScaler can't load) with ANR FG in its custom folder. Nothing of it is bundled.

The release's "full" package is downloaded from GitHub and unpacked into the plugin's runtime folder. Its own
install.sh and uninstall.sh put it into a game's .exe folder and take it out (they back up and restore the proxy DLL
and OptiScaler.ini there), so an update follows upstream. The game must offer DLSS frame generation (DirectX 12):
turning that on in the game runs ANR FG instead.
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import updates
from .helixsr import _extract

REPO = "apex-compute/ANR"
# tags FG-V.B14 -> files anr-fg-V.B14-full.zip
TAG_PREFIX = "FG-"
ARCHIVE = "anr-fg-{version}-full.zip"
RECORD = Path("OptiScaler") / "nr_fg_install.json"
CONFIG = Path("OptiScaler") / "custom" / "Apex Neural Rendering FG" / "dlssg" / "nr_fg.ini"
MODEL_SIZES = ("auto", "large", "small")


class ANRFG:
    def __init__(self, state_dir: Path):
        self.base = state_dir / "anrfg"
        self.package = self.base / "package"     # the unpacked "full" release
        self.lock = threading.RLock()
        self.job: dict | None = None
        self._latest = None                       # (checked, release)

    # --- the upstream copy ---------------------------------------------------------------------------------------

    def info(self) -> dict | None:
        try:
            return json.loads((self.package / "nr_fg_package.json").read_text())
        except (OSError, ValueError):
            return None

    def version(self) -> str | None:
        info = self.info()
        return (info or {}).get("version") if self.ready() else None

    def ready(self) -> bool:
        return all((self.package / f).is_file() for f in ("install.sh", "uninstall.sh", "game/dxgi.dll",
                                                            "nr_fg_package.json"))

    # --- releases ------------------------------------------------------------------------------------------------

    def latest(self, refresh: bool = False) -> dict | None:
        """ANR FG's newest release with its full package: {version, tag, name, url, size, sha256}."""
        if not refresh and self._latest and self._latest[0] > time.time() - 3600:
            return self._latest[1]
        rel = updates.latest_release(REPO)
        tag = rel.get("tag_name") or ""
        version = tag.removeprefix(TAG_PREFIX)
        name = ARCHIVE.format(version=version)
        asset = next((a for a in rel.get("assets", []) if a.get("name") == name), None)
        out = None
        if asset and not rel.get("draft"):
            digest = asset.get("digest") or ""
            out = {"version": version, "tag": tag, "name": name, "url": asset["browser_download_url"],
                   "size": asset.get("size"), "sha256": digest[7:].lower() if digest.startswith("sha256:") else None}
        elif tag.startswith(TAG_PREFIX):
            # the file list couldn't be read: the name follows the tag
            out = {"version": version, "tag": tag, "name": name, "size": None, "sha256": None,
                   "url": f"https://github.com/{REPO}/releases/download/{tag}/{name}"}
        self._latest = (time.time(), out)
        return out

    # --- install job ---------------------------------------------------------------------------------------------

    def status(self, games: list[str]) -> dict:
        info = self.info() if self.ready() else None
        return {"version": self.version(), "ready": self.ready(), "built_at": (info or {}).get("built_at"),
                "games": games, "job": dict(self.job) if self.job else None}

    def running(self) -> bool:
        return bool(self.job and self.job["state"] == "running")

    def start_install(self, after=None) -> dict:
        """Downloads the latest release in the background; after(job) runs once it is unpacked (games refreshed)."""
        with self.lock:
            if self.running():
                return {"ok": False, "error": "ANR FG is already being installed."}
            self.job = {"state": "running", "done": 0, "total": 0, "error": None, "version": None,
                        "started": time.time()}
            threading.Thread(target=self._run, args=(after,), daemon=True).start()
            return {"ok": True}

    def _run(self, after) -> None:
        job = self.job
        try:
            try:
                rel = self.latest(refresh=True)
            except Exception as exc:
                raise RuntimeError(f"Couldn't reach ANR's releases on GitHub: {exc}") from exc
            if not rel:
                raise RuntimeError("ANR's latest release has no full package to download.")
            job.update(version=rel["version"], total=rel.get("size") or 0)
            if rel["version"] != self.version():
                self._unpack(rel, job)
                if after:
                    job["refreshed"] = after()
            job.update(state="done", version=self.version())
        except Exception as exc:  # shown in the panel
            job.update(state="failed", error=str(exc))

    def _unpack(self, rel: dict, job: dict) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        zip_path = self.base / rel["name"]
        zip_path.unlink(missing_ok=True)
        p = subprocess.Popen(["curl", "-fsSL", "--retry", "3", "-o", str(zip_path), rel["url"]], env=_env(),
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            started = time.time()
            while p.poll() is None:
                try:
                    job["done"] = zip_path.stat().st_size
                except OSError:
                    pass
                if time.time() - started > 900:
                    p.kill()
                time.sleep(0.5)
            if p.returncode:
                raise RuntimeError("Download failed: " + p.stderr.read().decode(errors="replace")[-300:])
            job["done"] = job["total"] = zip_path.stat().st_size
            if rel.get("sha256") and _sha256(zip_path) != rel["sha256"]:
                raise RuntimeError("The download doesn't match GitHub's checksum. Try again.")
            tmp = self.base / "package.partial"
            shutil.rmtree(tmp, ignore_errors=True)
            _extract(zip_path, tmp)
            if not all((tmp / f).is_file() for f in ("install.sh", "uninstall.sh", "game/dxgi.dll")):
                shutil.rmtree(tmp, ignore_errors=True)
                raise RuntimeError("The ANR FG package is missing its files (install.sh, game/dxgi.dll).")
            with self.lock:
                shutil.rmtree(self.package, ignore_errors=True)
                tmp.rename(self.package)
        finally:
            if p.stderr:
                p.stderr.close()
            zip_path.unlink(missing_ok=True)

    def remove(self, games: list[str]) -> dict:
        if self.running():
            return {"ok": False, "error": "Wait for the install to finish."}
        if games:
            return {"ok": False, "error": "Take ANR FG out of your games first.", "games": games}
        with self.lock:
            shutil.rmtree(self.base, ignore_errors=True)
            self.job = None
        return {"ok": True}

    # --- games ---------------------------------------------------------------------------------------------------

    @staticmethod
    def installed_in(target: str | None) -> bool:
        return bool(target) and (Path(target) / RECORD).is_file()

    @staticmethod
    def proxy(target: str) -> str:
        try:
            return json.loads((Path(target) / RECORD).read_text()).get("proxy") or "dxgi.dll"
        except (OSError, ValueError, AttributeError):
            return "dxgi.dll"

    def overrides(self, target: str) -> str:
        """The WINEDLLOVERRIDES=... Proton needs to load ANR's OptiScaler under its proxy name."""
        return f'WINEDLLOVERRIDES="{self.proxy(target).removesuffix(".dll")}=n,b"'

    def _script(self, name: str, target: str) -> tuple[bool, str]:
        p = subprocess.run(["sh", str(self.package / name), target], env=_env(), capture_output=True, text=True,
                           timeout=180, stdin=subprocess.DEVNULL)
        out = (p.stdout + p.stderr).strip()
        return p.returncode == 0, out.splitlines()[-1] if out else ""

    def install(self, target: str) -> dict:
        """ANR FG with Apex's OptiScaler into the game's .exe folder (its own install.sh)."""
        if not self.ready():
            return {"ok": False, "error": "Install ANR FG under Backends first."}
        if not Path(target).is_dir():
            return {"ok": False, "error": f"The game's folder isn't there: {target}"}
        with self.lock:
            ok, msg = self._script("install.sh", target)
        if not ok:
            return {"ok": False, "error": msg or "ANR FG's installer failed."}
        return {"ok": True, "target_dir": target, "proxy": self.proxy(target), "overrides": self.overrides(target)}

    def uninstall(self, target: str) -> dict:
        """ANR FG out of the game: the proxy DLL and OptiScaler.ini it backed up go back (its own uninstall.sh)."""
        if not self.installed_in(target):
            return {"ok": True, "was_on": False}
        if not self.ready():
            return {"ok": False, "error": "ANR FG's package is gone: install it under Backends to take it out."}
        with self.lock:
            ok, msg = self._script("uninstall.sh", target)
        return {"ok": True, "was_on": True} if ok else {"ok": False, "error": msg or "ANR FG's uninstaller failed."}

    @staticmethod
    def model_size(target: str) -> str | None:
        return _ini_value(Path(target) / CONFIG, "model_size")

    @staticmethod
    def set_model_size(target: str, size: str) -> bool:
        if size not in MODEL_SIZES:
            return False
        return _set_ini_value(Path(target) / CONFIG, "model_size", size)

    @staticmethod
    def newest_log(target: str) -> str | None:
        folder = Path(target) / CONFIG.parent
        try:
            logs = sorted(folder.glob("nr_fg-*.log"), key=lambda p: p.stat().st_mtime)
        except OSError:
            return None
        return str(logs[-1]) if logs else None


def _ini_value(path: Path, key: str) -> str | None:
    """A key=value of nr_fg.ini (no sections; ; comments)."""
    try:
        for line in path.read_text(errors="replace").splitlines():
            m = re.match(rf"\s*{re.escape(key)}\s*=\s*(\S*)", line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return None


def _set_ini_value(path: Path, key: str, value: str) -> bool:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return False
    done = False
    for i, line in enumerate(lines):
        if re.match(rf"\s*{re.escape(key)}\s*=", line):
            lines[i] = f"{key} = {value}"
            done = True
            break
    if not done:
        lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n")
    return True


def _env() -> dict:
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG", "")
    return env


def _sha256(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
