from jinja2 import Environment, FileSystemLoader, select_autoescape
from . import config

AVAILABLE_TEMPLATES = {
    "classic": {"file": "classic.html.j2", "label": "Classic — Hero + 변형 5종"},
    "magazine": {"file": "magazine.html.j2", "label": "Magazine — 와이드 + 2x2 그리드"},
    "minimal":  {"file": "minimal.html.j2", "label": "Minimal — 균일 리스트형"},
}

_env = Environment(
    loader=FileSystemLoader(config.TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render(template_key: str, data: dict) -> str:
    if template_key not in AVAILABLE_TEMPLATES:
        raise ValueError(f"Unknown template: {template_key}")
    tpl = _env.get_template(AVAILABLE_TEMPLATES[template_key]["file"])
    return tpl.render(**data)
