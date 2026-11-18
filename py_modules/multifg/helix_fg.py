"""HelixSR's own frame generation (HelixSR 3.4+) in a game set up with HelixSR Scaler.

HelixSR's setup builds it into the game as OptiScaler/custom/HelixSR-FG (an nvngx_dlssg.dll replacement); the game's
DLSS Frame Generation switch then runs it. Getting a DirectX 12 game to offer DLSS Frame Generation on the Deck needs
more of OptiScaler.ini than HelixSR's installer sets:
- FGInput=NvngxFG with FGNvngxReplacement=HelixSR-FG: the game's DLSSG calls go to HelixSR's DLL
- SpoofHAGS=true: games only offer DLSSG with hardware GPU scheduling, which Proton doesn't report
- Dxgi=true and LoadAsiPlugins=false: games check for an NVIDIA GPU; OptiPatcher (an .asi plugin) and some of
  OptiScaler's per-game defaults switch DXGI spoofing off again (seen in Marvel's Spider-Man Miles Morales)

OptiScaler's Streamline (OptiScaler/streamline) is newer than most games' own and replaces it. When it lacks a plugin
the game ships (sl.dlss.dll in HelixSR Scaler 2.3.1), OptiScaler warns "You are missing the following dlls from the
streamline folder"; the missing ones come from NVIDIA's Streamline SDK of the same version."""

import json
import re
import struct
import zlib
from pathlib import Path

from . import updates
from .helix_opti import INI, _read, _write, ini_get, ini_set

FG_DIR = Path("OptiScaler") / "custom" / "HelixSR-FG"
FG_DLL = FG_DIR / "dlssg" / "nvngx_dlssg.dll"
FG_LOG = FG_DIR / "dlssg" / "helixsr_fg.log"
SL_DIR = Path("OptiScaler") / "streamline"
RECORD = Path("OptiScaler") / "multifg-helixsr-fg.json"
SL_RECORD = Path("OptiScaler") / "multifg-streamline.json"   # the plugins fix_streamline added
SDK_URL = "https://github.com/NVIDIA-RTX/Streamline/releases/download/v{v}/streamline-sdk-v{v}.zip"

SETTINGS = {
    ("FrameGen", "FGInput"): "NvngxFG",
    ("FrameGen", "FGNvngxReplacement"): "HelixSR-FG",
    ("Spoofing", "SpoofHAGS"): "true",
    ("Spoofing", "Dxgi"): "true",
    ("Plugins", "LoadAsiPlugins"): "false",
}

# OptiScaler's frame generation switched off (by MultiFrameGen for MAKO, or by hand) also stops HelixSR's: these go
# back to OptiScaler's defaults while HelixSR's frame generation is on
FG_BLOCKERS = {("FrameGen", "Enabled"): "false", ("FrameGen", "FGOutput"): "nofg"}


def available(exe_folder: str | Path) -> bool:
    """HelixSR's frame generation is in the game (its setup built it and the installer copied it)."""
    return (Path(exe_folder) / FG_DLL).is_file()


def enabled(exe_folder: str | Path) -> bool | None:
    p = Path(exe_folder) / INI
    if not p.is_file():
        return None
    text = _read(p)
    return all((ini_get(text, s, k) or "").lower() == v.lower() for (s, k), v in SETTINGS.items())


def switch(exe_folder: str | Path, on: bool) -> bool | None:
    """On: OptiScaler.ini gets SETTINGS, its earlier values kept in RECORD. Off: they go back (keys changed by hand
    since stay as they are). None when the game has no OptiScaler.ini."""
    folder = Path(exe_folder)
    p = folder / INI
    if not p.is_file():
        return None
    rec = folder / RECORD
    text = _read(p)
    if on:
        try:
            previous = json.loads(rec.read_text()).get("previous", {})
        except (OSError, ValueError):
            previous = {}
        for (s, k), v in SETTINGS.items():
            previous.setdefault(f"{s}/{k}", ini_get(text, s, k))
            text = ini_set(text, s, k, v)
        for (s, k), off in FG_BLOCKERS.items():
            if (ini_get(text, s, k) or "").lower() == off:
                previous.setdefault(f"{s}/{k}", off)
                text = ini_set(text, s, k, "auto")
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(json.dumps({"previous": previous}, indent=1) + "\n")
    else:
        try:
            previous = json.loads(rec.read_text()).get("previous", {})
        except (OSError, ValueError):
            previous = {}
        for (s, k), v in SETTINGS.items():
            if (ini_get(text, s, k) or "").lower() == v.lower():
                text = ini_set(text, s, k, previous.get(f"{s}/{k}") or "auto")
        for (s, k), off in FG_BLOCKERS.items():
            if previous.get(f"{s}/{k}") == off and (ini_get(text, s, k) or "").lower() == "auto":
                text = ini_set(text, s, k, off)
        rec.unlink(missing_ok=True)
    _write(p, text)
    return enabled(folder)


def pe_version(path: str | Path) -> str | None:
    """A Windows DLL's file version (a.b.c), from its VS_FIXEDFILEINFO."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    # the signature's bytes can also occur in code: the real one is followed by struct version 1.0
    for m in re.finditer(re.escape(struct.pack("<II", 0xFEEF04BD, 0x10000)), data):
        ms, ls = struct.unpack_from("<II", data, m.start() + 8)
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}"
    return None


def _is_sl(name: str) -> bool:
    n = name.lower()
    return (n.startswith("sl.") and n.endswith(".dll") and n != "sl.interposer.dll") or n == "nvlowlatencyvk.dll"


def streamline(exe_folder: str | Path) -> dict:
    """The game's Streamline plugins OptiScaler's Streamline folder lacks, and that folder's version."""
    folder = Path(exe_folder)
    sl = folder / SL_DIR
    if not sl.is_dir():
        return {"version": None, "missing": []}
    have = {f.name.lower() for f in sl.iterdir()}
    game = sorted(f.name for f in folder.iterdir() if f.is_file() and _is_sl(f.name))
    return {"version": pe_version(sl / "sl.common.dll"),
            "missing": [n for n in game if n.lower() not in have]}


# Through curl like the plugin's other downloads: Decky's bundled Python can't verify HTTPS certificates on the Deck
def _range(url: str, start: int, end: int) -> bytes:
    p = updates._curl(["-L", "-r", f"{start}-{end}", "-w", "\n%{http_code}", url])
    body, _, code = p.stdout.rpartition(b"\n")
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace").strip()[-200:] or "download failed")
    if code != b"206":   # a server ignoring Range would send the whole 260 MB SDK
        raise ValueError(f"no range support (HTTP {code.decode()})")
    return body


def _size(url: str) -> int:
    p = updates._curl(["-fsIL", url])
    sizes = re.findall(rb"(?im)^content-length:\s*(\d+)", p.stdout)
    if p.returncode or not sizes:
        raise RuntimeError(p.stderr.decode(errors="replace").strip()[-200:] or "not found")
    return int(sizes[-1])


def zip_members(url: str, wanted: set[str]) -> dict[str, bytes]:
    """Members of a remote zip whose base name is in wanted (lower case), fetched with range requests: a few hundred
    KB instead of NVIDIA's 260 MB SDK."""
    size = _size(url)
    tail = _range(url, max(0, size - 65536), size - 1)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("not a zip (no end of central directory)")
    cd_size, cd_off = struct.unpack_from("<II", tail, eocd + 12)
    if cd_off == 0xFFFFFFFF:   # zip64
        z = tail.rfind(b"PK\x06\x06")
        cd_size, cd_off = struct.unpack_from("<QQ", tail, z + 40)
    cd = _range(url, cd_off, cd_off + cd_size - 1)
    out, i = {}, 0
    while i + 46 <= len(cd) and cd[i:i + 4] == b"PK\x01\x02":
        method = struct.unpack_from("<H", cd, i + 10)[0]
        csize, usize = struct.unpack_from("<II", cd, i + 20)
        n, m, k = struct.unpack_from("<HHH", cd, i + 28)
        offset = struct.unpack_from("<I", cd, i + 42)[0]
        name = cd[i + 46:i + 46 + n].decode(errors="replace")
        extra = cd[i + 46 + n:i + 46 + n + m]
        if 0xFFFFFFFF in (usize, csize, offset):   # zip64 sizes and offset, in that order, for those that overflowed
            j = 0
            while j + 4 <= len(extra):
                hid, hlen = struct.unpack_from("<HH", extra, j)
                if hid == 1:
                    vals = list(struct.unpack_from("<" + "Q" * (hlen // 8), extra, j + 4))
                    if usize == 0xFFFFFFFF:
                        usize = vals.pop(0)
                    if csize == 0xFFFFFFFF:
                        csize = vals.pop(0)
                    if offset == 0xFFFFFFFF:
                        offset = vals.pop(0)
                j += 4 + hlen
        base = name.rsplit("/", 1)[-1].lower()
        if base in wanted and "/bin/x64/" in f"/{name.lower()}" and base not in out:
            head = _range(url, offset, offset + 29)
            fn, fe = struct.unpack_from("<HH", head, 26)
            start = offset + 30 + fn + fe
            raw = _range(url, start, start + csize - 1)
            data = zlib.decompress(raw, -15) if method == 8 else raw
            if len(data) != usize:
                raise ValueError(f"{name}: unpacked {len(data)} bytes, expected {usize}")
            out[base] = data
        i += 46 + n + m + k
    return out


def fix_streamline(exe_folder: str | Path) -> dict:
    """Downloads the Streamline plugins OptiScaler's Streamline folder lacks, from NVIDIA's SDK of its version."""
    folder = Path(exe_folder)
    s = streamline(folder)
    if not s["missing"]:
        return {"ok": True, "added": []}
    if not s["version"] or not re.fullmatch(r"\d+\.\d+\.\d+", s["version"]):
        return {"ok": False, "error": "Couldn't read the version of OptiScaler's Streamline (sl.common.dll)"}
    try:
        got = zip_members(SDK_URL.format(v=s["version"]), {n.lower() for n in s["missing"]})
    except Exception as exc:   # network, a version NVIDIA never released, a broken zip
        return {"ok": False, "error": f"Couldn't get Streamline {s['version']} from NVIDIA: {exc}"}
    added = []
    for name in s["missing"]:
        data = got.get(name.lower())
        if data is None:
            continue
        tmp = folder / SL_DIR / (name + ".multifg-new")
        tmp.write_bytes(data)
        tmp.replace(folder / SL_DIR / name)
        added.append(name)
    try:
        before = json.loads((folder / SL_RECORD).read_text()).get("added", [])
    except (OSError, ValueError):
        before = []
    (folder / SL_RECORD).write_text(json.dumps({"added": sorted(set(before) | set(added))}, indent=1) + "\n")
    left = [n for n in s["missing"] if n not in added]
    return {"ok": not left, "added": added, "missing": left,
            **({"error": f"Not in Streamline {s['version']}: {', '.join(left)}"} if left else {})}


def cleanup(exe_folder: str | Path) -> None:
    """After HelixSR's removal (it only takes out the files it installed): the Streamline plugins fix_streamline
    added, the records, and OptiScaler's folders when that leaves them empty."""
    folder = Path(exe_folder)
    try:
        added = json.loads((folder / SL_RECORD).read_text()).get("added", [])
    except (OSError, ValueError):
        added = []
    for name in added:
        (folder / SL_DIR / Path(name).name).unlink(missing_ok=True)
    for rec in (SL_RECORD, RECORD):
        (folder / rec).unlink(missing_ok=True)
    for d in (folder / SL_DIR, folder / "OptiScaler"):
        try:
            d.rmdir()
        except OSError:
            pass


def fg_log(exe_folder: str | Path, lines: int = 8) -> dict | None:
    p = Path(exe_folder) / FG_LOG
    try:
        text = p.read_text(errors="replace")
        return {"path": str(p), "modified": p.stat().st_mtime, "lines": text.splitlines()[-lines:],
                "started": "frame generation started" in text}
    except OSError:
        return None


def status(exe_folder: str | Path) -> dict:
    return {"available": available(exe_folder), "enabled": enabled(exe_folder),
            "streamline": streamline(exe_folder), "log": fg_log(exe_folder)}
