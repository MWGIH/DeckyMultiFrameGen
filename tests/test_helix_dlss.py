import asyncio
import unittest
from unittest import mock

import support

from multifg import helix_dlss


def _read_raw(path):
    """The file's text with its line endings as they are (Path.read_text has no newline argument before 3.13)."""
    with open(path, newline="") as f:
        return f.read()


DOC = ("[Upscaling]\r\n"
       "; NetworkResolution: full = the screen size, fast = twice the render size\r\n"
       "NetworkResolution = full\r\n"
       "; DeepReuse: exact = the whole network every frame\r\n"
       "DeepReuse = exact\r\n"
       "\r\n"
       "[Sharpening]\r\n"
       "; off, nvidia or rcas\r\n"
       "Sharpener = off\r\n")


class IniTests(unittest.TestCase):
    def test_set_changes_only_the_key_and_keeps_comments_and_other_sections(self):
        text = helix_dlss.ini_set(DOC, "DeepReuse", "1:4")
        self.assertEqual(text, DOC.replace("DeepReuse = exact", "DeepReuse = 1:4"))
        text = helix_dlss.ini_set(text, "NetworkResolution", "fast")
        self.assertEqual(text, DOC.replace("DeepReuse = exact", "DeepReuse = 1:4")
                         .replace("NetworkResolution = full", "NetworkResolution = fast"))

    def test_set_reuses_a_commented_example_line(self):
        text = "[Upscaling]\n; DeepReuse = exact\n; DeepReuse: doc line\n"
        self.assertEqual(helix_dlss.ini_set(text, "DeepReuse", "1:2"),
                         "[Upscaling]\nDeepReuse = 1:2\n; DeepReuse: doc line\n")

    def test_unset_comments_out_the_key_only(self):
        text = helix_dlss.ini_unset(DOC, "DeepReuse")
        self.assertEqual(text, DOC.replace("DeepReuse = exact", ";DeepReuse = exact"))
        self.assertEqual(helix_dlss.ini_unset(text, "DeepReuse"), text)   # already off: unchanged

    def test_set_adds_the_section_and_key_when_missing(self):
        text = helix_dlss.ini_set("[Sharpening]\nSharpener = off\n", "NetworkResolution", "fast")
        self.assertEqual(text, "[Sharpening]\nSharpener = off\n\n[Upscaling]\nNetworkResolution = fast\n")
        self.assertIsNone(helix_dlss.ini_get("[Sharpening]\nSharpener = off\n", "NetworkResolution"))

    def test_keys_are_case_insensitive_and_keep_their_spacing(self):
        text = "[Upscaling]\r\n  deepreuse = Exact \r\n"
        self.assertEqual(helix_dlss.ini_get(text, "DeepReuse"), "Exact")
        self.assertEqual(helix_dlss.ini_set(text, "DeepReuse", "1:2"), "[Upscaling]\r\nDeepReuse = 1:2\r\n")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.game = support.reset_home() / "game"
        (self.game / "HelixSR").mkdir(parents=True)
        (self.game / "HelixSR" / "helixsr.dll").write_bytes(b"x")
        (self.game / "OptiScaler.ini").write_text("[HelixSR]\nDeepReuse=auto\n")

    def test_unknown_values_are_refused_and_nothing_changes(self):
        r = helix_dlss.apply(self.game, "scaler", deep_reuse="1:3")
        self.assertFalse(r["ok"])
        self.assertIn("deep_reuse", r["error"])
        r = helix_dlss.apply(self.game, "scaler", network_resolution="half")
        self.assertFalse(r["ok"])
        self.assertIn("network_resolution", r["error"])
        self.assertFalse((self.game / "HelixSR" / "helixsr.ini").exists())
        self.assertEqual((self.game / "OptiScaler.ini").read_text(), "[HelixSR]\nDeepReuse=auto\n")

    def test_values_are_normalised(self):
        r = helix_dlss.apply(self.game, "scaler", deep_reuse=" 1:4 ", network_resolution="FAST")
        self.assertTrue(r["ok"])
        self.assertEqual((r["deep_reuse"], r["network_resolution"]), ("1:4", "fast"))

    def test_supports_checks_the_helixsr_version(self):
        self.assertTrue(helix_dlss.supports("v3.4.1"))
        self.assertTrue(helix_dlss.supports("3.4"))
        self.assertFalse(helix_dlss.supports("v3.3.2"))
        self.assertFalse(helix_dlss.supports("v1.9.3"))
        self.assertFalse(helix_dlss.supports(None))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.game = support.reset_home() / "game"

    def test_scaler_ngx_layout(self):
        (self.game / "HelixSR").mkdir(parents=True)
        (self.game / "HelixSR" / "helixsr.dll").write_bytes(b"x")
        (self.game / "OptiScaler.ini").write_text("[HelixSR]\n")
        r = helix_dlss.resolve(self.game, "scaler")
        self.assertEqual(r["ini"], self.game / "HelixSR" / "helixsr.ini")
        self.assertEqual(r["opti"], self.game / "OptiScaler.ini")

    def test_scaler_2_0_layout(self):
        (self.game / "HelixSR-fsrfg").mkdir(parents=True)
        (self.game / "HelixSR-fsrfg" / "amd_fidelityfx_dx12.dll").write_bytes(b"x")
        r = helix_dlss.resolve(self.game, "scaler")
        self.assertEqual(r["ini"], self.game / "HelixSR-fsrfg" / "helixsr.ini")

    def test_scaler_existing_ini_wins_over_the_other_layout(self):
        (self.game / "HelixSR").mkdir(parents=True)
        (self.game / "HelixSR" / "helixsr.dll").write_bytes(b"x")
        (self.game / "HelixSR-fsrfg").mkdir()
        (self.game / "HelixSR-fsrfg" / "helixsr.ini").write_text("[Upscaling]\n")
        r = helix_dlss.resolve(self.game, "scaler")
        self.assertEqual(r["ini"], self.game / "HelixSR-fsrfg" / "helixsr.ini")

    def test_direct_drop_in_uses_the_fsr_dlls_folder(self):
        target = self.game / "bin" / "x64" / "amd_fidelityfx_upscaler_dx12.dll"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"x")
        r = helix_dlss.resolve(self.game, "direct", [str(target)])
        self.assertEqual(r["ini"], target.parent / "helixsr.ini")
        self.assertIsNone(r["opti"])

    def test_direct_drop_in_prefers_the_bridges_settings_path(self):
        hint = self.game / "other" / "helixsr.ini"
        r = helix_dlss.resolve(self.game, "direct", [], str(hint))
        self.assertEqual(r["ini"], hint)
        self.assertIsNone(helix_dlss.resolve(self.game, "direct", []))

    def test_helixsr_inside_optiscaler(self):
        self.assertIsNone(helix_dlss.resolve(self.game, "optiscaler"))
        (self.game / helix_dlss.OPTI_DIR).mkdir(parents=True)
        self.assertEqual(helix_dlss.resolve(self.game, "optiscaler")["ini"],
                         self.game / helix_dlss.OPTI_DIR / "helixsr.ini")


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.game = support.reset_home() / "game"
        (self.game / "HelixSR").mkdir(parents=True)
        (self.game / "HelixSR" / "helixsr.dll").write_bytes(b"x")
        self.opti = self.game / "OptiScaler.ini"
        self.opti.write_text("; HelixSR Scaler\r\n[HelixSR]\r\n; DeepReuse: auto, exact, 1:2 or 1:4\r\nDeepReuse=auto\r\n"
                             "WaveSize=auto\r\n\r\n[Upscalers]\r\nDx12Upscaler=fsr31\r\n")

    def test_scaler_sets_both_files_and_default_removes_both_overrides(self):
        r = helix_dlss.apply(self.game, "scaler", deep_reuse="1:4", network_resolution="fast")
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["deep_reuse"], r["network_resolution"]), ("1:4", "fast"))
        ini = self.game / "HelixSR" / "helixsr.ini"
        text = _read_raw(ini)
        self.assertIn("NetworkResolution = fast", text)
        self.assertIn("DeepReuse = 1:4", text)
        opti = _read_raw(self.opti)
        self.assertIn("DeepReuse=1:4\r\n", opti)
        self.assertIn("; DeepReuse: auto, exact, 1:2 or 1:4\r\n", opti)   # its comments stay
        self.assertIn("WaveSize=auto\r\n", opti)
        self.assertIn("Dx12Upscaler=fsr31\r\n", opti)

        r = helix_dlss.apply(self.game, "scaler", deep_reuse="default", network_resolution="default")
        self.assertEqual((r["deep_reuse"], r["network_resolution"]), ("default", "full"))
        self.assertIn(";DeepReuse = 1:4", _read_raw(ini))
        self.assertIn(";NetworkResolution = fast", _read_raw(ini))
        self.assertIn("DeepReuse=auto\r\n", _read_raw(self.opti))
        self.assertIn("Dx12Upscaler=fsr31\r\n", _read_raw(self.opti))

    def test_scaler_reads_optiscaler_deep_reuse_before_the_ini(self):
        ini = self.game / "HelixSR" / "helixsr.ini"
        ini.write_text("[Upscaling]\nDeepReuse = 1:2\n")
        self.assertEqual(helix_dlss.status(self.game, "scaler")["deep_reuse"], "1:2")
        self.opti.write_text("[HelixSR]\nDeepReuse=1:4\n")
        self.assertEqual(helix_dlss.status(self.game, "scaler")["deep_reuse"], "1:4")
        self.opti.write_text("[HelixSR]\nDeepReuse=auto\n")
        self.assertEqual(helix_dlss.status(self.game, "scaler")["deep_reuse"], "1:2")

    def test_helixsr_inside_optiscaler_round_trip(self):
        mod = self.game / helix_dlss.OPTI_DIR
        mod.mkdir()
        r = helix_dlss.apply(self.game, "optiscaler", network_resolution="fast")
        self.assertTrue(r["ok"], r)
        ini = mod / "helixsr.ini"
        self.assertIn("NetworkResolution = fast\n", ini.read_text())
        self.assertIn("DeepReuse=auto", self.opti.read_text())
        self.assertEqual(helix_dlss.apply(self.game, "optiscaler", network_resolution="default")["network_resolution"],
                         "full")
        self.assertIn(";NetworkResolution = fast", ini.read_text())

    def test_direct_drop_in_writes_only_helixsr_ini(self):
        target = self.game / "bin" / "x64" / "amd_fidelityfx_upscaler_dx12.dll"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"x")
        before = self.opti.read_text()
        r = helix_dlss.apply(self.game, "direct", [str(target)], None, deep_reuse="1:2")
        self.assertTrue(r["ok"], r)
        self.assertIn("DeepReuse = 1:2", (target.parent / "helixsr.ini").read_text())
        self.assertEqual(self.opti.read_text(), before)

    def test_default_does_not_create_a_file(self):
        (self.game / "HelixSR" / "helixsr.ini").unlink(missing_ok=True)
        r = helix_dlss.apply(self.game, "scaler", deep_reuse="default", network_resolution="default")
        self.assertTrue(r["ok"], r)
        self.assertFalse((self.game / "HelixSR" / "helixsr.ini").exists())

    def test_exact_is_shown_as_the_default(self):
        ini = self.game / "HelixSR" / "helixsr.ini"
        ini.write_text("[Upscaling]\nDeepReuse = exact\nNetworkResolution = full\n")
        r = helix_dlss.status(self.game, "scaler")
        self.assertEqual((r["deep_reuse"], r["network_resolution"]), ("default", "full"))


if __name__ == "__main__":
    unittest.main()


class MainApiTests(unittest.TestCase):
    """main.Plugin.helixsr_dlss finds the install and calls the right files (the rest is covered above)."""

    def setUp(self):
        self.game = support.reset_home() / "game"
        (self.game / "HelixSR").mkdir(parents=True)
        (self.game / "HelixSR" / "helixsr.dll").write_bytes(b"x")
        (self.game / "OptiScaler.ini").write_text("[HelixSR]\nDeepReuse=auto\n")

    def _plugin(self):
        import main
        return main

    def test_scaler_game_round_trip(self):
        main = self._plugin()
        status = {"ok": True, "installed": True, "current": "scaler", "exe_folder": str(self.game),
                  "installed_version": "v3.4.1"}
        with mock.patch.object(main, "_game_folder", return_value=str(self.game)), \
                mock.patch.object(main.HELIXSR, "game_status", return_value=status):
            p = main.Plugin()
            r = asyncio.run(p.helixsr_dlss("123", "1:4", "fast"))
            self.assertEqual((r["deep_reuse"], r["network_resolution"], r["route"]), ("1:4", "fast", "scaler"))
            r = asyncio.run(p.helixsr_dlss("123"))
            self.assertEqual((r["deep_reuse"], r["network_resolution"]), ("1:4", "fast"))
            r = asyncio.run(p.helixsr_dlss("123", "default", "default"))
            self.assertEqual((r["deep_reuse"], r["network_resolution"]), ("default", "full"))

    def test_old_helixsr_is_refused(self):
        main = self._plugin()
        status = {"ok": True, "installed": True, "current": "scaler", "exe_folder": str(self.game),
                  "installed_version": "v3.3.2"}
        with mock.patch.object(main, "_game_folder", return_value=str(self.game)), \
                mock.patch.object(main.HELIXSR, "game_status", return_value=status):
            r = asyncio.run(main.Plugin().helixsr_dlss("123"))
        self.assertFalse(r["ok"])
        self.assertIn("3.4", r["error"])

    def test_helixsr_inside_optiscaler_needs_34(self):
        main = self._plugin()
        with mock.patch.object(main, "_game_folder", return_value=str(self.game)), \
                mock.patch.object(main.HELIXSR, "game_status", return_value={"ok": True, "installed": False}), \
                mock.patch.object(main.helix_opti, "status",
                                          return_value={"installed": True, "helixsr": "v1.9.3"}):
            async def target(_appid):
                return str(self.game / helix_dlss.OPTI_DIR)
            with mock.patch.object(main, "_opti_target", target):
                (self.game / helix_dlss.OPTI_DIR).mkdir()
                r = asyncio.run(main.Plugin().helixsr_dlss("123"))
        self.assertFalse(r["ok"])
        self.assertIn("3.4", r["error"])
