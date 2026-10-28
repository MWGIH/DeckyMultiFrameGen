"""Update checks: this plugin's own releases, and the upstream releases its backends come from.

OptiScaler's files and MAKO's Renderer are pinned by this plugin (Decky Framegen's and MAKO Decky's install code is
vendored with the exact assets it expects), so a new upstream release reaches them through a new release of this
plugin. HelixSR is downloaded from its own releases directly, so it can update on its own."""

import json
import os
import re
import subprocess

GITHUB = "https://api.github.com/repos"
SELF_REPO = "MWGIH/DeckyMultiFrameGen"
SELF_ZIP = "Decky-MultiFrameGen.zip"
FRAMEGEN_REPO = "xXJSONDeruloXx/Decky-Framegen"
MAKO_REPO = "eugeniosegala/MAKO"

# The upstream versions vendored into this release of the plugin
FRAMEGEN_VENDORED = "0.17"
MAKO_VENDORED = "4.6.0"


def version_key(v: str | None) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4])


def newer(latest: str | None, current: str | None) -> bool:
    return bool(latest) and version_key(latest) > version_key(current)


def _get(url: str):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG", "")
    p = subprocess.run(["curl", "-fsSL", "--retry", "2", "-H", "Accept: application/vnd.github+json", url],
                       env=env, capture_output=True, timeout=30)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace").strip()[-200:] or "download failed")
    return json.loads(p.stdout)


def latest_release(repo: str) -> dict:
    return _get(f"{GITHUB}/{repo}/releases/latest")


def latest_tag(repo: str, prefix: str = "") -> str | None:
    """Newest published tag starting with prefix (MAKO tags its plugin 'plugin-v…' and its renderer 'render-v…')."""
    if not prefix:
        return latest_release(repo).get("tag_name")
    tags = [r["tag_name"] for r in _get(f"{GITHUB}/{repo}/releases?per_page=30")
            if not r.get("draft") and not r.get("prerelease") and r.get("tag_name", "").startswith(prefix)]
    return max(tags, key=version_key) if tags else None


def is_test_build(version: str | None) -> bool:
    return "-test." in (version or "")


def self_update(current: str, test_builds: bool = False) -> dict:
    """This plugin's update: the newest release, or with test_builds the "test" prerelease (a branch's build).
    A test build installed while test builds are off is offered the release, so turning them off goes back to it."""
    if test_builds:
        rel = _get(f"{GITHUB}/{SELF_REPO}/releases/tags/test")
        # the workflow names it "Test build <version> (<branch>)"
        m = re.search(r"Test build (\S+)", rel.get("name") or "")
        latest = m.group(1) if m else None
        available = bool(latest) and latest != current
    else:
        rel = latest_release(SELF_REPO)
        latest = (rel.get("tag_name") or "").lstrip("v") or None
        available = newer(latest, current) or (is_test_build(current) and bool(latest))
    asset = next((a for a in rel.get("assets", []) if a.get("name") == SELF_ZIP), None)
    digest = (asset or {}).get("digest") or ""
    return {
        "current": current,
        "latest": latest,
        "test_builds": test_builds,
        "update_available": available and asset is not None,
        "url": asset["browser_download_url"] if asset else None,
        "sha256": digest[7:] if digest.startswith("sha256:") else None,
    }


def upstream(repo: str, vendored: str, prefix: str = "") -> dict:
    """The newest upstream release next to the vendored one; an offline check leaves latest unknown."""
    try:
        tag = latest_tag(repo, prefix)
    except Exception as exc:
        return {"vendored": vendored, "latest": None, "newer_upstream": False, "upstream_error": str(exc)}
    return {"vendored": vendored, "latest": tag, "newer_upstream": newer(tag, vendored)}
