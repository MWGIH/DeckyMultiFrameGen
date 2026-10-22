#!/usr/bin/env python3
"""Brings a newer MAKO Decky release into this plugin (the vendored py_modules/mako_plugin and src/mako, the MAKO
Renderer's assets in assets/mako/renderer.json, bin/mako-diagnostics).

    scripts/update_mako.py MAKO_CLONE [TO_TAG]

MAKO_CLONE is a git clone of https://github.com/eugeniosegala/MAKO with its tags; TO_TAG defaults to its newest
plugin-v* tag. The upstream changes from the vendored tag (MAKO_VENDORED in py_modules/multifg/updates.py) to TO_TAG
are merged three-way into this plugin's copies, so the small marked changes this plugin carries stay. Prints what it
did; exits 0 when updated, 1 when already up to date, 2 when a file needs a hand merge (conflict markers left in it).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPDATES = ROOT / "py_modules" / "multifg" / "updates.py"
# upstream path -> this plugin's path
MAPS = [
    ("plugin/py_modules/mako_plugin", "py_modules/mako_plugin"),
    ("plugin/src", "src/mako"),
    ("plugin/shared_config.py", "py_modules/shared_config.py"),
    ("plugin/shared_flatpak_runtimes.py", "py_modules/shared_flatpak_runtimes.py"),
    ("scripts/mako-diagnostics", "bin/mako-diagnostics"),
]
SKIP = {"plugin/src/index.tsx"}   # MAKO Decky's own plugin entry; this plugin has its own


def git(repo, *args, check=True):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and p.returncode:
        raise SystemExit(p.stderr.decode(errors="replace"))
    return p


def version_key(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag)[:4])


def ours(up):
    for a, b in MAPS:
        if up == a or up.startswith(a + "/"):
            return b + up[len(a):]
    return None


def blob(repo, tag, path):
    p = git(repo, "show", f"{tag}:{path}", check=False)
    return p.stdout if p.returncode == 0 else None


def main():
    repo = Path(sys.argv[1])
    current = re.search(r'MAKO_VENDORED = "([^"]+)"', UPDATES.read_text()).group(1)
    base = f"plugin-v{current}"
    tags = [t for t in git(repo, "tag").stdout.decode().split() if re.fullmatch(r"plugin-v\d+(\.\d+)*", t)]
    to = sys.argv[2] if len(sys.argv) > 2 else max(tags, key=version_key)
    if version_key(to) <= version_key(base):
        print(f"MAKO {current} is the newest ({to})")
        return 1
    version = to.removeprefix("plugin-v")
    print(f"MAKO {current} -> {version}")

    conflicts = []
    names = git(repo, "diff", "--name-status", "--no-renames", base, to, "--",
                *[a for a, _ in MAPS]).stdout.decode().splitlines()
    for line in names:
        status, up = line.split("\t", 1)
        if up in SKIP or "/tests/" in up:
            continue
        dest = ROOT / ours(up)
        if status == "D":
            if dest.exists():
                dest.unlink()
                print("removed", ours(up))
            continue
        new, old = blob(repo, to, up), blob(repo, base, up)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cur = dest.read_bytes() if dest.exists() else None
        if cur is None or old is None or cur == old:
            dest.write_bytes(new)
            print("updated" if cur is not None else "added", ours(up))
            continue
        b, t = dest.with_name(dest.name + ".base"), dest.with_name(dest.name + ".theirs")
        b.write_bytes(old)
        t.write_bytes(new)
        r = subprocess.run(["git", "merge-file", "-L", "MultiFrameGen", "-L", base, "-L", to, str(dest), str(b), str(t)])
        b.unlink()
        t.unlink()
        print("merged" if r.returncode == 0 else "CONFLICT", ours(up))
        if r.returncode:
            conflicts.append(ours(up))
    if (ROOT / "bin" / "mako-diagnostics").exists():
        os.chmod(ROOT / "bin" / "mako-diagnostics", 0o755)

    # the MAKO Renderer's release assets, downloaded at run time (multifg/mako_payload.py)
    pkg = json.loads(blob(repo, to, "plugin/package.json"))
    renderer = {
        "_note": f"MAKO Renderer release assets, copied from MAKO Decky's package.json ({to}). Downloaded at runtime "
                 "by multifg/mako_payload.py.",
        "version": pkg["version"],
        "remote_binary": pkg["remote_binary"],
    }
    (ROOT / "assets" / "mako" / "renderer.json").write_text(json.dumps(renderer, indent=2) + "\n")

    # what MAKO Decky's build generates from its release notes
    notes = blob(repo, to, "plugin/RELEASE_NOTES.md").decode()
    codename = re.search(r"^### Release codename:\s*(.+?)\s*$", notes, re.M).group(1)
    info = ROOT / "src" / "mako" / "config" / "releaseInfo.ts"
    info.write_text(re.sub(r'\{ version: "[^"]*", codename: "[^"]*" \}',
                           f'{{ version: "{version}", codename: "{codename}" }}', info.read_text()))

    UPDATES.write_text(UPDATES.read_text().replace(f'MAKO_VENDORED = "{current}"', f'MAKO_VENDORED = "{version}"'))
    credits = ROOT / "CREDITS.md"
    credits.write_text(credits.read_text().replace(f"`{base}`", f"`{to}`"))
    print(f"MAKO Renderer {pkg['remote_binary'][0]['version']}, codename {codename}")
    if conflicts:
        print("needs a hand merge:", ", ".join(conflicts))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
