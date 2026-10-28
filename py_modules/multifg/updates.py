"""Update checks: this plugin's own releases, and the upstream releases its backends come from.

OptiScaler's files and MAKO's Renderer are pinned by this plugin (Decky Framegen's and MAKO Decky's install code is
vendored with the exact assets it expects), so a new upstream release reaches them through a new release of this
plugin. HelixSR is downloaded from its own releases directly, so it can update on its own."""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

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


# GitHub's API allows 60 unauthenticated calls an hour per IP address, and each update check makes several. Its
# answers are kept with their ETag: asking again with it costs nothing when nothing changed (304), and a refused call
# (403 when the hour's calls are used up) answers from what was kept
_CACHE: dict[str, tuple[str, object]] = {}


def _env() -> dict:
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG", "")
    return env


def _curl(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["curl", "-sS", "--retry", "2", "-A", "Decky-MultiFrameGen", *args],
                          env=_env(), capture_output=True, timeout=30)


def _get(url: str):
    cached = _CACHE.get(url)
    with tempfile.NamedTemporaryFile() as headers:
        args = ["-L", "-D", headers.name, "-H", "Accept: application/vnd.github+json", "-w", "\n%{http_code}"]
        if cached:
            args += ["-H", f"If-None-Match: {cached[0]}"]
        p = _curl(args + [url])
        head = Path(headers.name).read_bytes().decode(errors="replace")
    body, _, code = p.stdout.decode(errors="replace").rpartition("\n")
    if code == "304" and cached:
        return cached[1]
    if p.returncode or code != "200":
        if cached:
            return cached[1]
        if code == "403" and "x-ratelimit-remaining: 0" in head.lower():
            raise RuntimeError("GitHub's hourly limit for update checks is used up: try again in an hour")
        raise RuntimeError(p.stderr.decode(errors="replace").strip()[-200:] or f"GitHub answered {code}")
    data = json.loads(body)
    etag = re.findall(r"(?im)^etag:\s*(.+?)\s*$", head)
    if etag:
        _CACHE[url] = (etag[-1], data)
    return data


def _text(url: str) -> str | None:
    """A small file from github.com itself (a release download, not the API: no hourly limit)."""
    p = _curl(["-fL", url])
    return p.stdout.decode(errors="replace").strip() if p.returncode == 0 else None


def latest_release_tag(repo: str) -> str | None:
    """The latest release's tag from github.com's own redirect (releases/latest -> releases/tag/<tag>), no API."""
    p = _curl(["-o", "/dev/null", "-w", "%{redirect_url}", f"https://github.com/{repo}/releases/latest"])
    m = re.search(r"/releases/tag/([^/?#\s]+)$", p.stdout.decode(errors="replace").strip())
    return m.group(1) if p.returncode == 0 and m else None


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
    A test build installed while test builds are off is offered the release, so turning them off goes back to it.
    Both are read from github.com's release downloads, not its API, so the hourly API limit never blocks them."""
    if test_builds:
        url = f"https://github.com/{SELF_REPO}/releases/download/test/{SELF_ZIP}"
        # the workflow puts version.txt next to the test build's ZIP; test builds from before it say it in the name
        latest = _text(f"https://github.com/{SELF_REPO}/releases/download/test/version.txt")
        if not latest:
            rel = _get(f"{GITHUB}/{SELF_REPO}/releases/tags/test")
            m = re.search(r"Test build (\S+)", rel.get("name") or "")
            latest = m.group(1) if m else None
        available = bool(latest) and latest != current
    else:
        tag = latest_release_tag(SELF_REPO)
        if not tag:
            raise RuntimeError("couldn't reach GitHub")
        latest = tag.lstrip("v") or None
        url = f"https://github.com/{SELF_REPO}/releases/download/{tag}/{SELF_ZIP}"
        available = newer(latest, current) or (is_test_build(current) and bool(latest))
    return {
        "current": current,
        "latest": latest,
        "test_builds": test_builds,
        "update_available": available,
        "url": url,
        "sha256": None,
    }


def upstream(repo: str, vendored: str, prefix: str = "") -> dict:
    """The newest upstream release next to the vendored one; an offline check leaves latest unknown."""
    try:
        tag = latest_tag(repo, prefix)
    except Exception as exc:
        return {"vendored": vendored, "latest": None, "newer_upstream": False, "upstream_error": str(exc)}
    return {"vendored": vendored, "latest": tag, "newer_upstream": newer(tag, vendored)}
