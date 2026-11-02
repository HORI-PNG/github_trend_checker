from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "themes.json"
MAX_PROFILES = 3


@dataclass(frozen=True)
class Profile:
    """1 冊の PDF に対応する収集設定。"""

    name: str
    themes: list[str]
    language: str
    days: int
    themed_count: int
    general_count: int
    balanced: bool


def _int_in_range(raw: dict, key: str, default: int, lo: int, hi: int, where: str) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{where}: {key} は {lo}〜{hi} の整数で指定してください（現在: {value!r}）")
    return value


def _parse_profile(raw: dict, index: int) -> Profile:
    where = f"設定{index + 1}"
    name = raw.get("name") or where
    language = raw.get("language", "") or ""
    if not isinstance(name, str) or not isinstance(language, str):
        raise ValueError(f"{where}: name と language は文字列で指定してください")
    return Profile(
        name=name.strip(),
        themes=[t.strip() for t in raw.get("themes", []) if isinstance(t, str) and t.strip()],
        language=language.strip(),
        days=_int_in_range(raw, "days", 7, 1, 365, where),
        themed_count=_int_in_range(raw, "themed_count", 5, 0, 20, where),
        general_count=_int_in_range(raw, "general_count", 5, 0, 20, where),
        balanced=bool(raw.get("balanced", False)),
    )


def load_profiles(path: Path = DEFAULT_PATH) -> list[Profile]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    # 旧形式（設定 1 セットだけのフラットな JSON）も読めるようにする
    items = raw["profiles"] if "profiles" in raw else [raw]
    if not 1 <= len(items) <= MAX_PROFILES:
        raise ValueError(f"profiles は 1〜{MAX_PROFILES} 個で指定してください（現在: {len(items)} 個）")
    return [_parse_profile(item, i) for i, item in enumerate(items)]
