import asyncio
import unittest

import support  # noqa: F401

import main


def run(coro):
    return asyncio.run(coro)


GAME_FILES = {
    "Game.exe": b"MZ" + b"\0" * 2048,
    "libxess.dll": b"the game's own XeSS",
    "dxgi.dll": b"the game's own dxgi",
    "nvngx.dll": b"the game's own nvngx",
    "amdxc64.dll": b"the game's own amdxc64",
}


class AutoPatchTests(unittest.TestCase):
    """Choosing Use patches OptiScaler in and out by itself; the game's files come back and no backup is left."""

    def setUp(self):
        home = support.reset_home()
        steam = home / ".local" / "share" / "Steam"
        support.add_game(steam, "4242", "Some Game", "Some Game")
        self.d = steam / "steamapps" / "common" / "Some Game"
        for name, data in GAME_FILES.items():
            (self.d / name).write_bytes(data)
        # a stand-in for Decky Framegen's ~/fgmod
        fgmod = home / "fgmod"
        (fgmod / "fsr4-rdna2-valve-411-pre10").mkdir(parents=True)
        (fgmod / "OptiScaler.dll").write_bytes(b"MZ OptiScaler build")
        (fgmod / "OptiScaler.ini").write_text("[FrameGen]\nEnabled=auto\n")
        (fgmod / "libxess.dll").write_bytes(b"OptiScaler's XeSS")
        (fgmod / "amdxc64.dll").write_bytes(b"OptiScaler's amdxc64")
        (fgmod / "fsr4-rdna2-valve-411-pre10" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"FSR4")

    def files(self):
        return {f.name: f.read_bytes() for f in self.d.iterdir() if f.is_file()}

    def test_choosing_optiscaler_patches_and_off_restores_everything(self):
        p = main.Plugin()
        r = run(p.set_game_backend("4242", "optiscaler", "-foo", "winmm.dll"))
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["opti"]["ok"], r)
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=winmm=n,b SteamDeck=0 %command%")
        self.assertTrue(run(p.optiscaler_game_status("4242"))["patched"])
        f = self.files()
        self.assertEqual(f["winmm.dll"], b"MZ OptiScaler build")
        self.assertEqual(f["libxess.dll"], b"OptiScaler's XeSS")
        # the game's own files are kept aside, also the ones the patch deletes
        for name in ("dxgi.dll", "nvngx.dll", "amdxc64.dll", "libxess.dll"):
            self.assertEqual(f[f"{name}.b"], GAME_FILES[name], name)

        r = run(p.set_game_backend("4242", "none", r["launch_options"]))
        self.assertTrue(r["ok"], r)
        self.assertIn("OptiScaler", r["removed"])
        self.assertEqual(r["launch_options"], "-foo")
        self.assertEqual(self.files(), GAME_FILES)
        self.assertEqual(sorted(x.name for x in self.d.iterdir()), sorted(GAME_FILES))

    def test_the_proxy_dll_is_remembered_and_mako_kept_out_of_the_saved_options(self):
        p = main.Plugin()
        r = run(p.set_game_backend("4242", "optiscaler", "", "version.dll"))
        r = run(p.set_game_backend("4242", "none", r["launch_options"]))
        r = run(p.set_game_backend("4242", "optiscaler+mako", r["launch_options"] or ""))
        self.assertTrue(r["opti"]["ok"], r)
        self.assertEqual(r["opti"]["dll_name"], "version.dll")

    def test_repatching_keeps_the_games_backups(self):
        p = main.Plugin()
        r = run(p.set_game_backend("4242", "optiscaler", ""))
        r2 = run(p.optiscaler_patch_game("4242", "winmm.dll", r["launch_options"]))
        self.assertEqual(r2["status"], "success", r2)
        f = self.files()
        self.assertNotIn("dxgi.dll", f)            # the earlier proxy went, the game's own stays aside
        self.assertEqual(f["dxgi.dll.b"], GAME_FILES["dxgi.dll"])
        run(p.set_game_backend("4242", "none", r2["launch_options"]))
        self.assertEqual(self.files(), GAME_FILES)


class HelixBackupTests(unittest.TestCase):
    def test_backups_helixsr_left_are_put_back_and_deleted(self):
        from pathlib import Path
        from multifg import leftovers
        root = support.reset_home() / "game"
        fsr = root / "Engine" / "Plugins"
        exe = root / "bin"
        fsr.mkdir(parents=True)
        exe.mkdir(parents=True)
        (fsr / "amd_fidelityfx_dx12.original.dll").write_bytes(b"game fsr")
        (exe / "HelixSR-Scaler-backup").mkdir()
        (exe / "HelixSR-Scaler-backup" / "dxgi.dll").write_bytes(b"game dxgi")
        done = []
        for d in leftovers.helix_backup_folders(root, exe):
            done += leftovers.restore_helix_backups(Path(d))
        self.assertEqual(sorted(done), ["amd_fidelityfx_dx12.dll restored", "dxgi.dll restored"])
        self.assertEqual(sorted(x.name for x in fsr.iterdir()), ["amd_fidelityfx_dx12.dll"])
        self.assertEqual(sorted(x.name for x in exe.iterdir()), ["dxgi.dll"])


if __name__ == "__main__":
    unittest.main()
