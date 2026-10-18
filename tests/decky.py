"""Stand-in for Decky's `decky` module, so main.py can be imported outside Decky.
Every path points into the throwaway folder tests/support.py creates."""
import logging
import os

_root = os.environ["MULTIFG_TEST_ROOT"]

DECKY_USER = "deck"
DECKY_USER_HOME = os.path.join(_root, "home")
HOME = DECKY_USER_HOME
DECKY_HOME = os.path.join(_root, "homebrew")
DECKY_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the repo: assets/ is real
DECKY_PLUGIN_SETTINGS_DIR = os.path.join(_root, "settings")
DECKY_PLUGIN_RUNTIME_DIR = os.path.join(_root, "runtime")
DECKY_PLUGIN_LOG_DIR = os.path.join(_root, "logs")
DECKY_PLUGIN_VERSION = "0.0.0-test"

logger = logging.getLogger("multifg-test")


async def emit(*args):
    pass
