"""Sets up a throwaway home folder and import paths before main.py is imported."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="multifg-test-"))
os.environ["MULTIFG_TEST_ROOT"] = str(ROOT)
os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(ROOT / "runtime")  # Decky sets these for the plugin's process
os.environ["DECKY_USER_HOME"] = str(ROOT / "home")
os.environ["DECKY_HOME"] = str(ROOT / "homebrew")
HOME = ROOT / "home"

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(Path(__file__).resolve().parent), str(REPO / "py_modules"), str(REPO)]


def reset_home() -> Path:
    shutil.rmtree(ROOT, ignore_errors=True)
    HOME.mkdir(parents=True)
    return HOME


def add_game(library: Path, appid: str, name: str, installdir: str, create_dir: bool = True, state_flags: str = "4") -> None:
    steamapps = library / "steamapps"
    steamapps.mkdir(parents=True, exist_ok=True)
    (steamapps / f"appmanifest_{appid}.acf").write_text(
        f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"installdir"\t\t"{installdir}"\n\t"StateFlags"\t\t"{state_flags}"\n}}\n'
    )
    if create_dir:
        (steamapps / "common" / installdir).mkdir(parents=True, exist_ok=True)


def add_library_folder(steam_root: Path, extra: Path) -> None:
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    vdf.parent.mkdir(parents=True, exist_ok=True)
    vdf.write_text(f'"libraryfolders"\n{{\n\t"1"\n\t{{\n\t\t"path"\t\t"{extra}"\n\t}}\n}}\n')
