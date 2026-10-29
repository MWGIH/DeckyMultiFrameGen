import asyncio
import unittest

import support  # noqa: F401  (sets up paths and the fake home before main is imported)

import main
from multifg import game_files


class GameFilesTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        steam = self.home / ".local" / "share" / "Steam"
        support.add_game(steam, "100", "Game", "Game")
        self.exe = steam / "steamapps" / "common" / "Game" / "Bin"
        self.exe.mkdir(parents=True)

    def choices(self):
        return asyncio.run(main.Plugin().get_game("100"))

    def test_no_upscaler_files_hides_fsr4_injector_and_helixsr(self):
        g = self.choices()
        self.assertEqual(g["upscalers"], [])
        self.assertNotIn("fsr4injector", g["choices"])
        self.assertNotIn("helixsr+mako", g["choices"])
        self.assertNotIn("optiscaler+helixsr", g["choices"])
        self.assertIn("optiscaler+mako", g["choices"])
        self.assertIn({"choice": "fsr4injector+mako", "needs": ["FSR 3.1+ (DirectX 12)"], "reason": None}, g["hidden"])

    def test_dlss_game_gets_helixsr_but_not_fsr4_injector(self):
        (self.exe / "nvngx_dlss.dll").write_bytes(b"")
        g = self.choices()
        self.assertEqual(g["upscalers"], ["DLSS"])
        self.assertIn("helixsr", g["choices"])
        self.assertNotIn("fsr4injector", g["choices"])

    def test_fsr31_game_gets_everything(self):
        (self.exe / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"")
        g = self.choices()
        self.assertEqual(g["choices"], list(main.backends.GAME_CHOICES))
        self.assertEqual(g["hidden"], [])

    def test_optiscaler_copies_dont_count_but_kept_originals_do(self):
        for name in ("FRAMEGEN_PATCH", "amd_fidelityfx_dx12.dll", "libxess.dll", "libxess.dll.b"):
            (self.exe / name).write_bytes(b"")
        self.assertEqual(game_files.detect(str(self.exe.parent)), {"xess"})
        (self.exe / "nvngx_dlss.original.dll").write_bytes(b"")
        self.assertEqual(game_files.detect(str(self.exe.parent)), {"xess", "dlss"})

    def test_known_not_working_is_hidden_even_with_fsr31(self):
        support.add_game(self.home / ".local" / "share" / "Steam", "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        exe = self.home / ".local" / "share" / "Steam" / "steamapps" / "common" / "Cyberpunk 2077" / "bin"
        exe.mkdir(parents=True)
        (exe / "amd_fidelityfx_dx12.dll").write_bytes(b"")
        g = asyncio.run(main.Plugin().get_game("1091500"))
        self.assertNotIn("fsr4injector", g["choices"])
        self.assertNotIn("fsr4injector+mako", g["choices"])
        self.assertIn("fsr4injector", g["all_choices"])
        self.assertIn("helixsr", g["choices"])
        self.assertIn({"choice": "fsr4injector", "needs": ["FSR 3.1+ (DirectX 12)"], "reason": "takes away Cyberpunk 2077's FSR 4 option"},
                      g["hidden"])

    def test_helixsr_drop_in_not_offered_in_cyberpunk(self):
        st = {"ok": True, "found": True, "route": "direct", "ways": ["direct", "scaler"]}
        g = game_files.helix_ways("1091500", st)
        self.assertEqual((g["ways"], g["route"]), (["scaler"], "scaler"))
        self.assertIn("direct", g["hidden_ways"])
        self.assertIs(game_files.helix_ways("2420110", st), st)
        g = game_files.helix_ways("1091500", {**st, "ways": ["direct"]})
        self.assertEqual((g["ways"], g["route"]), ([], "blocked"))
        support.add_game(self.home / ".local" / "share" / "Steam", "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        r = asyncio.run(main.Plugin().helixsr_install_game("1091500", "direct", ""))
        self.assertFalse(r["ok"])
        self.assertIn("FSR drop-in", r["error"])

    def test_current_choice_stays_offered(self):
        main.SETTINGS.set_game_choice("100", "fsr4injector")
        self.assertIn("fsr4injector", self.choices()["choices"])


if __name__ == "__main__":
    unittest.main()


class ListingTests(unittest.TestCase):
    def test_lists_exes_and_upscaler_files_with_their_folders(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("PBZ.exe", "PBZ/Binaries/Win64/PBZ-Win64-Shipping.exe", "PBZ/Binaries/Win64/other.dll",
                        "Engine/Plugins/FSR/Binaries/ThirdParty/Win64/amd_fidelityfx_upscaler_dx12.original.dll",
                        "Engine/Plugins/FSR/Binaries/ThirdParty/Win64/amd_fidelityfx_loader_dx12.dll",
                        "Engine/Binaries/Win64/CrashReportClient.exe"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(b"MZ")
            self.assertEqual(game_files.listing(d), [
                "PBZ.exe",
                "Engine/Plugins/FSR/Binaries/ThirdParty/Win64/amd_fidelityfx_loader_dx12.dll",
                "Engine/Plugins/FSR/Binaries/ThirdParty/Win64/amd_fidelityfx_upscaler_dx12.original.dll",
                "PBZ/Binaries/Win64/PBZ-Win64-Shipping.exe",
            ])
        self.assertIsNone(game_files.listing("/nonexistent"))
