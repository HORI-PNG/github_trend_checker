from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

TEMPLATES = Path(__file__).resolve().parent / "templates"


def render_pdf(meta: dict, entries: list[dict], path: Path) -> None:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["j2"]))
    html = env.get_template("report.html.j2").render(meta=meta, entries=entries)
    HTML(string=html).write_pdf(path)
