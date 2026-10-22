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
        (exe_dir / "libxess.dll").write_bytes(b"the game's own XeSS")   # Cyberpunk ships XeSS
        p = main.Plugin()

        self.assertEqual(run(install_and_wait(p))["state"], "done")
        self.assertTrue(run(p.optiscaler_status())["exists"])
        r = run(p.optiscaler_patch_game("1091500", "dxgi.dll", "-skipStartScreen", ""))
        self.assertEqual(r["status"], "success", r)
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%")
        self.assertTrue((exe_dir / "dxgi.dll").exists())
        self.assertTrue(run(p.optiscaler_game_status("1091500"))["patched"])
        r = run(p.set_game_backend("1091500", "helixsr", r["launch_options"]))   # switching takes OptiScaler out
        self.assertEqual((r["removed"], r["launch_options"]), (["OptiScaler"], "-skipStartScreen"))
        self.assertFalse(run(p.optiscaler_game_status("1091500"))["patched"])
        self.assertEqual(sorted(x.name for x in exe_dir.iterdir()), ["Cyberpunk2077.exe", "libxess.dll"])
        self.assertEqual((exe_dir / "libxess.dll").read_bytes(), b"the game's own XeSS")


class LeftoverTests(unittest.TestCase):
    def setUp(self):
        home = support.reset_home()
        self.steam = home / ".local" / "share" / "Steam"
        support.add_game(self.steam, "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        self.exe_dir = self.steam / "steamapps" / "common" / "Cyberpunk 2077" / "bin" / "x64"
        self.exe_dir.mkdir(parents=True)
        (self.exe_dir / "Cyberpunk2077.exe").write_bytes(b"MZ" + b"\0" * 2048)
        self.fgmod = home / "fgmod"
        self.fgmod.mkdir()
        (self.fgmod / "libxell.dll").write_bytes(b"OptiScaler's XeLL")

    def test_none_puts_the_games_files_back_and_removes_the_rest(self):
        d = self.exe_dir
        (d / "dxgi.dll").write_bytes(b"MZ...OptiScaler build")          # no marker: Framegen's record was gone
        (d / "OptiScaler.ini").write_text("[Upscalers]\n")
        (d / "D3D12_Optiscaler").mkdir()
        (d / "libxess.dll.b").write_bytes(b"game xess")
        (d / "libxess.dll").write_bytes(b"optiscaler xess")
        (d / "libxell.dll").write_bytes(b"OptiScaler's XeLL")             # copied in, the game had none
        (d / "amd_fidelityfx_dx12.dll").write_bytes(b"HelixSR")
        (d / "amd_fidelityfx_dx12.original.dll").write_bytes(b"game fsr")
        (d / "HelixSR-Scaler-backup").mkdir()
        (d / "HelixSR-Scaler-backup" / "version.dll").write_bytes(b"game version")
        (d / "winhttp.dll").write_bytes(b"the game's own winhttp")         # not an OptiScaler build: stays
        r = run(main.Plugin().set_game_backend("1091500", "none", "WINEDLLOVERRIDES=dxgi=n,b %command%"))
        self.assertTrue(r["ok"], r)
        self.assertIn("leftover OptiScaler/HelixSR files", r["removed"])
        self.assertEqual(sorted(x.name for x in d.iterdir()), [
            "Cyberpunk2077.exe", "amd_fidelityfx_dx12.dll", "libxess.dll", "version.dll", "winhttp.dll"])
        self.assertEqual((d / "libxess.dll").read_bytes(), b"game xess")
        self.assertEqual((d / "amd_fidelityfx_dx12.dll").read_bytes(), b"game fsr")
        self.assertEqual((d / "version.dll").read_bytes(), b"game version")

    def test_a_clean_game_is_left_alone(self):
        (self.exe_dir / "libxess.dll").write_bytes(b"game xess")
        r = run(main.Plugin().set_game_backend("1091500", "mako", ""))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["removed"], [])
        self.assertEqual(sorted(x.name for x in self.exe_dir.iterdir()), ["Cyberpunk2077.exe", "libxess.dll"])


if __name__ == "__main__":
    unittest.main()
