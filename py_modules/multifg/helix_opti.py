"""HelixSR as a mod inside OptiScaler: HelixSR's DLL goes into a folder next to OptiScaler, and OptiScaler.ini points
OptiScaler's FSR 3.1 upscaler at it (the way HelixSR 1.5 to 1.8 installed into OptiScaler). The game's own files are
not touched, so this works with the OptiScaler Decky Framegen put in the game, also in games whose anti-cheat checks
the game's FSR DLL. In OptiScaler's menu HelixSR is the FSR 3.X upscaler.

Kept apart from HelixSR's own installer: its own folder name and record, so HelixSR's setup never mistakes it for one
of its installs (and the other way round)."""

import json
import re
import shutil
from pathlib import Path

DLL = "amd_fidelityfx_dx12.dll"              # HelixSR's built DLL in its release folder
# Where a release's setup leaves the built DLL: 2.0 builds it into HelixSR-fsrfg (and fsr3-drop-in), earlier
# releases into the release folder itself
BUILT = ("HelixSR-fsrfg/" + DLL, DLL, "fsr3-drop-in/" + DLL, "fsr3-drop-in/amd_fidelityfx_upscaler_dx12.dll")
NETWORK = ("helixsr_weights.bin", "helixsr_kernels.pak")
MOD_DIR = "HelixSR-OptiScaler"               # next to OptiScaler's DLL in the game
OWN = "helixsr.dll"                          # for FfxDx12Path (FSR 3.1 in one DLL)
OWN_SR = "helixsr_upscaler.dll"              # for FfxDx12SRPath (FSR 3.1's separate upscaler DLL)
RECORD = "multifg-helixsr.json"
INI = "OptiScaler.ini"


def win_path(p: Path) -> str:
    """The path as the game sees it under Proton (Z: is /)."""
    return "Z:" + str(p).replace("/", "\\")


def settings(mod: Path) -> dict:
    """(section, key) -> value OptiScaler.ini gets."""
    return {
        ("Libraries", "FfxDx12Path"): win_path(mod / OWN),
        ("Libraries", "FfxDx12SRPath"): win_path(mod / OWN_SR),
        # FSR4 would take the FSR 3.1 upscaler's place
        ("FSR", "Fsr4Update"): "false",
        ("Upscalers", "Dx12Upscaler"): "fsr31",
    }


def _key_re(key: str):
    return re.compile(r"(?m)^[ \t]*%s[ \t]*=[ \t]*(?P<val>[^\r\n]*?)[ \t]*(?=\r?$)" % re.escape(key))


def _section(text: str, section: str):
    """(start, end) of the section's body, or None."""
    m = re.search(r"(?m)^\[%s\][ \t]*\r?\n" % re.escape(section), text)
    if not m:
        return None
    nxt = re.search(r"(?m)^\[", text[m.end():])
    return m.end(), m.end() + nxt.start() if nxt else len(text)


def ini_get(text: str, section: str, key: str) -> str | None:
    span = _section(text, section)
    if not span:
        return None
    m = _key_re(key).search(text, *span)
    return m.group("val") if m else None


def ini_set(text: str, section: str, key: str, value: str) -> str:
    """key=value in [section]: the line is changed, else added at the start of the section (or a new section)."""
    span = _section(text, section)
    nl = "\r\n" if "\r\n" in text else "\n"
    if not span:
        return text.rstrip("\r\n") + f"{nl}{nl}[{section}]{nl}{key}={value}{nl}"
    m = _key_re(key).search(text, *span)
    if m:
        return text[:m.start("val")] + value + text[m.end("val"):]
    return text[:span[0]] + f"{key}={value}{nl}" + text[span[0]:]


def _read(p: Path) -> str:
    with open(p, encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def _write(p: Path, text: str) -> None:
    tmp = p.with_name(p.name + ".multifg-new")
    with open(tmp, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(text)
    tmp.replace(p)


def _embedded_network(dll: Path) -> bool:
    try:
        with open(dll, "rb") as f:
            f.seek(-32, 2)
            return f.read(8) == b"HXSRNET1"
    except OSError:
        return False


def built_dll(release_dir: str | Path) -> Path | None:
    """The release's DLL with the network the setup built: inside it (HXSRNET1) or as files next to it."""
    d = Path(release_dir)
    for rel in BUILT:
        dll = d / rel
        if dll.is_file() and (_embedded_network(dll) or all((dll.parent / n).is_file() for n in NETWORK)):
            return dll
    return None


def status(target_dir: str | Path) -> dict:
    t = Path(target_dir)
    mod = t / MOD_DIR
    installed = (mod / RECORD).is_file() and (mod / OWN).is_file()
    rec = {}
    if installed:
        try:
            rec = json.loads((mod / RECORD).read_text())
        except (OSError, ValueError):
            pass
    log = mod / "helixsr.log"
    lines = []
    if log.is_file():
        try:
            lines = log.read_text(errors="replace").splitlines()[-8:]
        except OSError:
            pass
    ini_ok = False
    if installed and (t / INI).is_file():
        text = _read(t / INI)
        ini_ok = all(ini_get(text, s, k) == v for (s, k), v in settings(mod).items())
    return {"ok": True, "installed": installed, "ini_ok": ini_ok, "helixsr": rec.get("helixsr"),
            "runtime_log": {"lines": lines, "modified": log.stat().st_mtime} if lines else None}


def install(release_dir: str | Path, target_dir: str | Path, tag: str) -> dict:
    """HelixSR into OptiScaler in target_dir (the folder with OptiScaler's DLL and OptiScaler.ini)."""
    src, t = Path(release_dir), Path(target_dir)
    if not (t / INI).is_file():
        return {"ok": False, "error": "OptiScaler isn't in this game. Patch it with OptiScaler first."}
    dll = built_dll(src)
    if not dll:
        return {"ok": False, "error": "HelixSR isn't set up yet."}
    mod = t / MOD_DIR
    mod.mkdir(exist_ok=True)
    for name in (OWN, OWN_SR):
        tmp = mod / (name + ".multifg-new")
        shutil.copyfile(dll, tmp)
        tmp.replace(mod / name)
    for n in NETWORK:
        if _embedded_network(dll):
            (mod / n).unlink(missing_ok=True)
        else:
            shutil.copyfile(dll.parent / n, mod / n)
    rec_path = mod / RECORD
    try:
        previous = json.loads(rec_path.read_text()).get("previous", {})
    except (OSError, ValueError):
        previous = {}
    text = _read(t / INI)
    for (s, k), v in settings(mod).items():
        previous.setdefault(f"{s}/{k}", ini_get(text, s, k))
        text = ini_set(text, s, k, v)
    _write(t / INI, text)
    rec_path.write_text(json.dumps({"helixsr": tag, "previous": previous}, indent=1) + "\n")
    return {"ok": True, "installed": True}


# OptiScaler's own frame generation off: MAKO generates the frames, and two frame generators must not run together
# (MAKO's docs: "disable their Frame Generation"). Decky Framegen turns it on (FGInput/FGOutput = nukems).
FG_OFF = {("FrameGen", "Enabled"): "false", ("FrameGen", "FGInput"): "nofg", ("FrameGen", "FGOutput"): "nofg"}


def frame_generation_off(target_dir: str | Path) -> bool:
    """OptiScaler.ini in target_dir with OptiScaler's frame generation off; False when there is no OptiScaler.ini."""
    p = Path(target_dir) / INI
    if not p.is_file():
        return False
    text = _read(p)
    new = text
    for (s, k), v in FG_OFF.items():
        new = ini_set(new, s, k, v)
    if new != text:
        _write(p, new)
    return True


def opti_logging(target_dir: str | Path, on: bool | None = None) -> bool | None:
    """OptiScaler's log file (off by default) in target_dir's OptiScaler.ini: switched when on is given, then read.
    On, it writes OptiScaler.log next to OptiScaler.ini at the Info level. None when there is no OptiScaler.ini."""
    p = Path(target_dir) / INI
    if not p.is_file():
        return None
    text = _read(p)
    if on is not None:
        new = ini_set(text, "Log", "LogToFile", "true" if on else "auto")
        new = ini_set(new, "Log", "LogLevel", "2" if on else "auto")
        new = ini_set(new, "Log", "LogFileName", win_path(Path(target_dir) / "OptiScaler.log") if on else "auto")
        if new != text:
            _write(p, new)
            text = new
    return (ini_get(text, "Log", "LogToFile") or "").lower() == "true"


def opti_log(target_dir: str | Path, lines: int = 15) -> dict | None:
    """The end of OptiScaler.log in target_dir (where a game that stops got to), or None when there is none."""
    log = Path(target_dir) / "OptiScaler.log"
    try:
        size = log.stat().st_size
        with open(log, "rb") as f:
            f.seek(max(0, size - 16384))   # the log grows by megabytes; its end is what counts
            text = f.read().decode(errors="replace")
        return {"path": str(log), "modified": log.stat().st_mtime, "lines": text.splitlines()[-lines:]}
    except OSError:
        return None


def uninstall(target_dir: str | Path) -> dict:
    """HelixSR out of OptiScaler: OptiScaler.ini gets its earlier values back and the mod's folder goes."""
    t = Path(target_dir)
    mod = t / MOD_DIR
    if not mod.exists():
        return {"ok": True, "removed": False}
    try:
        previous = json.loads((mod / RECORD).read_text()).get("previous", {})
    except (OSError, ValueError):
        previous = {}
    if (t / INI).is_file():
        text = _read(t / INI)
        for (s, k), v in settings(mod).items():
            old = previous.get(f"{s}/{k}")
            if ini_get(text, s, k) == v:   # changed by hand since: left as it is
                text = ini_set(text, s, k, old if old is not None else "auto")
        _write(t / INI, text)
    shutil.rmtree(mod, ignore_errors=True)
    return {"ok": True, "removed": True}
