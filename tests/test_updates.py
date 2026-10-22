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

    def test_check_updates_reports_each_part_and_survives_errors(self):
        def fake_get(url):
            if "MAKO" in url:
                return [{"tag_name": "plugin-v99.0.0"}, {"tag_name": "render-v4.6.0"}]
            raise RuntimeError("offline")
        with mock.patch.object(updates, "_get", side_effect=fake_get), \
                mock.patch.object(main.HELIXSR, "releases", return_value=[]):
            r = asyncio.run(main.Plugin().check_updates())
        self.assertEqual(set(r), {"plugin", "optiscaler", "helixsr", "mako"})
        self.assertIn("error", r["plugin"])
        self.assertNotIn("error", r["optiscaler"])   # only the upstream check failed
        self.assertIn("upstream_error", r["optiscaler"])
        self.assertEqual((r["mako"]["latest"], r["mako"]["newer_upstream"]), ("plugin-v99.0.0", True))
        self.assertFalse(r["helixsr"]["update_available"])


if __name__ == "__main__":
    unittest.main()
