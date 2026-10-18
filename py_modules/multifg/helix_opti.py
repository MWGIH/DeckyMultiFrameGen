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
    if not (src / DLL).is_file():
        return {"ok": False, "error": "HelixSR isn't set up yet."}
    mod = t / MOD_DIR
    mod.mkdir(exist_ok=True)
    for name in (OWN, OWN_SR):
        tmp = mod / (name + ".multifg-new")
        shutil.copyfile(src / DLL, tmp)
        tmp.replace(mod / name)
    for n in NETWORK:
        if _embedded_network(src / DLL):
            (mod / n).unlink(missing_ok=True)
        else:
            shutil.copyfile(src / n, mod / n)
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
