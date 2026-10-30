"""Update checks: this plugin's own releases, and the upstream releases its backends come from.

OptiScaler's files and MAKO's Renderer are pinned by this plugin (Decky Framegen's and MAKO Decky's install code is
vendored with the exact assets it expects), so a new upstream release reaches them through a new release of this
plugin. HelixSR is downloaded from its own releases directly, so it can update on its own."""

import html
import json
import os
import re
import subprocess
import tempfile
import time
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


# GitHub's API allows 60 unauthenticated calls an hour per IP address, and each update check makes several. So release
# information is read from github.com's own pages first (the releases/latest redirect, the releases list and a
# release's file list), which that limit doesn't cover; the API is only asked when a page can't be read. Its answers
# are kept with their ETag, on disk once use_cache_file() is called: asking again with it costs nothing when nothing
# changed (304), and a refused call (403 when the hour's calls are used up) answers from what was kept
_CACHE: dict[str, tuple[str, object]] = {}
_CACHE_FILE: Path | None = None
LIMIT_MESSAGE = "GitHub's hourly limit for update checks is used up: try again in an hour"


def use_cache_file(path: Path) -> None:
    """Keep the API answers in path too, so the ETags and the 403 fallback outlive a restart of Steam."""
    global _CACHE_FILE
    _CACHE_FILE = path
    try:
        data = json.loads(path.read_text())
        _CACHE.update({k: (v[0], v[1]) for k, v in data.items() if isinstance(v, list) and len(v) == 2})
    except (OSError, ValueError):
        pass


def _save_cache() -> None:
    if not _CACHE_FILE:
        return
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: list(v) for k, v in _CACHE.items()}))
        tmp.replace(_CACHE_FILE)
    except OSError:
        pass


def is_rate_limited(exc: Exception) -> bool:
    return str(exc) == LIMIT_MESSAGE


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
            raise RuntimeError(LIMIT_MESSAGE)
        raise RuntimeError(p.stderr.decode(errors="replace").strip()[-200:] or f"GitHub answered {code}")
    data = json.loads(body)
    etag = re.findall(r"(?im)^etag:\s*(.+?)\s*$", head)
    if etag:
        _CACHE[url] = (etag[-1], data)
        _save_cache()
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


# --- github.com's release pages (no hourly limit) ---------------------------------------------------------------

def _page(url: str) -> str:
    p = _curl(["-fL", "--compressed", url])
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace").strip()[-200:] or "couldn't reach GitHub")
    return p.stdout.decode(errors="replace")


_SECTION = re.compile(r"<section\b[^>]*data-release-anchor=", re.I)
_SIZE_UNITS = {"b": 1, "byte": 1, "bytes": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}


def parse_release_list(page: str, repo: str) -> list[dict]:
    """The releases on a github.com/<repo>/releases page: [{tag, prerelease, published_at}], as listed (newest first).
    Drafts are never on it."""
    out = []
    for part in _SECTION.split(page)[1:]:
        m = re.search(rf'href="/{re.escape(repo)}/releases/tag/([^"?#]+)"', part, re.I)
        if not m:
            continue
        tag = html.unescape(m.group(1))
        if any(r["tag"] == tag for r in out):
            continue
        when = re.search(r'<relative-time[^>]*\bdatetime="([^"]+)"', part)
        out.append({"tag": tag, "prerelease": bool(re.search(r">\s*Pre-release\s*<", part)),
                    "published_at": when.group(1) if when else None})
    return out


def parse_release_assets(page: str, repo: str, tag: str) -> list[dict]:
    """A release's files from github.com/<repo>/releases/expanded_assets/<tag>, shaped like the API's assets:
    [{name, browser_download_url, size (rounded, as the page shows it), digest}]. Source archives are left out."""
    prefix = f"/{repo}/releases/download/{tag}/"
    out = []
    for item in re.split(r"<li\b", page)[1:]:
        m = re.search(rf'href="({re.escape(prefix)}([^"]+))"', item, re.I)
        if not m:
            continue
        name = html.unescape(m.group(2))
        digest = re.search(r"sha256:[0-9a-fA-F]{64}", item)
        size = re.search(r">\s*([\d.]+)\s*(bytes?|[KMG]B)\s*<", item, re.I)
        out.append({"name": name, "browser_download_url": "https://github.com" + html.unescape(m.group(1)),
                    "size": int(float(size.group(1)) * _SIZE_UNITS[size.group(2).lower()]) if size else None,
                    "digest": digest.group(0).lower() if digest else None})
    return out


def release_list(repo: str, pages: int = 1) -> list[dict]:
    """Published releases from github.com's releases pages (10 a page), newest first."""
    out: list[dict] = []
    for n in range(1, pages + 1):
        listed = parse_release_list(_page(f"https://github.com/{repo}/releases?page={n}"), repo)
        out += [r for r in listed if all(r["tag"] != o["tag"] for o in out)]
        if len(listed) < 10:
            break
    if not out:
        raise RuntimeError("GitHub's releases page had no releases on it")
    return out


def release_assets(repo: str, tag: str) -> list[dict]:
    return parse_release_assets(_page(f"https://github.com/{repo}/releases/expanded_assets/{tag}"), repo, tag)


def _api_or(page_reader, api_reader):
    """page_reader's answer; the API's when github.com's pages couldn't be read or read (their layout can change)."""
    try:
        return page_reader()
    except Exception as page_exc:
        try:
            return api_reader()
        except Exception as api_exc:
            raise (api_exc if is_rate_limited(api_exc) else page_exc) from None


def latest_release(repo: str) -> dict:
    """The latest release shaped like the API's answer ({tag_name, prerelease, draft, assets}), read from the
    releases/latest redirect and the release's file list; the API only when those can't be read."""
    def from_pages():
        tag = latest_release_tag(repo)
        if not tag:
            raise RuntimeError("couldn't reach GitHub")
        return {"tag_name": tag, "prerelease": False, "draft": False, "assets": release_assets(repo, tag)}
    return _api_or(from_pages, lambda: _get(f"{GITHUB}/{repo}/releases/latest"))


def _stable_tag(tag: str) -> bool:
    """A tag without a pre-release marker after its version (4.6.0-beta.1, 5.0rc1), for lists that can't say."""
    return not re.search(r"\d[._-]?(alpha|beta|rc|pre|dev|test)", tag, re.I)


def latest_tag(repo: str, prefix: str = "") -> str | None:
    """Newest published tag starting with prefix (MAKO tags its plugin 'plugin-v…' and its renderer 'render-v…')."""
    if not prefix:
        def from_pages():
            tag = latest_release_tag(repo)
            if not tag:
                raise RuntimeError("couldn't reach GitHub")
            return tag
        return _api_or(from_pages, lambda: _get(f"{GITHUB}/{repo}/releases/latest").get("tag_name"))

    def pick(tags):
        tags = [t for t in tags if t.startswith(prefix) and _stable_tag(t)]
        return max(tags, key=version_key) if tags else None

    return _api_or(
        lambda: pick([r["tag"] for r in release_list(repo, pages=3) if not r["prerelease"]]),
        lambda: pick([r["tag_name"] for r in _get(f"{GITHUB}/{repo}/releases?per_page=30")
                      if not r.get("draft") and not r.get("prerelease")]))


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


# Upstream tags last seen, so a check GitHub refuses still reports them
_UPSTREAM: dict[tuple, tuple[float, str | None]] = {}


def upstream(repo: str, vendored: str, prefix: str = "") -> dict:
    """The newest upstream release next to the vendored one; an offline check leaves latest at what was last seen."""
    try:
        tag = latest_tag(repo, prefix)
        _UPSTREAM[(repo, prefix)] = (time.time(), tag)
    except Exception as exc:
        tag = _UPSTREAM.get((repo, prefix), (0, None))[1]
        return {"vendored": vendored, "latest": tag, "newer_upstream": newer(tag, vendored), "upstream_error": str(exc)}
    return {"vendored": vendored, "latest": tag, "newer_upstream": newer(tag, vendored)}
