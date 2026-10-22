import json
import os
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

import support  # noqa: F401

from multifg import helixsr
from multifg.helixsr import HelixSR

# A real HelixSR release folder (extracted official zip) for the end-to-end installer tests; skipped without one.
# The release's DLL is copied and a test-only network marker appended, so no setup has to run.
REAL_RELEASE = os.environ.get("HELIXSR_RELEASE_DIR")


def make_helix(home: Path) -> HelixSR:
    return HelixSR(home, support.ROOT / "runtime", support.ROOT / "logs", "deck")


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()

    def zip_with(self, entries):
        p = support.ROOT / "r.zip"
        with zipfile.ZipFile(p, "w") as z:
            for name, data in entries:
                z.writestr(name, data)
        return p

    def test_drops_the_top_folder_and_makes_scripts_executable(self):
        z = self.zip_with([("HelixSR-1.9.3/helixsr-setup.sh", "#!/bin/bash\n"), ("HelixSR-1.9.3/setup/a.py", "")])
        helixsr._extract(z, self.home / "out")
        self.assertTrue((self.home / "out" / "setup" / "a.py").exists())
        self.assertTrue(os.access(self.home / "out" / "helixsr-setup.sh", os.X_OK))

    def test_refuses_paths_outside_the_target(self):
        z = self.zip_with([("../evil.txt", "x"), ("ok.txt", "y")])
        with self.assertRaises(RuntimeError):
            helixsr._extract(z, self.home / "out")
        self.assertFalse((self.home / "evil.txt").exists())

    def test_picks_helixsrs_own_zip(self):
        assets = [{"name": "HelixSR-Desktop-1.0.3.zip"}, {"name": "HelixSR-Scaler-1.0.6.zip"},
                  {"name": "HelixSR-1.9.3.zip"}]
        self.assertEqual(helixsr._release_zip(assets)["name"], "HelixSR-1.9.3.zip")


class ReleaseStateTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        self.h = make_helix(self.home)

    def add_release(self, tag, built):
        d = self.home / "HelixSR" / tag
        d.mkdir(parents=True)
        (d / helixsr.DLL).write_bytes(b"MZ" + (b"HXSRNET1" + b"\0" * 24 if built else b"\0" * 32))
        return d

    def test_active_prefers_the_newest_built_release(self):
        self.add_release("v1.8.1", built=True)
        self.add_release("v1.9.3", built=False)
        self.assertEqual(self.h.local_releases(), ["v1.9.3", "v1.8.1"])
        self.assertEqual(self.h.active(), "v1.8.1")
        self.assertFalse(self.h.ready("v1.9.3"))

    def test_rejects_bad_tags(self):
        with self.assertRaises(ValueError):
            self.h.release_dir("../x")

    def test_finished_setup_is_recorded(self):
        self.add_release("v1.9.3", built=True)
        rc = support.ROOT / "runtime" / "helixsr-setup.rc"
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text("0\n")
        self.h._write_json(self.h.job_file, {"state": "running", "phase": "setup", "tag": "v1.9.3",
                                             "pid": 999999999, "rc_file": str(rc)})
        self.assertEqual(self.h.status()["job"]["state"], "succeeded")

    def test_setup_that_built_nothing_is_a_failure(self):
        self.add_release("v1.9.3", built=False)
        rc = support.ROOT / "runtime" / "helixsr-setup.rc"
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text("0\n")
        self.h._write_json(self.h.job_file, {"state": "running", "phase": "setup", "tag": "v1.9.3",
                                             "pid": 999999999, "rc_file": str(rc)})
        job = self.h.status()["job"]
        self.assertEqual(job["state"], "failed")
        self.assertIn("network", job["error"])

    def test_helixsr_2_setup_recognised_and_earlier_failure_cleared(self):
        # 2.0 builds into HelixSR-fsrfg; an earlier plugin version recorded that setup as failed
        d = self.add_release("v2.0.0", built=False)
        (d / "helixsr-setup.sh").write_text("")
        (d / "HelixSR-fsrfg").mkdir()
        (d / "HelixSR-fsrfg" / helixsr.DLL).write_bytes(b"MZ" + b"HXSRNET1" + b"\0" * 24)
        self.h._write_json(self.h.job_file, {"state": "failed", "phase": "setup", "tag": "v2.0.0",
                                             "error": "The setup ended without building the network."})
        st = self.h.status()
        self.assertEqual((st["job"]["state"], st["active"], st["active_ready"]), ("succeeded", "v2.0.0", True))

    def test_optiscaler_gets_the_newest_1x_release(self):
        self.add_release("v1.9.3", built=True)
        d = self.add_release("v2.0.0", built=False)
        (d / "HelixSR-fsrfg").mkdir()
        (d / "HelixSR-fsrfg" / helixsr.DLL).write_bytes(b"MZ" + b"HXSRNET1" + b"\0" * 24)
        self.assertEqual((self.h.active(), self.h.opti_release()), ("v2.0.0", "v1.9.3"))

    def test_no_release_for_optiscaler_with_only_2_0(self):
        d = self.add_release("v2.0.0", built=False)
        (d / "HelixSR-fsrfg").mkdir()
        (d / "HelixSR-fsrfg" / helixsr.DLL).write_bytes(b"MZ" + b"HXSRNET1" + b"\0" * 24)
        self.assertIsNone(self.h.opti_release())

    def test_download_interrupted_by_a_restart_is_a_failure(self):
        self.h._write_json(self.h.job_file, {"state": "running", "phase": "download", "tag": "v1.9.3"})
        self.assertEqual(self.h.status()["job"]["state"], "failed")


class SetupProgressTests(unittest.TestCase):
    def test_reads_the_steps_and_the_build_bar(self):
        sp = helixsr.setup_progress
        old = ["[helixsr-setup] [####################]  100%  2:42  done", "[multifg] 10:00:00 running /x/helixsr-setup.sh --yes"]
        self.assertEqual(sp(old + ["[helixsr-setup] downloading nvngx_dlss.dll from NVIDIA"]),
                         {"setup_percent": None, "setup_step": "downloading nvngx_dlss.dll from NVIDIA"})
        build = old + ["[helixsr-setup] building the network (about two minutes)",
                       "[helixsr-setup] [#####---------------]   25%  0:42  fragment tables 3/8",
                       "[helixsr-setup] compile k1 2.0 s"]
        self.assertEqual(sp(build), {"setup_percent": 25, "setup_step": "Building the network: fragment tables 3/8"})
        self.assertEqual(sp(build + ["[helixsr-setup] done: the network is built"])["setup_percent"], 100)


def fake_exe(imports):
    """A minimal 64-bit Windows .exe whose import table lists these DLLs."""
    import struct
    b = bytearray(0x400)
    b[:2] = b"MZ"
    struct.pack_into("<I", b, 0x3C, 0x40)
    b[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HH", b, 0x44 + 2, 1, 0)        # one section
    struct.pack_into("<H", b, 0x44 + 16, 240)          # optional header size
    opt = 0x58
    struct.pack_into("<H", b, opt, 0x20B)
    struct.pack_into("<II", b, opt + 112 + 8, 0x1000, 20 * (len(imports) + 1))
    struct.pack_into("<IIII", b, opt + 240 + 8, 0x200, 0x1000, 0x200, 0x200)
    names = 0x1000 + 20 * (len(imports) + 1)
    for k, name in enumerate(imports):
        struct.pack_into("<I", b, 0x200 + 20 * k + 12, names)
        raw = 0x200 + names - 0x1000
        b[raw:raw + len(name) + 1] = name.encode() + b"\0"
        names += len(name) + 1
    return bytes(b)


@unittest.skipUnless(REAL_RELEASE, "set HELIXSR_RELEASE_DIR to an extracted official HelixSR release")
class InstallerBridgeTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        rel = self.home / "HelixSR" / "v1.9.3"
        shutil.copytree(REAL_RELEASE, rel)
        with open(rel / helixsr.DLL, "ab") as f:
            f.write(b"HXSRNET1" + b"\0" * 24)   # test only: pretend the setup built the network
        self.h = make_helix(self.home)
        common = self.home / "steamapps" / "common"
        self.fsr = common / "FSR Game"
        (self.fsr / "Bin").mkdir(parents=True)
        (self.fsr / "Bin" / "Game.exe").write_bytes(b"MZ")
        (self.fsr / "Bin" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"ORIGINAL")
        self.dlss = common / "DLSS Game"
        self.dlss.mkdir(parents=True)
        (self.dlss / "Game.exe").write_bytes(b"MZ")
        (self.dlss / "nvngx_dlss.dll").write_bytes(b"x")

    def test_fsr_drop_in_round_trip(self):
        st = self.h.game_status(str(self.fsr))
        self.assertEqual((st["route"], st["installed"]), ("direct", False))
        r = self.h.install_game(str(self.fsr))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["current"], "direct")
        self.assertEqual(r["in_game"], "AMD FSR")
        r = self.h.uninstall_game(str(self.fsr))
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.fsr / "Bin" / "amd_fidelityfx_upscaler_dx12.dll").read_bytes(), b"ORIGINAL")

    def test_scaler_for_a_dlss_game(self):
        r = self.h.install_game(str(self.dlss))
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["current"], r["scaler_name"]), ("scaler", "dxgi.dll"))
        self.assertIsNone(r["launch_options"])   # Proton loads a game's own dxgi.dll by itself
        self.assertFalse(self.h.install_game(str(self.dlss), "direct")["ok"])
        self.assertTrue(self.h.uninstall_game(str(self.dlss))["ok"])
        self.assertEqual(sorted(p.name for p in self.dlss.iterdir()), ["Game.exe", "nvngx_dlss.dll"])

    def test_vulkan_game_and_helixsrs_log(self):
        (self.fsr / "Bin" / "Game.exe").write_bytes(fake_exe(["kernel32.dll", "vulkan-1.dll"]))
        st = self.h.game_status(str(self.fsr))
        self.assertEqual(st["graphics"], "vulkan")
        self.assertIsNone(st["runtime_log"])
        self.assertTrue(self.h.install_game(str(self.fsr))["ok"])
        (self.fsr / "Bin" / "helixsr.log").write_text("HelixSR 1.9.3 loaded\nupscaling 1280x800\n")
        st = self.h.game_status(str(self.fsr))
        self.assertEqual(st["runtime_log"]["lines"], ["HelixSR 1.9.3 loaded", "upscaling 1280x800"])
        (self.fsr / "Bin" / "Game.exe").write_bytes(fake_exe(["vulkan-1.dll", "d3d12.dll"]))
        self.assertIsNone(self.h.game_status(str(self.fsr))["graphics"])

    def test_switching_the_game_to_optiscaler_takes_helixsr_out(self):
        import asyncio
        import main
        steam = self.home / ".local" / "share" / "Steam"
        support.add_game(steam, "123", "DLSS Game", "DLSS Game", create_dir=False)
        game = steam / "steamapps" / "common" / "DLSS Game"
        shutil.copytree(self.dlss, game)
        (game / "dxgi.dll").write_bytes(b"the game's own")   # so HelixSR Scaler needs WINEDLLOVERRIDES
        p = main.Plugin()
        r = asyncio.run(p.helixsr_install_game("123", "", "-dx12"))
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["launch_options"])
        launch = f'{r["launch_options"].replace(" %command%", "")} %command% -dx12'
        r = asyncio.run(p.set_game_backend("123", "optiscaler", launch))
        self.assertEqual((r["ok"], r["removed"], r["launch_options"]), (True, ["HelixSR"], "-dx12"))
        self.assertFalse(asyncio.run(p.helixsr_game_status("123"))["installed"])
        r = asyncio.run(p.set_game_backend("123", "none", "-dx12"))
        self.assertEqual((r["removed"], r["launch_options"]), ([], None))

    def test_remove_takes_helixsr_out_of_games_then_deletes_it(self):
        self.assertTrue(self.h.install_game(str(self.fsr))["ok"])
        (self.home / ".local" / "share" / "HelixSR").mkdir(parents=True)
        r = self.h.remove([str(self.fsr), str(self.dlss)])
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["removed"], ["FSR Game"])
        self.assertEqual((self.fsr / "Bin" / "amd_fidelityfx_upscaler_dx12.dll").read_bytes(), b"ORIGINAL")
        self.assertFalse((self.home / "HelixSR").exists())
        self.assertFalse((self.home / ".local" / "share" / "HelixSR").exists())
        self.assertIsNone(self.h.active())

    def test_not_ready_refuses_to_install(self):
        dll = self.home / "HelixSR" / "v1.9.3" / helixsr.DLL
        dll.write_bytes(dll.read_bytes()[:-32])
        self.assertFalse(self.h.install_game(str(self.fsr))["ok"])


if __name__ == "__main__":
    unittest.main()
