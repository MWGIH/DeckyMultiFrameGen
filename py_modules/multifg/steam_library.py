"""Finds Steam libraries and the games installed in them.

Adapted from Decky Framegen (BSD-3-Clause, Kurt Himebauch): see licenses/.
"""

from pathlib import Path

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


def library_paths(home: Path) -> list[Path]:
    """Every Steam library folder: the Steam roots plus the paths listed in libraryfolders.vdf."""
    paths: list[Path] = []
    for root in steam_root_candidates(home):
        if root.exists():
            _add_unique(paths, root.resolve())
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if '"path"' not in line:
                continue
            value = line.split('"path"', 1)[1].strip().strip('"').replace("\\\\", "/")
            if value:
                _add_unique(paths, Path(value))
    return paths


def _add_unique(paths: list[Path], p: Path) -> None:
    if p not in paths:
        paths.append(p)


def _acf_field(text: str, name: str) -> str:
    key = f'"{name}"'
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(key):
            return stripped[len(key):].strip().strip('"')
    return ""


def installed_games(home: Path, appid: str | None = None) -> list[dict]:
    """Installed Steam games as {appid, name, install_path, install_found}, sorted by name."""
    games: dict[str, dict] = {}
    for library in library_paths(home):
        steamapps = library / "steamapps"
        if not steamapps.is_dir():
            continue
        pattern = f"appmanifest_{appid}.acf" if appid else "appmanifest_*.acf"
        for manifest in steamapps.glob(pattern):
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            gid = _acf_field(text, "appid")
            name = _acf_field(text, "name")
            if not gid or not name or name.startswith(_TOOL_PREFIXES):
                continue
            install_dir = _acf_field(text, "installdir")
            install_path = steamapps / "common" / install_dir if install_dir else None
            games[gid] = {
                "appid": gid,
                "name": name,
                "install_path": str(install_path) if install_path else "",
                "install_found": bool(install_path and install_path.is_dir()),
            }
    return sorted(games.values(), key=lambda g: g["name"].lower())


def is_installed(home: Path, appid: str) -> bool:
    return any(g["appid"] == appid for g in installed_games(home, appid))
