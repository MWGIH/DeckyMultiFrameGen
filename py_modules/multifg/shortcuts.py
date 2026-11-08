"""Non-Steam games added to Steam ("Add a non-Steam game", Heroic's or Lutris' "Add to Steam", store clients such as
the EA app): their Steam shortcuts, and the folder the game itself is in.

Reading shortcuts.vdf and the Heroic / Lutris lookups are adapted from HelixSR Manager (Unlicense, PeroTuncay).
"""

import json
import os
import re
import struct
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import steam_library

# size caps for what's read from other programs, so a broken or huge file can't stall the panel
MAX_VDF, MAX_JSON, MAX_YML, MAX_DB = 8 << 20, 16 << 20, 128 << 10, 256 << 20

# Store clients: a shortcut that starts one of these runs the client (or a game through it), so the exe's folder is
# the client's, not a game's
CLIENT_EXES = {
    "battle.net.exe": "Battle.net", "battle.net launcher.exe": "Battle.net",
    "eadesktop.exe": "EA app", "ealauncher.exe": "EA app", "origin.exe": "Origin",
    "upc.exe": "Ubisoft Connect", "ubisoftconnect.exe": "Ubisoft Connect", "uplay.exe": "Ubisoft Connect",
    "epicgameslauncher.exe": "Epic Games Launcher", "galaxyclient.exe": "GOG Galaxy",
    "amazon games.exe": "Amazon Games", "amazon games ui.exe": "Amazon Games", "itch.exe": "itch",
    "playnite.desktopapp.exe": "Playnite", "playnite.fullscreenapp.exe": "Playnite",
    "rockstarservice.exe": "Rockstar Games Launcher",
}
# Shortcuts that start a game through a Linux launcher (worth listing even before a folder is known)
LAUNCH_HINTS = (("heroic://", "Heroic"), ("heroic", "Heroic"), ("lutris:rungame", "Lutris"), ("lutris", "Lutris"),
                ("legendary launch", "Legendary"), ("bottles-cli run", "Bottles"), ("bottles", "Bottles"))


def _heroic_dirs(home: Path) -> list[Path]:
    return [home / ".config/heroic", home / ".var/app/com.heroicgameslauncher.hgl/config/heroic"]


def _lutris_dbs(home: Path) -> list[Path]:
    return [home / ".local/share/lutris/pga.db", home / ".var/app/net.lutris.Lutris/data/lutris/pga.db"]


def _lutris_config_dirs(home: Path) -> list[Path]:
    return [home / ".config/lutris/games", home / ".local/share/lutris/games",
            home / ".var/app/net.lutris.Lutris/config/lutris/games", home / ".var/app/net.lutris.Lutris/data/lutris/games"]


def _read_capped(path: Path, limit: int) -> bytes | None:
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _read_json(path: Path):
    raw = _read_capped(path, MAX_JSON)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def read_binary_vdf(data: bytes) -> dict:
    """Steam's binary KeyValues (shortcuts.vdf): 0x00 nested map, 0x01 string, 0x02 int32, 0x07 uint64, 0x08 end."""
    pos = 0

    def cstr() -> str:
        nonlocal pos
        end = data.index(b"\0", pos)
        s = data[pos:end].decode("utf-8", "replace")
        pos = end + 1
        return s

    def node() -> dict:
        nonlocal pos
        out: dict = {}
        while pos < len(data):
            t = data[pos]
            pos += 1
            if t == 0x08:
                return out
            key = cstr()
            if t == 0x00:
                out[key] = node()
            elif t == 0x01:
                out[key] = cstr()
            elif t == 0x02:
                out[key] = struct.unpack_from("<i", data, pos)[0]
                pos += 4
            elif t == 0x07:
                out[key] = struct.unpack_from("<Q", data, pos)[0]
                pos += 8
            else:
                raise ValueError(f"unknown KeyValues type {t}")
        return out

    return node()


def _unquote(value: str) -> str:
    return str(value or "").strip().strip('"').strip()


def all_shortcuts(home: Path) -> list[dict]:
    """Every Steam user's non-Steam shortcuts: {appid (unsigned, as text), name, exe, start_dir, launch, steam_root}."""
    out, seen_files, seen_ids = [], set(), set()
    for root in steam_library.steam_root_candidates(home):
        try:
            files = list(root.glob("userdata/*/config/shortcuts.vdf"))
        except OSError:
            continue
        for f in files:
            try:
                key = f.resolve()
                if key in seen_files:
                    continue
                seen_files.add(key)
                raw = _read_capped(f, MAX_VDF)
                data = read_binary_vdf(raw) if raw else {}
            except (OSError, ValueError, struct.error, IndexError):
                continue
            for s in (data.get("shortcuts") or {}).values():
                if not isinstance(s, dict):
                    continue
                low = {k.lower(): v for k, v in s.items()}
                appid = int(low.get("appid") or 0) & 0xFFFFFFFF
                if not appid or appid in seen_ids:
                    continue
                seen_ids.add(appid)
                out.append({"appid": str(appid), "name": str(low.get("appname") or "").strip(),
                            "exe": _unquote(low.get("exe")), "start_dir": _unquote(low.get("startdir")),
                            "launch": str(low.get("launchoptions") or ""), "steam_root": str(root)})
    return out


def find(home: Path, appid: str) -> dict | None:
    return next((s for s in all_shortcuts(home) if s["appid"] == str(appid)), None)


def _exe_names(folder: str) -> list[str]:
    try:
        with os.scandir(folder) as it:
            return [e.name for e in it if e.is_file() and e.name.lower().endswith(".exe")]
    except OSError:
        return []


def _client(exe: str) -> str | None:
    """The store client a shortcut starts (EA app, Battle.net, ...), or None."""
    name = os.path.basename(exe).lower()
    if name in CLIENT_EXES:
        return CLIENT_EXES[name]
    return None


def game_root(folder: str) -> str:
    """An Unreal game's top folder for an exe in <game>/<project>/Binaries/Win64 (its upscaler DLLs sit under
    Engine/ and <project>/Plugins, next to Binaries); for Digital Extremes' launcher (Soulframe, Warframe:
    .../Downloaded/Public/Tools/Launcher.exe) the Public folder, where the launcher puts the game's .x64.exe;
    else the folder itself."""
    parts = Path(folder).parts
    if len(parts) > 3 and [p.lower() for p in parts[-3:]] == ["downloaded", "public", "tools"]:
        return str(Path(*parts[:-1]))
    if len(parts) > 4 and parts[-2].lower() == "binaries" and parts[-1].lower() in ("win64", "wingdk", "win32"):
        return str(Path(*parts[:-3]))
    return folder


def launcher(sc: dict) -> str | None:
    """What starts the game instead of its own .exe: a store client or a Linux launcher such as Heroic; None for a
    shortcut to the game's .exe."""
    client = _client(sc["exe"])
    if client:
        return client
    text = f"{sc['exe']} {sc['launch']}".lower()
    return next((label for hint, label in LAUNCH_HINTS if hint in text), None)


# --- Heroic ----------------------------------------------------------------------------------------------------------

_HEROIC_URL = re.compile(r"heroic://launch[^\s\"']*")


def heroic_app(launch: str) -> str | None:
    """The game id in Heroic's launch link: heroic://launch/<runner>/<id> or heroic://launch?appName=<id>&runner=..."""
    m = _HEROIC_URL.search(launch or "")
    if not m:
        return None
    url = urlparse(m.group(0))
    query = parse_qs(url.query)
    if query.get("appName"):
        return query["appName"][0]
    parts = [unquote(p) for p in (url.netloc + url.path).split("/") if p]
    # netloc is "launch"; the id is the last part (an older form has no runner)
    return parts[-1] if len(parts) >= 2 else None


def heroic_folder(home: Path, app: str) -> str | None:
    """Where Heroic installed a game (GOG, Epic, Amazon or a side-loaded one), by its id."""
    for base in _heroic_dirs(home):
        epic = _read_json(base / "legendaryConfig/legendary/installed.json")
        if isinstance(epic, dict) and isinstance(epic.get(app), dict):
            folder = epic[app].get("install_path")
            if isinstance(folder, str) and os.path.isdir(folder):
                return folder
        for rel in ("gog_store/installed.json", "nile_config/nile/installed.json", "nile_config/installed.json"):
            data = _read_json(base / rel)
            items = data.get("installed", data) if isinstance(data, dict) else data
            if isinstance(items, dict):
                items = list(items.values())
            for g in items if isinstance(items, list) else []:
                if not isinstance(g, dict) or app not in (g.get("appName"), g.get("id"), g.get("app_name")):
                    continue
                folder = g.get("install_path") or g.get("installPath") or g.get("path")
                if isinstance(folder, str) and os.path.isdir(folder):
                    return folder
        side = _read_json(base / "sideload_apps/library.json")
        for g in (side.get("games") if isinstance(side, dict) else None) or []:
            if isinstance(g, dict) and g.get("app_name") == app:
                exe = (g.get("install") or {}).get("executable") or ""
                if isinstance(exe, str) and os.path.isfile(exe):
                    return os.path.dirname(exe)
    legendary = [home / ".config/legendary/installed.json",
                 home / ".var/app/com.heroicgameslauncher.hgl/config/legendary/installed.json"]
    for f in legendary:
        data = _read_json(f)
        if isinstance(data, dict) and isinstance(data.get(app), dict):
            folder = data[app].get("install_path")
            if isinstance(folder, str) and os.path.isdir(folder):
                return folder
    return None


# --- Lutris ----------------------------------------------------------------------------------------------------------

_LUTRIS_ID = re.compile(r"lutris:rungameid/(\d+)")
_LUTRIS_SLUG = re.compile(r"lutris:rungame/([\w.-]+)")


def lutris_folder(home: Path, launch: str) -> str | None:
    """A Lutris game's folder, from its lutris:rungameid/<id> or lutris:rungame/<slug> link: the folder its config's
    exe is in, else the database's install directory."""
    by_id, by_slug = _LUTRIS_ID.search(launch or ""), _LUTRIS_SLUG.search(launch or "")
    if not by_id and not by_slug:
        return None
    for db in _lutris_dbs(home):
        row = _lutris_row(db, by_id.group(1) if by_id else None, by_slug.group(1) if by_slug else None)
        if not row:
            continue
        directory, configpath = row
        exe = _lutris_exe(home, configpath, directory)
        if exe:
            return os.path.dirname(exe)
        if directory and os.path.isdir(directory) and _exe_names(directory):
            return directory
    return None


def _lutris_row(db: Path, game_id: str | None, slug: str | None):
    try:
        if not db.is_file() or db.stat().st_size > MAX_DB:
            return None
        import sqlite3
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)
        try:
            con.execute("PRAGMA query_only = ON")
            if game_id:
                row = con.execute("SELECT directory, configpath FROM games WHERE id = ?", (int(game_id),)).fetchone()
            else:
                row = con.execute("SELECT directory, configpath FROM games WHERE slug = ? ORDER BY id DESC",
                                  (slug,)).fetchone()
        finally:
            con.close()
    except Exception:
        return None
    return (row[0] or "", row[1] or "") if row else None


def _lutris_exe(home: Path, configpath: str, directory: str) -> str | None:
    if not configpath or "/" in configpath:
        return None
    for d in _lutris_config_dirs(home):
        text = (_read_capped(d / f"{configpath}.yml", MAX_YML) or b"").decode("utf-8", "replace")
        if not text:
            continue
        field = lambda k: (re.search(r"(?m)^\s*%s:\s*['\"]?(.+?)['\"]?\s*$" % k, text) or [None, ""])[1]
        exe = field("exe")
        if not exe.lower().endswith(".exe"):
            return None
        bases = [""] if os.path.isabs(exe) else [directory, field("working_dir"), field("prefix")]
        for b in bases:
            p = os.path.expanduser(os.path.join(b, exe)) if b or os.path.isabs(exe) else ""
            if p and os.path.isabs(p) and os.path.isfile(p):
                return p
    return None


# --- the game's folder -----------------------------------------------------------------------------------------------

def prefix_drive_c(sc: dict) -> str | None:
    """The shortcut's own Proton prefix C: drive (where e.g. the EA app installs its games), if it has one."""
    p = Path(sc.get("steam_root") or "") / "steamapps" / "compatdata" / sc["appid"] / "pfx" / "drive_c"
    return str(p) if p.is_dir() else None


def evolution_folder(sc: dict) -> str | None:
    """A Digital Extremes game (Soulframe, Warframe) installed in the shortcut's own Proton prefix by its .msi:
    drive_c/users/steamuser/AppData/Local/<Game>/Downloaded/Public, where its launcher (Tools/Launcher.exe) puts the
    game's <Game>.x64.exe. The one named like the shortcut if there are several."""
    drive_c = prefix_drive_c(sc)
    if not drive_c:
        return None
    try:
        found = [p for p in Path(drive_c, "users", "steamuser", "AppData", "Local").glob("*/Downloaded/Public")
                 if p.is_dir() and (_exe_names(str(p)) or (p / "Tools").is_dir())]
    except OSError:
        return None
    if not found:
        return None
    name = re.sub(r"[^a-z0-9]", "", (sc.get("name") or "").lower())
    named = [p for p in found if re.sub(r"[^a-z0-9]", "", p.parent.parent.name.lower()) in name]
    return str((named or sorted(found))[0])


def resolve(home: Path, sc: dict) -> dict:
    """Where a shortcut's game is: {folder (or None), source: "shortcut" | "heroic" | "lutris" | None, launcher}."""
    exe, start, launch = sc["exe"], sc["start_dir"], sc["launch"]
    found = launcher(sc)
    client = _client(exe)
    folder, source = None, None
    if exe.lower().endswith(".exe") and os.path.isfile(exe) and not client:
        folder, source = game_root(os.path.dirname(exe)), "shortcut"
    elif not client and (de := evolution_folder(sc)):
        folder, source = de, "shortcut"
    elif not client and start and os.path.isdir(start) and (names := _exe_names(start)) \
            and not any(_client(n) for n in names):
        folder, source = game_root(start), "shortcut"
    elif found == "Heroic":
        app = heroic_app(f"{exe} {launch}")
        folder = heroic_folder(home, app) if app else None
        source = "heroic" if folder else None
    elif found == "Lutris":
        folder = lutris_folder(home, f"{exe} {launch}")
        source = "lutris" if folder else None
    return {"folder": os.path.normpath(folder) if folder else None, "source": source,
            "launcher": found if source != "shortcut" else None}


def record(home: Path, sc: dict, picked: str | None = None) -> dict:
    """A shortcut as a game record like steam_library.installed_games gives, plus where its folder came from.
    picked: the folder the user chose in the panel, which wins over everything found."""
    where = resolve(home, sc)
    folder, source = where["folder"], where["source"]
    if picked and os.path.isdir(picked):
        folder, source = os.path.normpath(picked), "picked"
    return {"appid": sc["appid"], "name": sc["name"] or (Path(folder).name if folder else f"App {sc['appid']}"),
            "install_path": folder or "", "install_found": bool(folder and os.path.isdir(folder)),
            "non_steam": True, "folder_source": source, "launcher": where["launcher"],
            "browse_start": prefix_drive_c(sc) or folder or str(home)}


def listed(home: Path, sc: dict, picked: str | None = None) -> bool:
    """Whether a shortcut belongs in the game picker: it has a game folder, or it starts a game through a launcher
    (its folder can then be chosen). Apps and emulators stay out."""
    if picked:
        return True
    return bool(resolve(home, sc)["folder"]) or launcher(sc) is not None
