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

    def test_release_pages_are_read_without_the_api(self):
        fx = Path(__file__).parent / "fixtures" / "github"
        repo = "MWGIH/DeckyMultiFrameGen"
        rels = updates.parse_release_list((fx / "releases.html").read_text(), repo)
        self.assertEqual((len(rels), rels[0]), (10, {"tag": "v0.9.16", "prerelease": False,
                                                     "published_at": "2026-10-30T23:13:19Z"}))
        self.assertEqual([r["tag"] for r in rels if r["prerelease"]], ["test"])
        assets = updates.parse_release_assets((fx / "expanded_assets.html").read_text(), repo, "v0.9.16")
        self.assertEqual(assets, [{
            "name": "Decky-MultiFrameGen.zip",
            "browser_download_url": f"https://github.com/{repo}/releases/download/v0.9.16/Decky-MultiFrameGen.zip",
            "size": 530 * 1024,
            "digest": "sha256:584615f8c34df3bfb746deed9c286a3436ad63fc8d580608d2da790575a49274"}])

    def test_latest_release_reads_the_redirect_and_file_list(self):
        fx = Path(__file__).parent / "fixtures" / "github"
        with mock.patch.object(updates, "latest_release_tag", return_value="v0.9.16"), \
                mock.patch.object(updates, "_page", return_value=(fx / "expanded_assets.html").read_text()), \
                mock.patch.object(updates, "_get", side_effect=AssertionError("no API call")):
            rel = updates.latest_release(updates.SELF_REPO)
        self.assertEqual((rel["tag_name"], rel["assets"][0]["name"]), ("v0.9.16", "Decky-MultiFrameGen.zip"))

    def test_prefixed_tags_come_from_the_releases_page(self):
        page = "".join(
            f'<section data-release-anchor="{t}"><a href="/x/y/releases/tag/{t}">{t}</a>'
            f'{"<span>Pre-release</span>" if pre else ""}</section>'
            for t, pre in [("render-v4.7.0", False), ("plugin-v4.8.0", True), ("plugin-v4.7.0-beta.1", False),
                           ("plugin-v4.6.0", False)])
        with mock.patch.object(updates, "_page", return_value=page), \
                mock.patch.object(updates, "_get", side_effect=AssertionError("no API call")):
            self.assertEqual(updates.latest_tag("x/y", "plugin-v"), "plugin-v4.6.0")

    def test_api_is_the_fallback_and_a_used_up_limit_keeps_the_last_answer(self):
        with mock.patch.object(updates, "latest_release_tag", return_value=None), \
                mock.patch.object(updates, "_get", return_value={"tag_name": "v1"}):
            self.assertEqual(updates.upstream("a/b", "0.5")["latest"], "v1")
        with mock.patch.object(updates, "latest_release_tag", return_value=None), \
                mock.patch.object(updates, "_get", side_effect=RuntimeError(updates.LIMIT_MESSAGE)):
            r = updates.upstream("a/b", "0.5")
        self.assertEqual((r["latest"], r["newer_upstream"]), ("v1", True))

    def test_api_answers_are_kept_on_disk(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cache.json"
            updates._CACHE.clear()
            with mock.patch.object(updates, "_CACHE_FILE", f):
                updates._CACHE["u"] = ('W/"e"', {"tag_name": "v2"})
                updates._save_cache()
            updates._CACHE.clear()
            with mock.patch.object(updates, "_CACHE_FILE", None):
                updates.use_cache_file(f)
            self.assertEqual(updates._CACHE["u"], ('W/"e"', {"tag_name": "v2"}))
            updates._CACHE.clear()

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
                mock.patch.object(updates, "_page", side_effect=RuntimeError("offline")), \
                mock.patch.object(main.FSR4, "version", return_value="1.0"), \
                mock.patch.object(main.HELIXSR, "releases", return_value=[]):
            r = asyncio.run(main.Plugin().check_updates())
        self.assertEqual(set(r), {"plugin", "optiscaler", "helixsr", "mako", "fsr4injector"})
        self.assertIn("error", r["fsr4injector"])
        self.assertIn("error", r["plugin"])
        self.assertNotIn("error", r["optiscaler"])   # only the upstream check failed
        self.assertIn("upstream_error", r["optiscaler"])
        self.assertEqual((r["mako"]["latest"], r["mako"]["newer_upstream"]), ("plugin-v99.0.0", True))

    def test_fsr4injector_not_installed_checks_nothing(self):
        with mock.patch.object(main.FSR4, "version", return_value=None), \
                mock.patch.object(main.FSR4, "latest", side_effect=AssertionError("no check")), \
                mock.patch.object(updates, "_page", side_effect=RuntimeError("offline")), \
                mock.patch.object(updates, "_get", side_effect=RuntimeError(updates.LIMIT_MESSAGE)), \
                mock.patch.object(updates, "latest_release_tag", return_value=None), \
                mock.patch.object(main.HELIXSR, "releases", return_value=[]):
            r = asyncio.run(main.Plugin().check_updates())
        self.assertEqual(r["fsr4injector"]["update_available"], False)
        self.assertNotIn("error", r["optiscaler"])
        self.assertFalse(r["helixsr"]["update_available"])


if __name__ == "__main__":
    unittest.main()
