"""Import-safe paths for the installed MAKO Decky package."""

import os
from pathlib import Path


# This module must remain independent from shared_config: package import uses
# it to expose the plugin root before any generated/shared contract is loaded.
PLUGIN_ROOT = Path(__file__).parent.parent.parent

# Decky MultiFrameGen: the MAKO Renderer release assets are described by
# assets/mako/renderer.json and downloaded at runtime into Decky's runtime
# folder (the plugin folder isn't writable), instead of shipping in bin/.
RENDERER_MANIFEST = PLUGIN_ROOT / "assets" / "mako" / "renderer.json"
PAYLOAD_ROOT = Path(os.environ.get("DECKY_PLUGIN_RUNTIME_DIR") or PLUGIN_ROOT) / "mako"
