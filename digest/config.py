from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "themes.json"


@dataclass(frozen=True)
class Config:
    themes: list[str]
    language: str
    themed_count: int
    general_count: int
    days: int


def _int_in_range(raw: dict, key: str, default: int, lo: int, hi: int) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{key} は {lo}〜{hi} の整数で指定してください（現在: {value!r}）")
    return value


def load_config(path: Path = DEFAULT_PATH) -> Config:
    raw = json.loads(path.read_text(encoding="utf-8"))
    themes = [t.strip() for t in raw.get("themes", []) if isinstance(t, str) and t.strip()]
    language = raw.get("language", "") or ""
    if not isinstance(language, str):
        raise ValueError("language は文字列で指定してください")
    return Config(
        themes=themes,
        language=language.strip(),
        themed_count=_int_in_range(raw, "themed_count", 5, 0, 20),
        general_count=_int_in_range(raw, "general_count", 5, 0, 20),
        days=_int_in_range(raw, "days", 7, 1, 31),
    )
