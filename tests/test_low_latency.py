"""Low Latency Mode exports Proton-CachyOS DXVK/VKD3D pacing env for MAKO FG."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py_modules"))

from mako_plugin.config_schema_generated import get_script_generation_logic  # noqa: E402


class LowLatencyScriptTests(unittest.TestCase):
    def test_exports_dxvk_and_vkd3d_low_latency_when_enabled(self):
        lines = get_script_generation_logic()({"enable_low_latency": True})
        self.assertIn("export PROTON_DXVK_LOWLATENCY=1", lines)
        self.assertIn("export DXVK_FRAME_PACE=low-latency", lines)
        self.assertIn("export PROTON_VKD3D_LOWLATENCY=1", lines)

    def test_omits_exports_when_disabled(self):
        lines = get_script_generation_logic()({"enable_low_latency": False})
        self.assertNotIn("export PROTON_DXVK_LOWLATENCY=1", lines)
        self.assertNotIn("export DXVK_FRAME_PACE=low-latency", lines)
        self.assertNotIn("export PROTON_VKD3D_LOWLATENCY=1", lines)


if __name__ == "__main__":
    unittest.main()
