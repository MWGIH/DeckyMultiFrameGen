import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401

from multifg import leftovers


class SweepTests(unittest.TestCase):
    """The sweep takes out only what OptiScaler or HelixSR left, never files the game shipped itself."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.d = root / "game"
        self.fgmod = root / "fgmod"
        self.d.mkdir()
        self.fgmod.mkdir()
        # the same stock AMD/XeSS DLLs in the game and in Decky Framegen's install (as with Crimson Desert)
        for name in ("amd_fidelityfx_dx12.dll", "amd_fidelityfx_framegeneration_dx12.dll", "libxess.dll"):
            (self.d / name).write_bytes(b"stock " + name.encode())
            (self.fgmod / name).write_bytes(b"stock " + name.encode())
        (self.d / "nvngx.ini").write_text("the game's own")

    def tearDown(self):
        self.tmp.cleanup()

    def test_game_without_optiscaler_keeps_its_files(self):
        self.assertEqual(leftovers.sweep(self.d, self.fgmod), [])
        for name in ("amd_fidelityfx_dx12.dll", "amd_fidelityfx_framegeneration_dx12.dll", "libxess.dll",
                     "nvngx.ini"):
            self.assertTrue((self.d / name).is_file(), name)

    def test_optiscaler_leftovers_go(self):
        (self.d / "OptiScaler.ini").write_text("[FrameGen]\n")
        (self.d / "dxgi.dll").write_bytes(b"MZ OptiScaler build")
        (self.d / "libxess.dll.b").write_bytes(b"the game's older XeSS")
        done = leftovers.sweep(self.d, self.fgmod)
        self.assertIn("dxgi.dll removed", done)
        self.assertFalse((self.d / "OptiScaler.ini").exists())
        self.assertFalse((self.d / "amd_fidelityfx_dx12.dll").exists())
        self.assertEqual((self.d / "libxess.dll").read_bytes(), b"the game's older XeSS")

    def test_helixsr_leftovers_go_without_optiscaler(self):
        (self.d / "HelixSR").mkdir()
        (self.d / "HelixSR" / "helixsr.dll").write_bytes(b"x")
        self.assertEqual(leftovers.sweep(self.d, self.fgmod), ["HelixSR removed"])
        self.assertTrue((self.d / "amd_fidelityfx_dx12.dll").is_file())


if __name__ == "__main__":
    unittest.main()
