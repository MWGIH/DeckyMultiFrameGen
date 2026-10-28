"""What OptiScaler and HelixSR can leave in a game's folder after their own removal missed it (an install the plugin no
longer recognises, a patch whose DLL had gone, an earlier HelixSR version): the game's own files that were kept aside
go back, and files that are clearly theirs go. Used when a game is set to a choice with neither of them."""

import shutil
from pathlib import Path

from . import optiscaler as opti

# HelixSR Scaler (an OptiScaler build) keeps the game's files it replaced here; HelixSR's drop-in keeps the game's DLL
# as <name>.original.dll
SCALER_BACKUP = "HelixSR-Scaler-backup"
SCALER_RECORDS = ("HelixSR-Scaler.files", "HelixSR-Scaler-remove.sh", "helixsr.ini")
HELIX_DIRS = ("HelixSR-fsrfg", "HelixSR")
OPTI_FILES = ("OptiScaler.ini", "OptiScaler.log", opti.MARKER_FILENAME, "fgmod-uninstaller.sh", "nvngx.ini",
              "fakenvapi.ini", "fakenvapi.log", "dlssg_to_fsr3.log")
OPTI_DIRS = ("D3D12_Optiscaler",)
PROXIES = (*opti.PROXY_DLL_BACKUPS, "d3d12.dll", "nvngx.dll", "OptiScaler.dll")


def _contains(path: Path, needle: bytes) -> bool:
    try:
        return needle in path.read_bytes()
    except OSError:
        return False


def sweep(directory: Path, fgmod: Path | None = None) -> list[str]:
    """Cleans directory (a game's .exe folder); returns what changed, as file names, for the log and the toast.
    fgmod: OptiScaler's install (~/fgmod), to recognise the support files it copies in."""
    d = Path(directory)
    if not d.is_dir():
        return []
    done = restore_helix_backups(d)

    # an OptiScaler build under a proxy name: Decky Framegen's or HelixSR Scaler's (never one the game shipped)
    for name in PROXIES:
        p = d / name
        if p.is_file() and _contains(p, b"OptiScaler"):
            p.unlink()
            done.append(f"{name} removed")

    # files OptiScaler copied in, where the game had none of its own (then there is a .b, restored below)
    if fgmod is not None:
        for name in dict.fromkeys([*opti.SUPPORT_FILES, opti.FSR4_UPSCALER_FILENAME, *opti.VARIANT_EXTRA_FILENAMES]):
            p = d / name
            if p.is_file() and not (d / f"{name}.b").exists() and opti.OptiScaler()._is_managed_support_file(p, fgmod):
                p.unlink()
                done.append(f"{name} removed")

    for name in dict.fromkeys([*opti.RESTORABLE_BACKUP_FILES, "nvapi64.dll"]):
        b = d / f"{name}.b"
        if b.is_file():
            b.replace(d / name)
            done.append(f"{name} restored")

    for name in (*OPTI_FILES, *SCALER_RECORDS):
        if (d / name).is_file():
            (d / name).unlink()
            done.append(f"{name} removed")
    for name in (*OPTI_DIRS, *HELIX_DIRS):
        if (d / name).is_dir():
            shutil.rmtree(d / name, ignore_errors=True)
            done.append(f"{name} removed")
    return done


def restore_helix_backups(directory: Path) -> list[str]:
    """The game's files HelixSR kept aside in directory put back, and the backups deleted: HelixSR Scaler's backup
    folder, the drop-in's <name>.original.dll and an earlier HelixSR's HelixSR/backup folder. Run after HelixSR's own
    removal too, in case it left any."""
    d = Path(directory)
    if not d.is_dir():
        return []
    done: list[str] = []
    for backup in (d / SCALER_BACKUP, d / "HelixSR" / "backup"):
        if backup.is_dir():
            for f in sorted(backup.rglob("*")):
                if f.is_file():
                    dst = d / f.relative_to(backup)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    f.replace(dst)
                    done.append(f"{dst.name} restored")
            shutil.rmtree(backup, ignore_errors=True)
    for original in sorted(d.glob("*.original.dll")):
        dst = d / (original.name[: -len(".original.dll")] + ".dll")
        original.replace(dst)
        done.append(f"{dst.name} restored")
    return done


def helix_backup_folders(game_folder: Path, exe_folder: Path | None = None) -> list[Path]:
    """The folders under a game where HelixSR's drop-in left a <name>.original.dll (it goes next to the game's FSR
    DLL, which isn't always next to the .exe), plus the .exe folder (HelixSR Scaler's backup)."""
    folders = [Path(exe_folder)] if exe_folder else []
    root = Path(game_folder)
    if root.is_dir():
        for original in root.rglob("amd_fidelityfx*.original.dll"):
            if original.parent not in folders:
                folders.append(original.parent)
    return folders
