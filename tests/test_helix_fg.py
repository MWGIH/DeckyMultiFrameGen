import io
import struct
import unittest
import zipfile
from unittest import mock

import support

from multifg import helix_fg, helix_opti

INI = ("[FrameGen]\r\nEnabled=auto\r\nFGInput = auto\r\nFGNvngxReplacement=auto\r\n\r\n"
       "[Spoofing]\r\nDxgi=auto\r\nSpoofHAGS=auto\r\n\r\n[Plugins]\r\nLoadAsiPlugins=true\r\n")


def dll(version: str) -> bytes:
    a, b, c = (int(x) for x in version.split("."))
    return b"MZ" + struct.pack("<IIII", 0xFEEF04BD, 0x10000, (a << 16) | b, c << 16) + b"\0" * 16


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.game = support.reset_home() / "game"
        (self.game / "OptiScaler").mkdir(parents=True)
        (self.game / "OptiScaler.ini").write_bytes(INI.encode())

    def test_on_sets_everything_and_off_puts_the_earlier_values_back(self):
        self.assertTrue(helix_fg.switch(self.game, True))
        text = (self.game / "OptiScaler.ini").read_text(newline="")
        for (s, k), v in helix_fg.SETTINGS.items():
            self.assertEqual(helix_opti.ini_get(text, s, k), v)
        self.assertIn("FGInput = NvngxFG\r\n", text)   # OptiScaler's spaced style stays

        self.assertFalse(helix_fg.switch(self.game, False))
        self.assertEqual((self.game / "OptiScaler.ini").read_text(newline=""), INI)
        self.assertFalse((self.game / helix_fg.RECORD).exists())

    def test_off_leaves_values_changed_by_hand(self):
        helix_fg.switch(self.game, True)
        ini = self.game / "OptiScaler.ini"
        ini.write_text(helix_opti.ini_set(ini.read_text(newline=""), "Spoofing", "Dxgi", "false"), newline="")
        helix_fg.switch(self.game, False)
        self.assertEqual(helix_opti.ini_get(ini.read_text(newline=""), "Spoofing", "Dxgi"), "false")

    def test_frame_generation_switched_off_for_mako_comes_back_and_goes_off_again(self):
        ini = self.game / "OptiScaler.ini"
        off = helix_opti.ini_set(INI.replace("Enabled=auto", "Enabled=false"), "FrameGen", "FGOutput", "nofg")
        ini.write_text(off, newline="")
        helix_fg.switch(self.game, True)
        text = ini.read_text(newline="")
        self.assertEqual(helix_opti.ini_get(text, "FrameGen", "Enabled"), "auto")
        self.assertEqual(helix_opti.ini_get(text, "FrameGen", "FGOutput"), "auto")
        helix_fg.switch(self.game, False)
        self.assertEqual(ini.read_text(newline=""), off)

    def test_no_optiscaler(self):
        self.assertIsNone(helix_fg.switch(self.game / "missing", True))


class StreamlineTests(unittest.TestCase):
    def setUp(self):
        self.game = support.reset_home() / "game"
        sl = self.game / helix_fg.SL_DIR
        sl.mkdir(parents=True)
        for n in ("sl.common.dll", "sl.dlss_g.dll"):
            (sl / n).write_bytes(dll("2.14.16"))
        for n in ("sl.interposer.dll", "sl.common.dll", "sl.dlss.dll", "sl.dlss_g.dll", "game.exe"):
            (self.game / n).write_bytes(dll("2.4.0"))

    def test_version_skips_the_signature_bytes_in_code(self):
        p = self.game / "x.dll"
        p.write_bytes(struct.pack("<IIII", 0xFEEF04BD, 0x0283810F, 0xB70E0000, 0) + dll("2.14.16"))
        self.assertEqual(helix_fg.pe_version(p), "2.14.16")

    def test_missing_plugins_and_version(self):
        self.assertEqual(helix_fg.streamline(self.game), {"version": "2.14.16", "missing": ["sl.dlss.dll"]})

    def test_fix_downloads_from_the_sdk_of_that_version_and_cleanup_removes_it(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("bin/x64/sl.dlss.dll", dll("2.14.16") * 50)
            z.writestr("bin/x64/sl.common.dll", b"other")
        blob = buf.getvalue()
        urls = []

        def curl(args):
            urls.append(args[-1])
            if "-r" not in args:
                head = f"HTTP/2 302\r\ncontent-length: 0\r\n\r\nHTTP/2 200\r\ncontent-length: {len(blob)}\r\n\r\n"
                return mock.Mock(returncode=0, stdout=head.encode(), stderr=b"")
            a, b = (int(x) for x in args[args.index("-r") + 1].split("-"))
            return mock.Mock(returncode=0, stdout=blob[a:b + 1] + b"\n206", stderr=b"")

        with mock.patch.object(helix_fg.updates, "_curl", curl):
            r = helix_fg.fix_streamline(self.game)
        self.assertEqual(r, {"ok": True, "added": ["sl.dlss.dll"], "missing": []})
        self.assertTrue(all("v2.14.16/streamline-sdk-v2.14.16.zip" in u for u in urls))
        self.assertEqual((self.game / helix_fg.SL_DIR / "sl.dlss.dll").read_bytes(), dll("2.14.16") * 50)
        self.assertEqual(helix_fg.streamline(self.game)["missing"], [])

        helix_fg.cleanup(self.game)
        self.assertFalse((self.game / helix_fg.SL_DIR / "sl.dlss.dll").exists())
        self.assertTrue((self.game / helix_fg.SL_DIR / "sl.common.dll").exists())   # HelixSR's own stay


if __name__ == "__main__":
    unittest.main()
