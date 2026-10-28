import asyncio
import unittest
from unittest import mock

import support  # noqa: F401

import main
from multifg import updates


class UpdateTests(unittest.TestCase):
    def test_versions_compare_by_number(self):
        self.assertTrue(updates.newer("v0.6.0", "0.5.10"))
        self.assertFalse(updates.newer("v0.5.5", "0.5.5"))
        self.assertTrue(updates.newer("plugin-v99.0.0", "4.5.0"))
        self.assertFalse(updates.newer(None, "1"))

    def test_self_update_needs_the_zip(self):
        rel = {"tag_name": "v0.6.0", "assets": [{"name": "Decky-MultiFrameGen.zip", "browser_download_url": "https://x/z.zip",
                                                  "digest": "sha256:" + "a" * 64}]}
        with mock.patch.object(updates, "latest_release", return_value=rel):
            r = updates.self_update("0.5.5")
        self.assertEqual((r["update_available"], r["latest"], r["url"], r["sha256"]), (True, "0.6.0", "https://x/z.zip", "a" * 64))
        with mock.patch.object(updates, "latest_release", return_value={"tag_name": "v0.6.0", "assets": []}):
            self.assertFalse(updates.self_update("0.5.5")["update_available"])

    def test_test_builds_follow_the_test_prerelease(self):
        zip_ = {"name": updates.SELF_ZIP, "browser_download_url": "https://x/test.zip", "digest": "sha256:ab"}
        test = {"tag_name": "test", "name": "Test build 0.9.7-test.12 (claude/x)", "assets": [zip_]}
        with mock.patch.object(updates, "_get", return_value=test) as get:
            r = updates.self_update("0.9.5", test_builds=True)
        self.assertTrue(get.call_args[0][0].endswith("/releases/tags/test"))
        self.assertEqual((r["latest"], r["update_available"], r["url"]), ("0.9.7-test.12", True, "https://x/test.zip"))
        with mock.patch.object(updates, "_get", return_value=test):
            self.assertFalse(updates.self_update("0.9.7-test.12", test_builds=True)["update_available"])
        # test builds turned off: a test build is offered the release, even one with a lower number
        rel = {"tag_name": "v0.9.5", "assets": [zip_]}
        with mock.patch.object(updates, "latest_release", return_value=rel):
            self.assertTrue(updates.self_update("0.9.7-test.12")["update_available"])
            self.assertFalse(updates.self_update("0.9.5")["update_available"])

    def test_test_builds_setting_defaults_to_the_installed_kind(self):
        import tempfile
        from pathlib import Path
        from multifg.settings import Settings
        with tempfile.TemporaryDirectory() as d:
            s = Settings(Path(d) / "settings.json")
            self.assertTrue(s.test_builds("0.9.7-test.12"))
            self.assertFalse(s.test_builds("0.9.5"))
            s.set_test_builds(False)
            self.assertFalse(s.test_builds("0.9.7-test.12"))
            s.set_test_builds(True)
            self.assertTrue(s.test_builds("0.9.5"))

    def test_check_updates_reports_each_part_and_survives_errors(self):
        def fake_get(url):
            if "MAKO" in url:
                return [{"tag_name": "plugin-v99.0.0"}, {"tag_name": "render-v4.6.0"}]
            raise RuntimeError("offline")
        with mock.patch.object(updates, "_get", side_effect=fake_get), \
                mock.patch.object(main.HELIXSR, "releases", return_value=[]):
            r = asyncio.run(main.Plugin().check_updates())
        self.assertEqual(set(r), {"plugin", "optiscaler", "helixsr", "mako", "fsr4injector"})
        self.assertIn("error", r["fsr4injector"])
        self.assertIn("error", r["plugin"])
        self.assertNotIn("error", r["optiscaler"])   # only the upstream check failed
        self.assertIn("upstream_error", r["optiscaler"])
        self.assertEqual((r["mako"]["latest"], r["mako"]["newer_upstream"]), ("plugin-v99.0.0", True))
        self.assertFalse(r["helixsr"]["update_available"])


if __name__ == "__main__":
    unittest.main()
