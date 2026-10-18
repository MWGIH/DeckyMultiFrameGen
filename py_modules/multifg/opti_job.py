"""Installing OptiScaler in the background: its downloads come to ~325 MB, too long to keep a call from the panel waiting.
status() reports the progress, which the panel polls."""
import asyncio
import json
import time
from pathlib import Path

import decky

from multifg.optiscaler import ASSETS_DIR, ensure_binaries


class OptiInstallJob:
    def __init__(self, optiscaler):
        self.optiscaler = optiscaler
        self.job: dict | None = None
        self._task: asyncio.Task | None = None
        self._part: Path | None = None
        self._done_bytes = 0

    def running(self) -> bool:
        return bool(self.job and self.job["state"] == "running")

    def start(self, variant: str | None) -> dict:
        if self.running():
            return {"status": "error", "message": "OptiScaler is already being installed"}
        self.job = {"state": "running", "phase": "download", "asset": None, "downloaded": 0, "size": 0,
                    "started": time.time(), "message": None}
        self._part, self._done_bytes = None, 0
        self._task = asyncio.get_running_loop().create_task(self._run(variant))
        return {"status": "started"}

    def status(self) -> dict | None:
        if not self.job:
            return None
        job = dict(self.job)
        if job["state"] == "running" and job["phase"] == "download":
            part = 0
            try:
                part = self._part.stat().st_size if self._part else 0
            except OSError:
                pass
            job["downloaded"] = self._done_bytes + part
        return job

    def _progress(self, asset: dict, part: Path | None):
        if part is None:
            self._done_bytes += asset.get("size", 0)
        self._part = part
        self.job["asset"] = asset["name"]

    async def _run(self, variant):
        job = self.job
        try:
            job["size"] = sum(a.get("size", 0) for a in json.loads((ASSETS_DIR / "remote_binary.json").read_text()))
            await asyncio.to_thread(ensure_binaries, self._progress)
            job["phase"] = "install"
            result = await self.optiscaler.run_install_fgmod(variant)
            ok = result.get("status") == "success"
            job.update(state="done" if ok else "failed", message=result.get("output") if ok else result.get("message"))
        except Exception as exc:  # reported in the panel
            decky.logger.exception("OptiScaler install")
            job.update(state="failed", message=str(exc))
        finally:
            self._part = None
