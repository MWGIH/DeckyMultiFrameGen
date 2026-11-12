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

REPO = "lonewolf0622/HelixSR"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
RELEASES_TTL = 3600          # seconds between GitHub checks
RELEASES_PAGES = 2           # github.com lists 10 releases a page: the newest 20, like RELEASES_API
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,40}")
BRIDGE = Path(__file__).resolve().parent / "helix_bridge.py"
DRIVER = Path(__file__).resolve().parent / "setup_driver.py"
DLL = "amd_fidelityfx_dx12.dll"
# The newest HelixSR that runs inside a stock OptiScaler (the one Decky Framegen installs): HelixSR 2.0's DLL needs its
# own OptiScaler build, HelixSR Scaler 1.1.0 (its Dx12Upscaler=ffx); stock OptiScaler 0.9.4 falls back to FSR 2.1.2
OPTI_RELEASE = "v1.9.3"
# Optional extras HelixSR's setup builds on request (HelixSR 3.3 on), each with a switch in Backends:
# preset_k: NVIDIA's DLSS 4 Preset K network for HLX DLSS (--preset-k; built into <release>/HelixSR/k, which HelixSR's
#           installer puts into games next to HelixSR); vulkan: HLX DLSS's Vulkan kernels, so it runs natively in
#           Vulkan games (--vulkan; part of the network's build, so adding or dropping them rebuilds it: --rebuild)
EXTRAS = ("preset_k", "vulkan")
K_FILES = ("helixsr.dll", "helixsr_modelk_kernels.pak", "helixsr_modelk_weights.bin")
K_TOTAL = 31   # Preset K's shaders in HelixSR 3.3.0 (setup/lib/modelk/modelk_kernels.json), when a release doesn't say


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
        """Published HelixSR releases with their zip, newest first (cached; the cache is used offline or when GitHub
        refuses). Read from github.com's release pages, which the API's hourly limit doesn't cover; the API only when
        those pages can't be read."""
        cached = self._read_json(self.releases_cache) or {}
        if not refresh and cached.get("checked", 0) > time.time() - RELEASES_TTL:
            return cached.get("releases", [])
        try:
            try:
                out = self._releases_from_pages(cached)
            except Exception:
                out = self._releases_from_api()
            out.sort(key=lambda r: r["published_at"] or "", reverse=True)
            self._write_json(self.releases_cache, {"checked": time.time(), "releases": out})
            return out
        except Exception:
            return cached.get("releases", [])

    def _releases_from_pages(self, cached: dict) -> list[dict]:
        """The releases list page says which releases there are and which are pre-releases; a release's files are
        read once from its own file list and kept (a published release's zip doesn't change)."""
        known = {r["tag"]: r for r in cached.get("releases", []) if r.get("url")}
        out = []
        for r in updates.release_list(REPO, pages=RELEASES_PAGES):
            tag = r["tag"]
            if not _TAG.fullmatch(tag):
                continue
            if tag in known:
                out.append({**known[tag], "prerelease": r["prerelease"],
                            "published_at": r["published_at"] or known[tag].get("published_at")})
                continue
            asset = _release_zip(updates.release_assets(REPO, tag))
            if asset:
                out.append(_release_entry(tag, asset, r["prerelease"], r["published_at"]))
        return out

    def _fresh_release(self, tag: str) -> dict | None:
        """The release's zip as GitHub lists it now (not the cache), stored in the cache when it differs: an
        upstream release can have its zip replaced after it was published."""
        try:
            try:
                asset = _release_zip(updates.release_assets(REPO, tag))
            except Exception:
                asset = _release_zip(updates._get(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}")
                                     .get("assets", []))
        except Exception:
            return None
        if not asset:
            return None
        cached = self._read_json(self.releases_cache) or {}
        rels = cached.get("releases", [])
        old = next((r for r in rels if r["tag"] == tag), None)
        fresh = _release_entry(tag, asset, bool(old and old.get("prerelease")), old and old.get("published_at"))
        if old and old != fresh:
            cached["releases"] = [fresh if r["tag"] == tag else r for r in rels]
            self._write_json(self.releases_cache, cached)
        return fresh

    def _releases_from_api(self) -> list[dict]:
        out = []
        for r in updates._get(RELEASES_API):
            asset = _release_zip(r.get("assets", []))
            if r.get("draft") or not asset or not _TAG.fullmatch(r.get("tag_name") or ""):
                continue
            out.append(_release_entry(r["tag_name"], asset, bool(r.get("prerelease")), r.get("published_at")))
        return out

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

    # --- optional extras: Preset K and the Vulkan kernels ---------------------------------------------------------

    def extras_wanted(self) -> dict:
        settings = self._read_json(self.settings_file) or {}
        return {k: bool(settings.get(k)) for k in EXTRAS}

    def extra_available(self, tag: str | None, name: str) -> bool:
        """The release's setup can build it (HelixSR 3.3 on)."""
        if not tag:
            return False
        d = self.release_dir(tag)
        if name == "preset_k":
            return (d / "setup" / "preset-k" / "out_lo.bin").is_file()
        return (d / "setup" / "lib" / "setup_vk_shaders.py").is_file()

    def extra_built(self, tag: str | None, name: str) -> bool:
        if not tag:
            return False
        d = self.release_dir(tag)
        if name == "preset_k":
            return all((d / "HelixSR" / "k" / n).is_file() for n in K_FILES)
        return bool((self._read_json(d / "helixsr_setup.json") or {}).get("vulkan"))

    def k_total(self, tag: str | None) -> int:
        try:
            return len(json.loads((self.release_dir(tag) / "setup" / "lib" / "modelk" / "modelk_kernels.json")
                                  .read_text())["kernels"]) or K_TOTAL
        except (OSError, ValueError, KeyError, TypeError):
            return K_TOTAL

    def setup_args(self, tag: str) -> list[str]:
        """helixsr-setup.sh's options for the extras switched on. The Vulkan kernels are part of the network's build:
        when the built network has them and they're switched off, or the other way round, it is built again."""
        want = self.extras_wanted()
        args = []
        if want["preset_k"] and self.extra_available(tag, "preset_k"):
            args.append("--preset-k")
        if self.extra_available(tag, "vulkan"):
            if want["vulkan"]:
                args.append("--vulkan")
            if self.ready(tag) and want["vulkan"] != self.extra_built(tag, "vulkan"):
                args.append("--rebuild")
        return args

    def extras_status(self, tag: str | None) -> dict:
        want = self.extras_wanted()
        return {k: {"on": want[k], "available": self.extra_available(tag, k), "built": self.extra_built(tag, k)}
                for k in EXTRAS}

    def set_extra(self, name: str, on: bool) -> dict:
        """Switches an extra on or off. With HelixSR set up, its setup runs again at once to build (or, for the Vulkan
        kernels, rebuild without) it; Preset K switched off is taken out of the release (games get it no more when
        HelixSR is installed into them again). Without HelixSR set up, the switch applies when it is installed."""
        if name not in EXTRAS:
            return {"ok": False, "error": f"Unknown option: {name}"}
        job = self.status().get("job") or {}
        if job.get("state") == "running":
            return {"ok": False, "error": "Wait for HelixSR's setup to finish."}
        self._write_json(self.settings_file, {**(self._read_json(self.settings_file) or {}), name: bool(on)})
        tag = self.active()
        started = False
        if tag and self.ready(tag) and self.extra_available(tag, name):
            if name == "preset_k" and not on:
                shutil.rmtree(self.release_dir(tag) / "HelixSR" / "k", ignore_errors=True)
                self._log("Preset K switched off: removed from the release")
            elif bool(on) != self.extra_built(tag, name):
                r = self.start_install(tag)
                if not r.get("ok"):
                    return r
                started = True
        return {"ok": True, "started": started, "extras": self.extras_status(tag)}

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
            lines = _tail(self.log, 400, 65536)
            job.update(setup_progress(lines[-60:]))
            job["extras_progress"] = extras_progress(lines, job.get("k_total") or K_TOTAL)
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
            "extras": self.extras_status(active),
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
                    got = _sha256(zip_path)
                    if got != rel["sha256"]:
                        # the kept checksum can be stale: the release's zip was replaced after it was read
                        fresh = self._fresh_release(rel["tag"])
                        self._log(f"checksum {got} isn't the kept {rel['sha256']}; GitHub now says "
                                  f"{(fresh or {}).get('sha256')}")
                        if not fresh or fresh.get("sha256") != got:
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
        args = self.setup_args(d.name)
        # the extras this run builds, each with its own bar in the panel
        job.update(extras=[n for n, flag in (("vulkan", "--vulkan"), ("preset_k", "--preset-k")) if flag in args],
                   k_total=self.k_total(d.name))
        self._log(f"running {d / 'helixsr-setup.sh'}" + (f" {' '.join(args)}" if args else ""))
        self.log.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen([self.driver_python(), "-I", str(DRIVER), str(self.log), str(rc), "bash",
                                 str(d / "helixsr-setup.sh"), *args], cwd=str(d), env=env, stdin=subprocess.DEVNULL,
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


def _release_entry(tag: str, asset: dict, prerelease: bool, published_at: str | None) -> dict:
    digest = asset.get("digest") or ""
    return {
        "tag": tag, "name": asset["name"], "url": asset["browser_download_url"], "size": asset.get("size"),
        "prerelease": bool(prerelease), "published_at": published_at,
        "sha256": digest[7:].lower() if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) else None,
    }


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
        if m and not m.group(1).startswith(("stage seconds", "compile ", "Vulkan: ")):
            step = m.group(1).strip()
            if step.startswith("done"):
                pct, stage = 100, "done"
            elif not step.startswith(("building the network", "HLX FSR 4: its shaders")):
                pct, stage = None, None   # a step after the build started is a new one (done, installing games)
    if pct is not None and stage == "done":
        pct = 100   # the bar's last line with the Vulkan kernels' share in it
    if pct is not None:
        # HelixSR 3.0 builds HLX FSR 4 after the network, with a bar of its own (AMD's download, then its shaders)
        what = ("Building HLX FSR 4" if stage and ("HLX" in stage or "AMD" in stage)
                else "Building the Vulkan kernels" if stage and stage.startswith("Vulkan") else "Building the network")
        return {"setup_percent": pct, "setup_step": f"{what}: {stage}" if stage else what}
    return {"setup_percent": None, "setup_step": step}


_VK = re.compile(r"Vulkan shaders (\d+)/(\d+)")
_K_SHADER = re.compile(r"^[A-Za-z_]\w* (compiled|cached)$")
_K_TRANSLATED = re.compile(r"^[A-Za-z_]\w*: ")


def extras_progress(lines: list[str], k_total: int = K_TOTAL) -> dict:
    """How far the optional extras are in this run, from the setup's output:
    vulkan: HelixSR 3.3's build bar has a stage of its own after the network's shaders ('Vulkan shaders 120/352'),
            then a step line ('Vulkan: 352 shaders');
    preset_k: a step line starts it ('building Preset K ...' or 'Preset K: reusing the earlier build'), its builder
            prints a line per shader translated ('<kernel>: ...') and one per shader compiled ('<kernel> compiled'),
            and a step line ends it ('done: Preset K is built' or 'Preset K was not built ...').
    Each is {percent (None: not started or no measure yet), step, state: waiting|building|done|failed}."""
    vk = {"percent": None, "step": "Waits for the network's build", "state": "waiting"}
    k = {"percent": None, "step": "Waits for the network's build", "state": "waiting"}
    in_k, translated, compiled = False, 0, 0
    starts = [i for i, l in enumerate(lines) if l.startswith("[multifg]") and "helixsr-setup.sh" in l]
    for line in lines[starts[-1] + 1:] if starts else lines:   # this run's output only
        m = _BAR.search(line)
        if m and (m.group(2) or "").strip().startswith("Vulkan"):
            label = m.group(2).strip()
            v = _VK.search(label)
            if v and int(v.group(2)):
                vk = {"percent": round(100 * int(v.group(1)) / int(v.group(2))),
                      "step": f"Vulkan shaders {v.group(1)}/{v.group(2)}", "state": "building"}
            elif "done" in label:
                vk = {"percent": 100, "step": "Built", "state": "done"}
            else:
                vk = {**vk, "step": label, "state": "building"}
            continue
        m = _STEP.search(line)
        step = m.group(1).strip() if m else None
        if step and step.startswith("Vulkan: "):
            vk = {"percent": 100, "step": f"Built ({step[8:]})", "state": "done"}
            continue
        if step and step.startswith("building Preset K"):
            in_k, translated, compiled = True, 0, 0
            k = {"percent": 0, "step": "Starting", "state": "building"}
            continue
        if step and step.startswith("Preset K: reusing"):
            k = {"percent": 100, "step": "Reused the earlier build on this Deck", "state": "building"}
            continue
        if step and step.startswith("done: Preset K is built"):
            in_k = False
            k = {"percent": 100, "step": "Built", "state": "done"}
            continue
        if "Preset K was not built" in line or "Preset K is not in this package" in line:
            in_k = False
            k = {"percent": k["percent"], "step": line.split("] ", 1)[-1].strip(), "state": "failed"}
            continue
        if in_k and not line.startswith("["):
            text = line.strip()
            if _K_SHADER.match(text):
                compiled += 1
                k = {"percent": min(99, round(100 * compiled / max(1, k_total))),
                     "step": f"Shaders {compiled}/{k_total}", "state": "building"}
            elif _K_TRANSLATED.match(text):
                translated += 1
                k = {"percent": 0, "step": f"Translating NVIDIA's network {min(translated, k_total)}/{k_total}",
                     "state": "building"}
    return {"vulkan": vk, "preset_k": k}


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


def _tail(p: Path, n: int, size: int = 16384) -> list[str]:
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - size))
            lines = f.read().decode(errors="replace").replace("\r", "\n").splitlines()
        return [l for l in lines if l.strip()][-n:]
    except OSError:
        return []
