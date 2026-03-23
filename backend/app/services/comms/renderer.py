"""
Template Renderer — Jinja2-based message builder.
Loads templates from municipalities/{city_id}/templates/ with _default fallback.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

logger = logging.getLogger(__name__)

_MUNICIPALITIES_ROOT = Path(__file__).parents[4] / "municipalities"


class TemplateRenderer:

    def __init__(self, municipalities_root: Path = _MUNICIPALITIES_ROOT) -> None:
        self._root = municipalities_root
        self._envs: dict[str, Environment] = {}

    def _get_env(self, city_id: str) -> Environment:
        if city_id not in self._envs:
            # City templates take precedence, fall back to _default
            search_paths = [
                str(self._root / city_id / "templates"),
                str(self._root / "_default" / "templates"),
            ]
            loader = FileSystemLoader(search_paths)
            self._envs[city_id] = Environment(
                loader=loader,
                autoescape=select_autoescape([]),  # plain text / markdown
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._envs[city_id]

    def render(self, city_id: str, template_name: str, context: dict[str, Any]) -> str:
        env = self._get_env(city_id)
        filename = f"{template_name}.md"
        try:
            tmpl = env.get_template(filename)
            return tmpl.render(**context).strip()
        except TemplateNotFound:
            logger.warning("Template not found: %s (city=%s)", filename, city_id)
            return f"[{template_name}]"
        except Exception as exc:
            logger.error("Template render error: %s — %s", filename, exc)
            return f"[render error: {exc}]"


# Module singleton
renderer = TemplateRenderer()
