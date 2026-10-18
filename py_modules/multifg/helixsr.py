"""HelixSR: downloads official releases, runs HelixSR's own setup and installs it into games with HelixSR's own
installer (through helix_bridge.py). Nothing of HelixSR is bundled or changed.

Releases go to ~/HelixSR/<tag>/, the folder HelixSR Manager uses too, so either plugin sees the other's downloads.
Release download, extraction and the clean child environment are adapted from HelixSR Manager (Unlicense, PeroTuncay).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path

RELEASES_API = "https://api.github.com/repos/lonewolf0622/HelixSR/releases?per_page=20"
RELEASES_TTL = 3600          # seconds between GitHub checks (60 unauthenticated API calls per hour)
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,40}")
BRIDGE = Path(__file__).resolve().parent / "helix_bridge.py"
DLL = "amd_fidelityfx_dx12.dll"


class HelixSR:
    def __init__(self, home: Path, state_dir: Path, log_dir: Path, user: str):
        self.home = home
        self.user = user
        self.base = home / "HelixSR"
        self.state_dir = state_dir
        self.log = log_dir / "helixsr-setup.log"
        self.job_file = state_dir / "helixsr-job.json"
        self.releases_cache = state_dir / "helixsr-releases.json"
        self._lock = threading.Lock()
        self._job_thread = None

    # --- environment ---------------------------------------------------------------------------------------------

    def env(self) -> dict:
        """Environment for child processes: Decky's bundled Python sets LD_LIBRARY_PATH and PyInstaller variables
        that break system tools such as curl and Proton's wine, and would make another Python load Decky's stdlib."""
        env = dict(os.environ)
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        for k in list(env):
            if k in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH") or k.startswith(("_MEI", "_PYI")) or "_MEI" in env[k]:
                env.pop(k)
        if orig:
            env["LD_LIBRARY_PATH"] = orig
        env["HOME"] = str(self.home)
        env["USER"] = self.user
        env["XDG_DATA_HOME"] = str(self.home / ".local" / "share")
        env["PATH"] = env.get("PATH", "") + ":/usr/local/bin:/usr/bin:/bin"
        return env

    def python(self) -> str:
        """HelixSR's portable Python when its setup made one, else the system's (the installer needs no packages)."""
        portable = self.home / ".local" / "share" / "HelixSR" / "python" / "bin" / "python3"
        return str(portable) if portable.exists() else (shutil.which("python3", path="/usr/bin:/bin") or "python3")

    # --- releases ------------------------------------------------------------------------------------------------

    def releases(self, refresh: bool = False) -> list[dict]:
        """Published HelixSR releases with their zip, newest first (cached; the cache is used offline)."""
        cached = self._read_json(self.releases_cache) or {}
        if not refresh and cached.get("checked", 0) > time.time() - RELEASES_TTL:
            return cached.get("releases", [])
        try:
            p = subprocess.run(["curl", "-fsSL", "--retry", "2", "-H", "Accept: application/vnd.github+json",
                                RELEASES_API], env=self.env(), capture_output=True, timeout=30)
            if p.returncode:
                raise RuntimeError(p.stderr.decode(errors="replace")[-200:])
            out = []
            for r in json.loads(p.stdout):
                asset = _release_zip(r.get("assets", []))
                if r.get("draft") or not asset or not _TAG.fullmatch(r.get("tag_name") or ""):
                    continue
                digest = asset.get("digest") or ""
                out.append({
                    "tag": r["tag_name"], "name": asset["name"], "url": asset["browser_download_url"],
                    "size": asset.get("size"), "prerelease": bool(r.get("prerelease")),
                    "published_at": r.get("published_at"),
                    "sha256": digest[7:].lower() if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) else None,
                })
            out.sort(key=lambda r: r["published_at"] or "", reverse=True)
            self._write_json(self.releases_cache, {"checked": time.time(), "releases": out})
            return out
        except Exception:
            return cached.get("releases", [])

    def latest(self) -> dict | None:
        stable = [r for r in self.releases() if not r["prerelease"]]
        return stable[0] if stable else None

    def local_releases(self) -> list[str]:
        """Downloaded releases (~/HelixSR/<tag>/ with HelixSR's DLL and setup), newest first."""
        tags = []
        try:
            for d in self.base.iterdir():
                if d.is_dir() and _TAG.fullmatch(d.name) and (d / DLL).exists():
                    tags.append(d.name)
        except OSError:
            pass
        return sorted(tags, key=_version_key, reverse=True)

    def release_dir(self, tag: str) -> Path:
        if not _TAG.fullmatch(tag or ""):
            raise ValueError(f"Invalid release tag: {tag!r}")
        return self.base / tag

    def active(self) -> str | None:
        """The release games get: the newest downloaded one whose setup has finished, else the newest downloaded."""
        local = self.local_releases()
        ready = [t for t in local if self.ready(t)]
        return (ready or local or [None])[0]

    def ready(self, tag: str) -> bool:
        """The setup built the upscaling network into this release's DLL (as helixsr_install.py checks it)."""
        dll = self.release_dir(tag) / DLL
        try:
            with open(dll, "rb") as f:
                f.seek(-32, os.SEEK_END)
                if f.read(8) == b"HXSRNET1":
                    return True
        except OSError:
            return False
        return all((dll.parent / n).exists() for n in ("helixsr_weights.bin", "helixsr_kernels.pak"))

    # --- install job: download, verify, extract, run HelixSR's setup ---------------------------------------------

    def status(self) -> dict:
        job = self._read_json(self.job_file) or {}
        if job.get("state") == "running" and not self._job_alive(job):
            job["state"] = "failed" if not job.get("rc_file") or not Path(job["rc_file"]).exists() else (
                "succeeded" if Path(job["rc_file"]).read_text().strip() == "0" else "failed")
            if job["state"] == "succeeded" and job.get("tag") and not self.ready(job["tag"]):
                job["state"] = "failed"
                job["error"] = "The setup ended without building the network. See the log."
            if job["state"] == "failed" and not job.get("error"):
                errors = [l for l in _tail(self.log, 40) if "error:" in l]
                job["error"] = errors[-1].split("error:", 1)[1].strip() if errors else "The setup stopped. See the log."
            self._write_json(self.job_file, job)
        if job.get("phase") == "download" and job.get("state") == "running" and job.get("zip"):
            try:
                job["downloaded"] = Path(job["zip"]).stat().st_size
            except OSError:
                job["downloaded"] = 0
        local = self.local_releases()
        latest = self.latest()
        active = self.active()
        return {
            "job": job or None,
            "log": _tail(self.log, 12),
            "local": local,
            "active": active,
            "active_ready": bool(active and self.ready(active)),
            "latest": latest,
            "update_available": bool(latest and latest["tag"] not in local),
        }

    def start_install(self, tag: str | None = None) -> dict:
        with self._lock:
            job = self.status()["job"]
            if job and job.get("state") == "running":
                return {"ok": False, "error": "HelixSR is already being installed."}
            if tag and (self.release_dir(tag) / "helixsr-setup.sh").exists():
                rel = {"tag": tag, "name": f"{tag}.zip"}   # already downloaded: only its setup runs again
            else:
                rel = next((r for r in self.releases(refresh=True) if r["tag"] == tag), None) if tag else self.latest()
            if not rel:
                return {"ok": False, "error": "Couldn't get HelixSR's releases from GitHub. Check the connection."}
            job = {"state": "running", "phase": "download", "tag": rel["tag"], "size": rel.get("size"),
                   "started": time.time(), "pid": os.getpid(), "zip": str(self.base / rel["name"])}
            self._write_json(self.job_file, job)
            self._job_thread = threading.Thread(target=self._run_job, args=(rel, job), daemon=True)
            self._job_thread.start()
            return {"ok": True, "tag": rel["tag"]}

    def _run_job(self, rel: dict, job: dict) -> None:
        try:
            d = self.release_dir(rel["tag"])
            zip_path = Path(job["zip"])
            if d.exists() and (d / "helixsr-setup.sh").exists():
                self._log(f"HelixSR {rel['tag']} is already downloaded in {d}")
            else:
                self.base.mkdir(parents=True, exist_ok=True)
                self._log(f"downloading {rel['url']}")
                p = subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(zip_path), rel["url"]],
                                   env=self.env(), capture_output=True, timeout=3600)
                if p.returncode:
                    raise RuntimeError("Download failed: " + p.stderr.decode(errors="replace")[-300:])
                job.update(phase="verify")
                self._write_json(self.job_file, job)
                if rel.get("sha256"):
                    if _sha256(zip_path) != rel["sha256"]:
                        zip_path.unlink(missing_ok=True)
                        raise RuntimeError("The download doesn't match GitHub's checksum. Try again.")
                    self._log("checksum matches GitHub's")
                job.update(phase="extract")
                self._write_json(self.job_file, job)
                tmp = d.with_name(d.name + ".partial")
                shutil.rmtree(tmp, ignore_errors=True)
                _extract(zip_path, tmp)
                shutil.rmtree(d, ignore_errors=True)
                tmp.rename(d)
                zip_path.unlink(missing_ok=True)
                self._log(f"extracted into {d}")
            job.update(phase="setup")
            self._start_setup(d, job)
        except Exception as e:
            job.update(state="failed", error=str(e))
            self._write_json(self.job_file, job)
            self._log(f"error: {e}")

    def _start_setup(self, d: Path, job: dict) -> None:
        """HelixSR's own setup, unchanged: --yes agrees to the NVIDIA DLSS download the user confirmed in the plugin.
        stdin is empty, so after building the network its game installer stops at its first question; games are
        installed one by one from the plugin instead. A wrapper shell records the exit code, so the result is known
        even if Decky restarts the plugin meanwhile."""
        rc = self.state_dir / "helixsr-setup.rc"
        rc.unlink(missing_ok=True)
        tmp = self.state_dir / "helixsr-tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        env = self.env()
        env["TMPDIR"] = str(tmp)
        self._log(f"running {d / 'helixsr-setup.sh'} --yes")
        with open(self.log, "ab") as log:
            proc = subprocess.Popen(["bash", "-c", '"$@"; echo $? > "$0"', str(rc), "bash", str(d / "helixsr-setup.sh"),
                                     "--yes"], cwd=str(d), env=env, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        job.update(pid=proc.pid, rc_file=str(rc), setup_started=time.time())
        self._write_json(self.job_file, job)
        proc.wait()
        self.status()  # records the result

    def _job_alive(self, job: dict) -> bool:
        if job.get("phase") in ("download", "verify", "extract"):
            return bool(self._job_thread and self._job_thread.is_alive())
        pid = job.get("pid")
        if not pid:
            return False
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        return not (job.get("rc_file") and Path(job["rc_file"]).exists())

    # --- games ---------------------------------------------------------------------------------------------------

    def bridge(self, *args: str, timeout: int = 120) -> dict:
        tag = self.active()
        if not tag:
            return {"ok": False, "error": "HelixSR isn't installed yet."}
        p = subprocess.run([self.python(), "-I", str(BRIDGE), str(self.release_dir(tag)), *args], env=self.env(),
                           capture_output=True, timeout=timeout)
        lines = p.stdout.decode(errors="replace").strip().splitlines()
        try:
            out = json.loads(lines[-1])
        except (IndexError, ValueError):
            out = {"ok": False, "error": (p.stderr.decode(errors="replace") or "HelixSR's installer failed")[-400:]}
        out["release"] = tag
        return out

    def remove(self, game_folders: list[str]) -> dict:
        """Takes HelixSR out of every game (putting their files back) with HelixSR's own installer, then deletes the
        downloaded releases and what HelixSR's setup built or downloaded (~/.local/share/HelixSR)."""
        job = self.status().get("job") or {}
        if job.get("state") == "running":
            return {"ok": False, "error": "Wait for HelixSR's setup to finish"}
        removed = []
        if self.active():
            r = self.bridge("remove_all", *game_folders, timeout=900)
            if not r.get("ok"):
                return r
            if r["left"]:
                return {"ok": False, "removed": r["removed"],
                        "error": f"HelixSR couldn't be removed from {', '.join(r['left'])}. Close the game and try again."}
            removed = r["removed"]
        for d in self.base.iterdir() if self.base.is_dir() else []:
            if d.is_dir() and _TAG.fullmatch(d.name.removesuffix(".partial")):
                shutil.rmtree(d, ignore_errors=True)
        try:
            self.base.rmdir()   # only when nothing else is in it
        except OSError:
            pass
        shutil.rmtree(self.home / ".local" / "share" / "HelixSR", ignore_errors=True)
        self.job_file.unlink(missing_ok=True)
        self._log(f"removed HelixSR (games: {', '.join(removed) or 'none'})")
        return {"ok": True, "removed": removed}

    def game_status(self, folder: str) -> dict:
        return self.bridge("status", folder)

    def install_game(self, folder: str, route: str | None = None) -> dict:
        if route not in (None, "", "direct", "scaler"):
            return {"ok": False, "error": f"Unknown install method: {route}"}
        tag = self.active()
        if tag and not self.ready(tag):
            return {"ok": False, "error": "HelixSR's setup hasn't finished yet."}
        return self.bridge("install", folder, *([route] if route else []))

    def uninstall_game(self, folder: str) -> dict:
        return self.bridge("uninstall", folder)

    # --- helpers -------------------------------------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log, "a") as f:
            f.write(f"[multifg] {time.strftime('%H:%M:%S')} {msg}\n")

    @staticmethod
    def _read_json(p: Path):
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write_json(p: Path, data) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(p)


def _release_zip(assets: list) -> dict | None:
    """HelixSR's own zip among a release's files (HelixSR-<version>.zip, not the Scaler or desktop app downloads)."""
    zips = [a for a in assets if a.get("name", "").lower().endswith(".zip")]
    own = [a for a in zips if re.fullmatch(r"helixsr-\d[\w.\-]*\.zip", a["name"].lower())]
    other = [a for a in zips if not re.search(r"scaler|desktop", a["name"].lower())]
    return (own or other or [None])[0]


def _version_key(tag: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", tag)[:4])


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract(zip_path: Path, target: Path) -> None:
    """Extracts the release, dropping its single top folder, refusing paths outside target, keeping exec bits."""
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(zip_path) as z:
        members = z.infolist()
        tops = {m.filename.split("/", 1)[0] for m in members}
        strip = len(tops) == 1 and all("/" in m.filename for m in members)
        for m in members:
            name = m.filename.split("/", 1)[1] if strip else m.filename
            if not name or name.endswith("/"):
                continue
            dest = (target / name).resolve()
            if root not in dest.parents:
                raise RuntimeError(f"Unsafe path in the zip: {m.filename}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            mode = (m.external_attr >> 16) & 0o777
            if dest.suffix == ".sh":
                mode |= 0o755
            if mode:
                os.chmod(dest, mode)


def _tail(p: Path, n: int) -> list[str]:
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 16384))
            lines = f.read().decode(errors="replace").replace("\r", "\n").splitlines()
        return [l for l in lines if l.strip()][-n:]
    except OSError:
        return []
