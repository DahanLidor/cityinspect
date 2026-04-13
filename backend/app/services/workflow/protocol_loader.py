"""
Protocol Loader — loads YAML protocol definitions.
Merges _default with city-specific overrides.
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

def _find_municipalities_root() -> Path:
    # Try /municipalities (Docker bind), then relative to project root, then inside backend/
    candidates = [
        Path("/municipalities"),
        Path(__file__).parents[4] / "municipalities",
        Path(__file__).parents[3] / "municipalities",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # fallback

_MUNICIPALITIES_ROOT = _find_municipalities_root()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class ProtocolLoader:
    """
    Loads protocol YAML files. City-specific protocol overrides _default.
    Results are cached per (city_id, defect_type).
    """

    def __init__(self, municipalities_root: Path = _MUNICIPALITIES_ROOT) -> None:
        self._root = municipalities_root
        self._cache: dict[tuple[str, str], dict] = {}

    def load(self, city_id: str, defect_type: str) -> dict[str, Any]:
        cache_key = (city_id, defect_type)
        if cache_key in self._cache:
            return self._cache[cache_key]

        default_path = self._root / "_default" / "protocols" / f"{defect_type}.yaml"
        city_path = self._root / city_id / "protocols" / f"{defect_type}.yaml"

        default_data = _load_yaml(default_path)
        city_data = _load_yaml(city_path)

        if not default_data and not city_data:
            logger.warning("No protocol found for defect_type=%s city=%s", defect_type, city_id)
            return {}

        merged = _deep_merge(default_data, city_data)
        protocol = merged.get("protocol", merged)

        self._cache[cache_key] = protocol
        return protocol

    def get_step(self, city_id: str, defect_type: str, step_id: str) -> dict[str, Any] | None:
        protocol = self.load(city_id, defect_type)
        for step in protocol.get("steps", []):
            if step["id"] == step_id:
                return step
        return None

    def get_first_step(self, city_id: str, defect_type: str) -> dict[str, Any] | None:
        protocol = self.load(city_id, defect_type)
        steps = protocol.get("steps", [])
        return steps[0] if steps else None

    def get_next_step(self, city_id: str, defect_type: str, current_step_id: str) -> dict[str, Any] | None:
        protocol = self.load(city_id, defect_type)
        steps = protocol.get("steps", [])
        for i, step in enumerate(steps):
            if step["id"] == current_step_id and i + 1 < len(steps):
                return steps[i + 1]
        return None

    def load_city_config(self, city_id: str) -> dict[str, Any]:
        default = _load_yaml(self._root / "_default" / "config.yaml")
        city = _load_yaml(self._root / city_id / "config.yaml")
        return _deep_merge(default, city)

    def load_contacts(self, city_id: str) -> dict[str, Any]:
        default = _load_yaml(self._root / "_default" / "contacts.yaml")
        city = _load_yaml(self._root / city_id / "contacts.yaml")
        return _deep_merge(default, city)

    def clear_cache(self) -> None:
        self._cache.clear()


# Module singleton
protocol_loader = ProtocolLoader()
