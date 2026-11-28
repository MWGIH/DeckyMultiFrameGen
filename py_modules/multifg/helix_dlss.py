"""HLX DLSS's speed settings in helixsr.ini (HelixSR 3.4+), per game.

HelixSR reads helixsr.ini next to its DLL: [Upscaling] DeepReuse (exact, 1:2, 1:4) and NetworkResolution (full, fast).
Under HelixSR Scaler, [HelixSR] DeepReuse in OptiScaler.ini is the supported place for the first (HelixSR 3.4.1 writes
it to helixsr.ini at every game start, next to the settings it manages, and keeps the rest of the file), so a Scaler
install gets both: OptiScaler.ini's value and the same one in helixsr.ini. NetworkResolution has no OptiScaler.ini key;
its only home is helixsr.ini, which HelixSR Scaler leaves intact.

HelixSR's own bridge only accepts a fixed allow-list of settings, which has neither key, so the plugin edits the ini
itself. Values HelixSR doesn't know fall back to its defaults; "default" here means the key is not set (commented out)
and, for a Scaler install, OptiScaler.ini's DeepReuse is auto."""

import re
from pathlib import Path

from . import helix_opti

INI = "helixsr.ini"
SECTION = "Upscaling"
SCALER_DIRS = ("HelixSR", "HelixSR-fsrfg")    # HelixSR 3.4's ngx layout, then 2.0's
SCALER_DLLS = {"HelixSR": "helixsr.dll", "HelixSR-fsrfg": "amd_fidelityfx_dx12.dll"}
OPTI_DIR = "HelixSR-OptiScaler"               # HelixSR as a mod inside OptiScaler
VALUES = {"deep_reuse": ("exact", "1:2", "1:4"), "network_resolution": ("full", "fast")}
SINCE = (3, 4)                                # HLX DLSS's speed settings arrived in HelixSR 3.4
HEADER = ("; helixsr.ini - HLX DLSS settings written by Decky MultiFrameGen's game panel.\n"
          "; Every other setting keeps HelixSR's default; restart the game after a change.\n")


def _line_re(key: str, commented: bool = False):
    prefix = r"[ \t]*[;#][ \t]*" if commented else r"[ \t]*"
    return re.compile(r"(?mi)^%s%s[ \t]*=[ \t]*(?P<val>[^\r\n]*?)[ \t]*(?=\r?$)" % (prefix, re.escape(key)))


def ini_get(text: str, key: str, section: str = SECTION) -> str | None:
    """The key's active value in [section] (case-insensitive, like HelixSR's own ini reader), or None."""
    span = helix_opti._section(text, section)
    if not span:
        return None
    m = _line_re(key).search(text, *span)
    return m.group("val") if m else None


def ini_set(text: str, key: str, value: str, section: str = SECTION) -> str:
    """Key = value in [section]: an active line is changed, else the last commented example line becomes the setting,
    else it is added at the top of the section. Every other line stays as it is."""
    span = helix_opti._section(text, section)
    nl = "\r\n" if "\r\n" in text else "\n"
    line = f"{key} = {value}"
    if not span:
        return text.rstrip("\r\n") + f"{nl}{nl}[{section}]{nl}{line}{nl}"
    start, end = span
    lines = text[start:end].splitlines(keepends=True)
    active = [i for i, l in enumerate(lines) if _line_re(key).match(l)]
    if active:
        first = active[0]
        ending = lines[first][len(lines[first].rstrip("\r\n")):]
        lines[first] = line + ending
        for i in active[1:]:   # a duplicate key: HelixSR's bridge comments the others out too
            lines[i] = ";" + lines[i].lstrip(" \t")
    else:
        commented = [i for i, l in enumerate(lines) if _line_re(key, True).match(l)]
        if commented:
            last = commented[-1]
            ending = lines[last][len(lines[last].rstrip("\r\n")):]
            lines[last] = line + ending
        else:
            lines.insert(0, line + nl)
    return text[:start] + "".join(lines) + text[end:]


def ini_unset(text: str, key: str, section: str = SECTION) -> str:
    """Comments the key's active line(s) out, as HelixSR's bridge does for a setting it removes; other lines stay."""
    span = helix_opti._section(text, section)
    if not span:
        return text
    start, end = span
    body = _line_re(key).sub(lambda m: ";" + m.group(0), text[start:end])
    return text[:start] + body + text[end:]


def _value(name: str, value: str | None) -> str | None:
    """The value checked against the setting's allowed set; default stays default, None means no change."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if v == "default":
        return v
    if v not in VALUES[name]:
        raise ValueError(f"{name}: {value!r} isn't one of default, {', '.join(VALUES[name])}")
    return v


def supports(version: str | None) -> bool:
    """Whether a HelixSR version has HLX DLSS's DeepReuse / NetworkResolution (3.4 and newer)."""
    nums = tuple(int(x) for x in re.findall(r"\d+", str(version or ""))[:3])
    return len(nums) >= 2 and nums >= SINCE


def resolve(exe_folder: str | Path, route: str, fsr_targets: list[str] | None = None,
            ini_hint: str | None = None) -> dict | None:
    """Where a route keeps HelixSR's files: {ini, opti}. ini is helixsr.ini; opti is the game's OptiScaler.ini, which
    HelixSR Scaler takes DeepReuse from (None for the other routes). None when the route isn't in the game."""
    exe = Path(exe_folder)
    if route == "direct":
        # the FSR drop-in: helixsr.ini sits next to the game's FSR DLL (HelixSR's own settings_dir does the same)
        candidates = ([Path(ini_hint)] if ini_hint else []) + [Path(t).parent / INI for t in fsr_targets or ()]
        return {"ini": candidates[0], "opti": None} if candidates else None
    if route == "optiscaler":
        mod = exe / OPTI_DIR
        return {"ini": mod / INI, "opti": None} if mod.is_dir() else None
    if route == "scaler":
        for name in SCALER_DIRS:
            if (exe / name / INI).is_file():
                return {"ini": exe / name / INI, "opti": exe / "OptiScaler.ini"}
        for name in SCALER_DIRS:
            if (exe / name / SCALER_DLLS[name]).is_file():
                return {"ini": exe / name / INI, "opti": exe / "OptiScaler.ini"}
        return {"ini": exe / SCALER_DIRS[0] / INI, "opti": exe / "OptiScaler.ini"}
    return None


def status(exe_folder: str | Path, route: str, fsr_targets: list[str] | None = None,
           ini_hint: str | None = None) -> dict:
    """The game's current HLX DLSS speed settings; "default" means HelixSR's own default applies."""
    r = resolve(exe_folder, route, fsr_targets, ini_hint)
    if not r:
        return {"ok": False, "error": "HLX DLSS isn't in this game"}
    ini, opti = r["ini"], r["opti"]
    text = helix_opti._read(ini) if ini.is_file() else ""
    opti_text = helix_opti._read(opti) if opti and opti.is_file() else ""
    deep = None
    if route == "scaler" and opti_text:
        # Scaler's setting wins; auto means "exact, or what helixsr.ini says"
        v = (helix_opti.ini_get(opti_text, "HelixSR", "DeepReuse") or "").strip().lower()
        deep = v if v in VALUES["deep_reuse"] else None
    if deep is None:
        v = (ini_get(text, "DeepReuse") or "").strip().lower()
        deep = v if v in VALUES["deep_reuse"] else None
    net = (ini_get(text, "NetworkResolution") or "").strip().lower()
    return {"ok": True, "route": route, "ini": str(ini), "ini_exists": ini.is_file(),
            "opti_ini": str(opti) if opti and opti.is_file() else None,
            # exact and full are HelixSR's defaults: the panel shows them as Default / Full
            "deep_reuse": "default" if deep in (None, "exact") else deep,
            "network_resolution": net if net in ("full", "fast") else "full"}


def apply(exe_folder: str | Path, route: str, fsr_targets: list[str] | None = None,
          ini_hint: str | None = None, deep_reuse: str | None = None,
          network_resolution: str | None = None) -> dict:
    """Sets the given settings (None: unchanged; "default": HelixSR's default again), then returns status()."""
    r = resolve(exe_folder, route, fsr_targets, ini_hint)
    if not r:
        return {"ok": False, "error": "HLX DLSS isn't in this game"}
    try:
        deep = _value("deep_reuse", deep_reuse)
        net = _value("network_resolution", network_resolution)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    ini = r["ini"]
    text = helix_opti._read(ini) if ini.is_file() else HEADER
    new = text
    if deep is not None:
        new = ini_unset(new, "DeepReuse") if deep == "default" else ini_set(new, "DeepReuse", deep)
    if net is not None:
        new = ini_unset(new, "NetworkResolution") if net == "default" else ini_set(new, "NetworkResolution", net)
    # a Scaler install reads DeepReuse from OptiScaler.ini and copies it to helixsr.ini at game start
    if route == "scaler" and deep is not None and r["opti"] and r["opti"].is_file():
        opti_text = helix_opti._read(r["opti"])
        changed = helix_opti.ini_set(opti_text, "HelixSR", "DeepReuse", "auto" if deep == "default" else deep)
        if changed != opti_text:
            helix_opti._write(r["opti"], changed)
    # nothing to write (a default with no override in place): don't create the file
    if new != text:
        ini.parent.mkdir(parents=True, exist_ok=True)
        helix_opti._write(ini, new)
    return status(exe_folder, route, fsr_targets, ini_hint)
