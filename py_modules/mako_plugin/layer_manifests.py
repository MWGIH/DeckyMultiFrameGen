"""Resolve native layer selection for installation and development deployment."""

import json
from pathlib import Path

from .constants import ACTIVE_RENDERER_OWNER_DECKY, ACTIVE_RENDERER_OWNER_STANDALONE


def manifest_library(manifest_path: Path, identity: str | None = None) -> Path:
    """Resolve an explicit library path relative to its Vulkan manifest."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    layer = manifest.get("layer") if isinstance(manifest, dict) else None
    if not isinstance(layer, dict):
        raise ValueError(f"Invalid layer manifest: {manifest_path}")
    if identity is not None and layer.get("name") != identity:
        raise ValueError(f"Unexpected layer identity in {manifest_path}")
    library = layer.get("library_path")
    if not isinstance(library, str) or not library:
        raise ValueError(f"Missing library path in {manifest_path}")
    path = Path(library)
    return (path if path.is_absolute() else manifest_path.parent / path).resolve()


def manifest_owner(manifest_path: Path, decky_library: Path,
                   standalone_library: Path) -> str | None:
    """Identify only the two managed native library locations."""
    try:
        selected = manifest_library(manifest_path)
        if selected == decky_library.resolve():
            return ACTIVE_RENDERER_OWNER_DECKY
        if selected == standalone_library.resolve():
            return ACTIVE_RENDERER_OWNER_STANDALONE
    except (OSError, ValueError, TypeError):
        pass
    return None
