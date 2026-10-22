"""Compiler-reflected shader controls; persistence remains in profile_storage."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import struct
from typing import Literal, NotRequired, TypedDict


class ShaderParameterPresentation(TypedDict):
    widget: Literal["", "input", "drag", "slider", "combo", "radio", "list", "color", "button"]
    group: str
    label: str
    component: int
    count: int


class ShaderParameter(TypedDict):
    key: str
    label: str
    description: str
    category: str
    type: Literal["bool", "int", "uint", "float"]
    default: float
    value: float
    min: float | None
    max: float | None
    step: float | None
    items: list[str]
    presentation: NotRequired[ShaderParameterPresentation]
    resettable: NotRequired[bool]


class ShaderEffectParameters(TypedDict):
    id: str
    name: str
    path: str
    parameters: list[ShaderParameter]
    error: str | None


PARAMETER_KEY = re.compile(r"makoShader_(?:[0-9a-f]{2})+_(?:[0-9a-f]{2})+_(?:0|[1-9][0-9]*)")


def discover(tool: Path, config: Path) -> list[ShaderEffectParameters]:
    if not tool.is_file():
        raise ValueError("Install the updated MAKO Renderer to customize shader parameters.")
    # Decky's PyInstaller runtime prepends its private libraries. The external
    # native helper needs the pre-bundle search path (or the host defaults).
    # Modify only the child environment; other plugin threads still need Decky's.
    environment = os.environ.copy()
    original_library_path = environment.pop("LD_LIBRARY_PATH_ORIG", None)
    if original_library_path:
        environment["LD_LIBRARY_PATH"] = original_library_path
    else:
        environment.pop("LD_LIBRARY_PATH", None)
    environment.update(VKBASALT_LOG_LEVEL="none", VKBASALT_LOG_FILE="stderr")
    result = subprocess.run([str(tool), str(config)], capture_output=True, text=True,
                            timeout=30, check=False, env=environment)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Unable to read shader parameters")
    if len(result.stdout) > 4 * 1024 * 1024:
        raise ValueError("Shader parameter metadata is too large")
    return normalize_metadata(json.loads(result.stdout))


def float32(value: float) -> float:
    try:
        result = struct.unpack("f", struct.pack("f", value))[0]
    except (OverflowError, struct.error):
        raise ValueError("Shader value is outside its numeric type") from None
    if not math.isfinite(result):
        raise ValueError("Shader value is outside its numeric type")
    return result


def normalize_metadata(data: object) -> list[ShaderEffectParameters]:
    if (not isinstance(data, dict) or type(data.get("schema")) is not int
            or data.get("schema") != 1 or not isinstance(data.get("effects"), list)):
        raise ValueError("Unsupported shader parameter metadata")
    effects: list[ShaderEffectParameters] = []
    effect_ids: set[str] = set()
    parameter_keys: set[str] = set()
    for effect in data["effects"]:
        if not isinstance(effect, dict) or not all(isinstance(effect.get(k), str) for k in ("id", "name", "path")):
            raise ValueError("Invalid shader metadata")
        if not effect["id"] or effect["id"] in effect_ids or not isinstance(effect.get("parameters"), list):
            raise ValueError("Ambiguous shader metadata")
        effect_ids.add(effect["id"])
        prefix = "makoShader_" + effect["id"].encode("utf-8").hex() + "_"
        parameters: list[ShaderParameter] = []
        for p in effect["parameters"]:
            if not isinstance(p, dict) or not all(isinstance(p.get(k), str) for k in ("key", "label", "description", "category", "type")):
                raise ValueError("Invalid shader parameter")
            if (not PARAMETER_KEY.fullmatch(p["key"]) or not p["key"].startswith(prefix)
                    or p["key"] in parameter_keys or p["type"] not in ("bool", "int", "uint", "float")):
                raise ValueError("Invalid shader parameter key or type")
            parameter_keys.add(p["key"])
            for key in ("default", "value", "min", "max", "step"):
                value = p.get(key)
                if value is None and key in ("min", "max", "step"):
                    continue
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("Invalid shader parameter value")
            if not isinstance(p.get("items"), list) or any(not isinstance(item, str) for item in p["items"]):
                raise ValueError("Invalid shader choices")
            for key in ("default", "value"):
                value = p[key]
                if ((p["type"] == "bool" and value not in (0, 1)) or
                        (p["type"] == "int" and (value != int(value) or not -2147483648 <= value <= 2147483647)) or
                        (p["type"] == "uint" and (value != int(value) or not 0 <= value <= 4294967295))):
                    raise ValueError("Invalid shader parameter value for its type")
                if p["type"] == "float":
                    float32(value)
            parameter = ShaderParameter(**{key: p.get(key) for key in ShaderParameter.__required_keys__})
            parameter["items"] = list(p["items"])
            if p["items"] and p["type"] not in ("int", "uint"):
                raise ValueError("Invalid shader choices for this type")
            if "resettable" in p:
                if type(p["resettable"]) is not bool:
                    raise ValueError("Invalid shader reset policy")
                parameter["resettable"] = p["resettable"]
            # Additive metadata: old helpers remain usable. Invalid hints cannot
            # turn a numeric value into a misleading specialized control.
            hint = p.get("presentation")
            if p["type"] == "bool" and isinstance(hint, dict) and hint.get("widget") == "button":
                continue
            if (isinstance(hint, dict)
                    and hint.get("widget") in ("", "input", "drag", "slider", "combo", "radio", "list", "color", "button")
                    and isinstance(hint.get("group"), str) and PARAMETER_KEY.fullmatch(hint["group"])
                    and isinstance(hint.get("label"), str)
                    and type(hint.get("count")) in (int, float) and hint["count"] in (1, 2, 3, 4)
                    and type(hint.get("component")) in (int, float) and hint["component"] in range(int(hint["count"]))):
                parameter["presentation"] = ShaderParameterPresentation(
                    widget=hint["widget"], group=hint["group"], label=hint["label"],
                    component=int(hint["component"]), count=int(hint["count"]))
            parameters.append(parameter)
        error = effect.get("error")
        if error is not None and not isinstance(error, str):
            raise ValueError("Invalid shader error")
        effects.append(ShaderEffectParameters(id=effect["id"], name=effect["name"], path=effect["path"], parameters=parameters, error=error))
    return effects


def validate_changes(effects: list[ShaderEffectParameters], changes: dict[str, float | None]) -> dict[str, str]:
    if not isinstance(changes, dict) or not changes or len(changes) > 1024:
        raise ValueError("Invalid shader parameter update")
    allowed = {p["key"]: p for effect in effects for p in effect["parameters"]}
    result: dict[str, str] = {}
    for key, value in changes.items():
        if key not in allowed:
            raise ValueError("Shader parameters changed; reopen the editor")
        p = allowed[key]
        resetting = value is None
        if resetting:
            if p.get("resettable") is False:
                raise ValueError("This shader parameter does not allow reset")
            value = p["default"]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Shader values must be finite numbers")
        if p["type"] != "float" and value != int(value):
            raise ValueError("This shader parameter requires a whole number")
        if p["type"] == "bool" and value not in (0, 1):
            raise ValueError("Invalid shader toggle")
        comparison = float32(value) if p["type"] == "float" else value
        lower = 0 if p["type"] == "uint" else -2147483648 if p["type"] == "int" else -math.inf
        upper = 4294967295 if p["type"] == "uint" else 2147483647 if p["type"] == "int" else math.inf
        if not resetting:
            declared_min = p["min"]
            declared_max = p["max"]
            if p["type"] == "float":
                declared_min = float32(declared_min) if declared_min is not None else None
                declared_max = float32(declared_max) if declared_max is not None else None
            lower = max(lower, declared_min) if declared_min is not None else lower
            upper = min(upper, declared_max) if declared_max is not None else upper
        if not lower <= comparison <= upper:
            raise ValueError("Shader value is outside its declared range")
        if not resetting and p["items"] and not 0 <= value < len(p["items"]):
            raise ValueError("Invalid shader choice")
        result[key] = "default" if resetting else str(int(value)) if p["type"] != "float" else format(value, ".9g")
    return result
