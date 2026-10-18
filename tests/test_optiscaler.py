import asyncio
import os
import shutil
import unittest

import support  # noqa: F401

import main

# Downloads OptiScaler and its FSR4 files from upstream (a few hundred MB) and needs 7z: opt-in.
NETWORK = os.environ.get("MULTIFG_NETWORK_TESTS") == "1" and shutil.which("7z")


def run(coro):
    return asyncio.run(coro)


async def install_and_wait(p, variant=""):
    started = await p.optiscaler_install(variant)
    if started["status"] != "started":
        return started
    while (job := (await p.optiscaler_status())["job"])["state"] == "running":
        await asyncio.sleep(0.2)
    return job


class InstallJobTests(unittest.TestCase):
    def test_reports_download_progress_then_the_result(self):
        from multifg import opti_job

        class FakeOpti:
            async def run_install_fgmod(self, variant):
                return {"status": "success", "output": f"installed {variant}"}

        seen = []

        def fake_ensure(progress):
            progress({"name": "a.7z", "size": 10}, None)
            job.status()  # mid-download reads must work
            progress({"name": "b.dll", "size": 5}, None)
            seen.append(job.status()["downloaded"])

        async def go():
            await asyncio.sleep(0)
            self.assertEqual(job.start("x")["status"], "started")
            self.assertEqual(job.start("x")["status"], "error")   # one install at a time
            while job.running():
                await asyncio.sleep(0.01)
            return job.status()

        job = opti_job.OptiInstallJob(FakeOpti())
        original = opti_job.ensure_binaries
        opti_job.ensure_binaries = fake_ensure
        try:
            result = asyncio.run(go())
        finally:
            opti_job.ensure_binaries = original
        self.assertEqual(seen, [15])
        self.assertEqual((result["state"], result["message"]), ("done", "installed x"))


@unittest.skipUnless(NETWORK, "set MULTIFG_NETWORK_TESTS=1 (and have 7z) to run the OptiScaler install end to end")
class OptiScalerEndToEnd(unittest.TestCase):
    def test_install_patch_unpatch(self):
        home = support.reset_home()
        steam = home / ".local" / "share" / "Steam"
        support.add_game(steam, "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        exe_dir = steam / "steamapps" / "common" / "Cyberpunk 2077" / "bin" / "x64"
        exe_dir.mkdir(parents=True)
        (exe_dir / "Cyberpunk2077.exe").write_bytes(b"MZ" + b"\0" * 2048)
        p = main.Plugin()

        self.assertEqual(run(install_and_wait(p))["state"], "done")
        self.assertTrue(run(p.optiscaler_status())["exists"])
        r = run(p.optiscaler_patch_game("1091500", "dxgi.dll", "-skipStartScreen", ""))
        self.assertEqual(r["status"], "success", r)
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%")
        self.assertTrue((exe_dir / "dxgi.dll").exists())
        self.assertTrue(run(p.optiscaler_game_status("1091500"))["patched"])
        r = run(p.optiscaler_unpatch_game("1091500"))
        self.assertEqual(r["launch_options"], "-skipStartScreen")
        self.assertEqual([x.name for x in exe_dir.iterdir()], ["Cyberpunk2077.exe"])


if __name__ == "__main__":
    unittest.main()
