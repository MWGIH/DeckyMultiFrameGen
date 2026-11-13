"""Finds Steam libraries and the games installed in them.

Adapted from Decky Framegen (BSD-3-Clause, Kurt Himebauch): see licenses/.
"""

import re
from pathlib import Path

import decky

LOSSLESS_SCALING_APPID = "993090"

# Steam tools that show up as "games" in appmanifests
_TOOL_PREFIXES = ("Proton", "Steam Linux Runtime", "Steamworks Common", "SteamVR", "Steam Audio")


def steam_root_candidates(home: Path) -> list[Path]:
    candidates = [
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / ".var" / "app" / "com.valvesoftware.Steam" / "home" / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / "home" / ".steam" / "steam",
    ]
    unique: list[Path] = []
    for c in candidates:
        if c not in unique:
            unique.append(c)
    return unique


# Where SteamOS and desktop Linux mount SD cards and USB drives (/run/media/mmcblk0p1, /run/media/deck/<label>, ...)
MEDIA_ROOTS = (Path("/run/media"), Path("/media"))
_VDF_PATH = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"', re.IGNORECASE)


def _vdf_library_paths(root: Path) -> list[Path]:
    """The "path" entries of a Steam root's libraryfolders.vdf (Steam keeps one in steamapps/ and one in config/)."""
    found: list[Path] = []
    for vdf in (root / "steamapps" / "libraryfolders.vdf", root / "config" / "libraryfolders.vdf"):
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for value in _VDF_PATH.findall(text):
            value = value.replace("\\\\", "\\").replace('\\"', '"')
            if value:
                found.append(Path(value))
    return found


def steamapps_dir(library: Path) -> Path | None:
    """library/steamapps, also when a drive formatted on Windows calls it SteamApps."""
    plain = library / "steamapps"
    try:
        if plain.is_dir():
            return plain
        for child in library.iterdir():
            if child.name.lower() == "steamapps" and child.is_dir():
                return child
    except OSError:
        pass
    return None


def _media_libraries(media_roots=None) -> list[Path]:
    """Steam libraries on mounted SD cards and drives, for when libraryfolders.vdf doesn't list them (or can't be read).
    Looks at each mount and one level below it (/run/media/<user>/<label>), at the mount itself and a SteamLibrary folder."""
    mounts: list[Path] = []
    for media in MEDIA_ROOTS if media_roots is None else media_roots:
        try:
            children = sorted(media.iterdir())
        except OSError:
            continue
        for child in children:
            mounts.append(child)
            try:
                if child.is_dir() and not steamapps_dir(child):
                    mounts.extend(sorted(c for c in child.iterdir() if c.is_dir()))
            except OSError:
                continue
    found: list[Path] = []
    for mount in mounts:
        for library in (mount, mount / "SteamLibrary"):
            if steamapps_dir(library):
                found.append(library)
    return found


def library_paths(home: Path, media_roots=None) -> list[Path]:
    """Every Steam library folder: the Steam roots, the paths listed in libraryfolders.vdf, and Steam libraries
    on mounted SD cards and drives. The same folder reached two ways (/run/media/mmcblk0p1 is a link to
    /run/media/deck/<label> on SteamOS) is listed once."""
    paths: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except (OSError, RuntimeError):
            key = str(p)
        if key not in seen:
            seen.add(key)
            paths.append(p)

    for root in steam_root_candidates(home):
        if root.exists():
            add(root.resolve())
        for p in _vdf_library_paths(root):
            add(p)
    for p in _media_libraries(media_roots):
        add(p)
    return paths


def _acf_field(text: str, name: str) -> str:
    key = f'"{name}"'
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(key.lower()):
            return stripped[len(key):].strip().strip('"')
    return ""


# StateFlags bit 4 is "fully installed"; manifests also exist for games that are queued, downloading or half removed
_STATE_FULLY_INSTALLED = 4


def _fully_installed(text: str) -> bool:
    flags = _acf_field(text, "StateFlags")
    if not flags.isdigit():
        return True  # older manifests without the field: trust the install folder
    return bool(int(flags) & _STATE_FULLY_INSTALLED)


def _settled(text: str) -> bool:
    """True when Steam isn't doing anything to the game: no update queued, running or paused, not being verified."""
    flags = _acf_field(text, "StateFlags")
    return not flags.isdigit() or int(flags) == _STATE_FULLY_INSTALLED


def installed_games(home: Path, appid: str | None = None, media_roots=None) -> list[dict]:
    """Installed Steam games as {appid, name, install_path, install_found}, sorted by name."""
    games: dict[str, dict] = {}
    for library in library_paths(home, media_roots):
        steamapps = steamapps_dir(library)
        if not steamapps:
            continue
        pattern = f"appmanifest_{appid}.acf" if appid else "appmanifest_*.acf"
        try:
            manifests = list(steamapps.glob(pattern))
        except OSError as exc:
            decky.logger.warning(f"can't read Steam library {steamapps}: {exc}")
            continue
        for manifest in manifests:
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                decky.logger.warning(f"can't read {manifest}: {exc}")
                continue
            gid = _acf_field(text, "appid")
            name = _acf_field(text, "name")
            if not gid or not name or name.startswith(_TOOL_PREFIXES):
                continue
            install_dir = _acf_field(text, "installdir")
            install_path = _common_dir(steamapps) / install_dir if install_dir else None
            game = {
                "appid": gid,
                "name": name,
                "install_path": str(install_path) if install_path else "",
                "install_found": bool(install_path and install_path.is_dir()) and _fully_installed(text),
                "settled": _settled(text),
            }
            # a leftover manifest in one library mustn't hide the game installed in another (moved to the SD card)
            if gid not in games or not games[gid]["install_found"]:
                games[gid] = game
    return sorted(games.values(), key=lambda g: g["name"].lower())


def _common_dir(steamapps: Path) -> Path:
    plain = steamapps / "common"
    if plain.is_dir():
        return plain
    try:
        for child in steamapps.iterdir():
            if child.name.lower() == "common" and child.is_dir():
                return child
    except OSError:
        pass
    return plain


def is_installed(home: Path, appid: str) -> bool:
    return any(g["appid"] == appid for g in installed_games(home, appid))
