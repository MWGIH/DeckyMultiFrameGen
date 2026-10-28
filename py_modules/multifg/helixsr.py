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

from . import helix_opti, updates

RELEASES_API = "https://api.github.com/repos/lonewolf0622/HelixSR/releases?per_page=20"
RELEASES_TTL = 3600          # seconds between GitHub checks (60 unauthenticated API calls per hour)
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,40}")
BRIDGE = Path(__file__).resolve().parent / "helix_bridge.py"
DRIVER = Path(__file__).resolve().parent / "setup_driver.py"
DLL = "amd_fidelityfx_dx12.dll"
# The newest HelixSR that runs inside a stock OptiScaler (the one Decky Framegen installs): HelixSR 2.0's DLL needs its
# own OptiScaler build, HelixSR Scaler 1.1.0 (its Dx12Upscaler=ffx); stock OptiScaler 0.9.4 falls back to FSR 2.1.2
OPTI_RELEASE = "v1.9.3"


class HelixSR:
    def __init__(self, home: Path, state_dir: Path, log_dir: Path, user: str):
        self.home = home
        self.user = user
        self.base = home / "HelixSR"
        self.state_dir = state_dir
        self.log = log_dir / "helixsr-setup.log"
        self.job_file = state_dir / "helixsr-job.json"
        self.releases_cache = state_dir / "helixsr-releases.json"
        self.settings_file = state_dir / "helixsr-settings.json"
        self._lock = threading.Lock()
        self._installer_ready = {}   # tag -> (release folder's mtime, network built, HLX FSR 4 built)
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

    def driver_python(self) -> str:
        """The system's Python for setup_driver.py (standard library only; HelixSR's portable one may not exist yet)."""
        return shutil.which("python3", path="/usr/bin:/bin") or self.python()

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
            out = []
            for r in updates._get(RELEASES_API):
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
        """The newest release games can get: stable ones only, unless the user turned pre-releases on."""
        pre = self.prereleases()
        offered = [r for r in self.releases() if pre or not r["prerelease"]]
        return max(offered, key=lambda r: _version_key(r["tag"])) if offered else None

    def newer_prerelease(self) -> str | None:
        """A pre-release newer than the newest stable release (HelixSR 3.0.0 came out as one), for the hint."""
        rels = self.releases()
        stable = max((_version_key(r["tag"]) for r in rels if not r["prerelease"]), default=())
        pre = [r["tag"] for r in rels if r["prerelease"] and _version_key(r["tag"]) > stable]
        return max(pre, key=_version_key) if pre else None

    def prereleases(self) -> bool:
        return bool((self._read_json(self.settings_file) or {}).get("prereleases"))

    def set_prereleases(self, on: bool) -> dict:
        self._write_json(self.settings_file, {**(self._read_json(self.settings_file) or {}), "prereleases": bool(on)})
        return {"ok": True, "prereleases": bool(on)}

    def local_releases(self) -> list[str]:
        """Downloaded releases (~/HelixSR/<tag>/ with HelixSR's setup), newest first."""
        tags = []
        try:
            for d in self.base.iterdir():
                if (d.is_dir() and _TAG.fullmatch(d.name) and not d.name.endswith(".partial")
                        and ((d / "helixsr-setup.sh").exists() or (d / DLL).exists())):
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

    def opti_release(self) -> str | None:
        """The newest set-up release whose DLL a stock OptiScaler can load: a 1.x one (2.0 has its HelixSR-fsrfg DLL,
        3.0 HelixSR/helixsr.dll, both only for their own HelixSR Scaler)."""
        for tag in self.local_releases():
            if _version_key(tag)[:1] < (2,) and not (self.release_dir(tag) / "HelixSR-fsrfg").exists() \
                    and self.ready(tag):
                return tag
        return None

    def ready(self, tag: str) -> bool:
        """The setup built the upscaling network: found where releases so far put it, else the release's own
        installer is asked (its layout can change between releases)."""
        return self._ask_ready(tag)[0]

    def hlx_ready(self, tag: str) -> bool | None:
        """HLX FSR 4 (HelixSR 3.0's FSR drop-in) is built; None for a release without it."""
        return self._ask_ready(tag)[1]

    def _ask_ready(self, tag: str) -> tuple:
        d = self.release_dir(tag)
        if helix_opti.built_dll(d):
            return True, None
        try:
            mtime = d.stat().st_mtime
        except OSError:
            return False, None
        cached = self._installer_ready.get(tag)
        if cached and cached[0] == mtime:
            return cached[1:]
        ok, hlx = False, None
        if (d / "setup" / "helixsr_install.py").exists():
            try:
                p = subprocess.run([self.python(), "-I", str(BRIDGE), str(d), "ready"], env=self.env(),
                                   stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
                r = json.loads(p.stdout.decode(errors="replace").strip().splitlines()[-1])
                ok, hlx = bool(r.get("ready")), r.get("hlx_ready")
            except (OSError, subprocess.SubprocessError, IndexError, ValueError):
                ok = False
        self._installer_ready[tag] = (mtime, ok, hlx)
        return ok, hlx

    # --- install job: download, verify, extract, run HelixSR's setup ---------------------------------------------

    def status(self) -> dict:
        job = self._read_json(self.job_file) or {}
        if job.get("state") == "running" and not self._job_alive(job):
            job["state"] = "failed" if not job.get("rc_file") or not Path(job["rc_file"]).exists() else (
                "succeeded" if Path(job["rc_file"]).read_text().strip() == "0" else "failed")
            if job["state"] == "succeeded" and job.get("tag") and not self.ready(job["tag"]):
                job["state"] = "failed"
                job["error"] = "The setup ended without building the network. See the setup log below."
            if job["state"] == "failed" and not job.get("error"):
                errors = [l for l in _tail(self.log, 40) if "error:" in l]
                job["error"] = errors[-1].split("error:", 1)[1].strip() if errors else "The setup stopped. See the setup log below."
            self._write_json(self.job_file, job)
        if job.get("state") == "failed" and job.get("phase") == "setup" and job.get("tag") in self.local_releases() \
                and self.ready(job["tag"]):
            # the network was built after all (a release this plugin didn't recognise yet)
            job.update(state="succeeded", error=None)
            self._write_json(self.job_file, job)
        if job.get("phase") == "download" and job.get("state") == "running" and job.get("zip"):
            try:
                job["downloaded"] = Path(job["zip"]).stat().st_size
            except OSError:
                job["downloaded"] = 0
        if job.get("phase") == "setup" and job.get("state") == "running":
            job.update(setup_progress(_tail(self.log, 60)))
        local = self.local_releases()
        latest = self.latest()
        active = self.active()
        active_ready = bool(active and self.ready(active))
        return {
            "job": job or None,
            "log": setup_output(_tail(self.log, 60))[-12:],
            "local": local,
            "active": active,
            "active_ready": active_ready,
            # False: the release has HLX FSR 4 (3.0 on) and its setup didn't build it (AMD's download failed)
            "active_hlx": self.hlx_ready(active) if active_ready else None,
            "latest": latest,
            "update_available": bool(latest and latest["tag"] not in local
                                     and (not active or _version_key(latest["tag"]) > _version_key(active))),
            "prereleases": self.prereleases(),
            "newer_prerelease": self.newer_prerelease(),
        }

    def setup_log(self, lines: int = 80) -> dict:
        return {"path": str(self.log), "lines": _tail(self.log, max(1, min(int(lines), 400)))}

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
        """HelixSR's own setup, unchanged, through setup_driver.py: it answers yes to the downloads the user confirmed
        in the plugin (NVIDIA's DLSS DLL, AMD's driver package for HLX FSR 4) and gives HelixSR's game installer no
        answer after the build, so no game is changed; games are installed one by one from the plugin instead. Not
        --yes: from HelixSR 2.0 the setup passes it to its game installer, which then installs into every game. The
        driver runs detached and records the exit code, so the result is known even if Decky restarts the plugin."""
        rc = self.state_dir / "helixsr-setup.rc"
        rc.unlink(missing_ok=True)
        tmp = self.state_dir / "helixsr-tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        env = self.env()
        env["TMPDIR"] = str(tmp)
        self._log(f"running {d / 'helixsr-setup.sh'}")
        self.log.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen([self.driver_python(), "-I", str(DRIVER), str(self.log), str(rc), "bash",
                                 str(d / "helixsr-setup.sh")], cwd=str(d), env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        job.update(pid=proc.pid, rc_file=str(rc), setup_started=time.time())
        self._write_json(self.job_file, job)
        proc.wait()
        self._installer_ready.clear()   # the setup changed files the cached answers don't see (HLX FSR 4's DLL)
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
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
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


_BAR = re.compile(r"\[helixsr-setup\] \[[#-]+\]\s+(\d+)%\s+\S+\s*(.*)")
_STEP = re.compile(r"\[helixsr-setup\] (?!\[)(.+)")


def setup_progress(lines: list[str]) -> dict:
    """How far HelixSR's setup is, from its output: the network build prints a bar line
    ('[helixsr-setup] [#####---------------]  25%  0:42  fragment tables 3/8'); the steps before it (portable Python,
    NVIDIA's DLL, the shader compiler) print a line each. setup_percent is None until the build starts."""
    pct, stage, step = None, None, None
    for line in lines:
        if line.startswith("[multifg]") and "helixsr-setup.sh" in line:   # this run's start: earlier runs don't count
            pct, stage, step = None, None, None
            continue
        m = _BAR.search(line)
        if m:
            pct, stage = int(m.group(1)), m.group(2).strip() or None
            continue
        m = _STEP.search(line)
        if m and not m.group(1).startswith(("stage seconds", "compile ")):
            step = m.group(1).strip()
            if step.startswith("done"):
                pct, stage = 100, "done"
            elif not step.startswith(("building the network", "HLX FSR 4: its shaders")):
                pct, stage = None, None   # a step after the build started is a new one (done, installing games)
    if pct is not None:
        # HelixSR 3.0 builds HLX FSR 4 after the network, with a bar of its own (AMD's download, then its shaders)
        what = "Building HLX FSR 4" if stage and ("HLX" in stage or "AMD" in stage) else "Building the network"
        return {"setup_percent": pct, "setup_step": f"{what}: {stage}" if stage else what}
    return {"setup_percent": None, "setup_step": step}


def setup_output(lines: list[str]) -> list[str]:
    """The setup's output for the panel: the network build redraws its bar line ('\\r') several times a second,
    so a run of bar lines keeps only its newest; the progress bar above shows the rest."""
    out: list[str] = []
    for line in lines:
        if out and _BAR.search(line) and _BAR.search(out[-1]):
            out[-1] = line
        else:
            out.append(line)
    return out


def _tail(p: Path, n: int) -> list[str]:
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 16384))
            lines = f.read().decode(errors="replace").replace("\r", "\n").splitlines()
        return [l for l in lines if l.strip()][-n:]
    except OSError:
        return []
