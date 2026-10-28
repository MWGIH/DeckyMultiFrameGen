import asyncio
import subprocess
import unittest
from pathlib import Path
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

    def test_self_update_reads_the_release_without_the_api(self):
        with mock.patch.object(updates, "latest_release_tag", return_value="v0.6.0"), \
                mock.patch.object(updates, "_get", side_effect=AssertionError("no API call")):
            r = updates.self_update("0.5.5")
        self.assertEqual((r["update_available"], r["latest"], r["url"]),
                         (True, "0.6.0", f"https://github.com/{updates.SELF_REPO}/releases/download/v0.6.0/{updates.SELF_ZIP}"))
        with mock.patch.object(updates, "latest_release_tag", return_value=None):
            self.assertRaises(RuntimeError, updates.self_update, "0.5.5")

    def test_latest_release_tag_reads_the_redirect(self):
        done = subprocess.CompletedProcess([], 0, b"https://github.com/MWGIH/DeckyMultiFrameGen/releases/tag/v0.9.7", b"")
        with mock.patch.object(updates, "_curl", return_value=done):
            self.assertEqual(updates.latest_release_tag(updates.SELF_REPO), "v0.9.7")

    def test_test_builds_follow_the_test_prerelease(self):
        with mock.patch.object(updates, "_text", return_value="0.9.7-test.12"), \
                mock.patch.object(updates, "_get", side_effect=AssertionError("no API call")):
            r = updates.self_update("0.9.5", test_builds=True)
            self.assertFalse(updates.self_update("0.9.7-test.12", test_builds=True)["update_available"])
        self.assertEqual((r["latest"], r["update_available"], r["url"]),
                         ("0.9.7-test.12", True, f"https://github.com/{updates.SELF_REPO}/releases/download/test/{updates.SELF_ZIP}"))
        # a test build from before version.txt: its release name says the version
        test = {"tag_name": "test", "name": "Test build 0.9.7-test.12 (claude/x)", "assets": []}
        with mock.patch.object(updates, "_text", return_value=None), \
                mock.patch.object(updates, "_get", return_value=test) as get:
            self.assertEqual(updates.self_update("0.9.5", test_builds=True)["latest"], "0.9.7-test.12")
        self.assertTrue(get.call_args[0][0].endswith("/releases/tags/test"))
        # test builds turned off: a test build is offered the release, even one with a lower number
        with mock.patch.object(updates, "latest_release_tag", return_value="v0.9.5"):
            self.assertTrue(updates.self_update("0.9.7-test.12")["update_available"])
            self.assertFalse(updates.self_update("0.9.5")["update_available"])

    def test_api_answers_are_kept_for_304_and_a_used_up_limit(self):
        url = "https://api.github.com/repos/x/y/releases/latest"
        calls = []

        def fake_curl(args):
            calls.append(args)
            headers = Path(args[args.index("-D") + 1])
            n = len(calls)
            if n == 1:
                headers.write_text('HTTP/2 200\r\nETag: W/"abc"\r\n\r\n')
                return subprocess.CompletedProcess(args, 0, b'{"tag_name": "v1"}\n200', b"")
            headers.write_text("HTTP/2 403\r\nx-ratelimit-remaining: 0\r\n\r\n" if n == 3 else "HTTP/2 304\r\n\r\n")
            return subprocess.CompletedProcess(args, 0, (b"{}\n403" if n == 3 else b"\n304"), b"")

        updates._CACHE.clear()
        with mock.patch.object(updates, "_curl", side_effect=fake_curl):
            self.assertEqual(updates._get(url), {"tag_name": "v1"})
            self.assertEqual(updates._get(url), {"tag_name": "v1"})
            self.assertIn('If-None-Match: W/"abc"', calls[1])
            self.assertEqual(updates._get(url), {"tag_name": "v1"})   # the 403 answers from what was kept
            updates._CACHE.clear()
            calls.clear()
            calls.extend([None, None])
            with self.assertRaisesRegex(RuntimeError, "hourly limit"):
                updates._get(url)

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
                mock.patch.object(updates, "latest_release_tag", return_value=None), \
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
