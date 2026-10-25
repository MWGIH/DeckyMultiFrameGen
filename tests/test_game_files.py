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
        self.assertIn({"choice": "fsr4injector+mako", "needs": ["FSR 3.1+"]}, g["hidden"])

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

    def test_current_choice_stays_offered(self):
        main.SETTINGS.set_game_choice("100", "fsr4injector")
        self.assertIn("fsr4injector", self.choices()["choices"])


if __name__ == "__main__":
    unittest.main()
