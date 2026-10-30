from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from digest.config import Config, load_config
from digest.github_client import GitHubClient, Repo
from digest.summarize import MODEL, fallback_summary, summarize

log = logging.getLogger("digest")

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent


def select_repos(gh: GitHubClient, cfg: Config, since: str) -> list[Repo]:
    lang = f" language:{cfg.language}" if cfg.language else ""

    themed: dict[str, Repo] = {}
    for theme in cfg.themes:
        query = f"{theme} in:name,description,topics created:>={since}{lang}"
        for item in gh.search_repos(query):
            repo = themed.setdefault(item["full_name"], Repo.from_api(item, "theme"))
            repo.matched_themes.append(theme)
    themed_top = sorted(themed.values(), key=lambda r: r.stars, reverse=True)[: cfg.themed_count]

    taken = {r.full_name for r in themed_top}
    general_top: list[Repo] = []
    for item in gh.search_repos(f"created:>={since}", per_page=50):
        if len(general_top) >= cfg.general_count:
            break
        if item["full_name"] not in taken:
            general_top.append(Repo.from_api(item, "general"))

    return themed_top + general_top


def to_markdown(meta: dict, entries: list[dict]) -> str:
    lines = [
        f"# GitHub 週間スター上位レポート（{meta['date']}）",
        "",
        f"- 対象: {meta['since']} 以降に作成されたリポジトリ",
        f"- テーマ: {', '.join(meta['themes']) or '（なし）'}",
        "",
    ]
    for i, e in enumerate(entries, 1):
        r, s = e["repo"], e["summary"]
        label = "テーマ" if r["category"] == "theme" else "総合"
        lines += [
            f"## {i}. [{r['full_name']}]({r['html_url']})（{label} / ★{r['stars']:,}）",
            "",
            f"**{s['one_liner']}**",
            "",
            s["summary"],
            "",
            *[f"- {p}" for p in s["key_points"]],
            "",
        ]
        for d in s["details"]:
            lines += [f"### {d['heading']}", "", d["body"], ""]
        lines += [
            f"- 技術構成: {', '.join(s['tech_stack']) or '不明'}",
            f"- 向いている人: {s['target_users']}",
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub 週間スター上位レポートを作成する")
    parser.add_argument("--dry-run", action="store_true", help="Claude API を呼ばずに出力まで行う")
    parser.add_argument("--limit", type=int, help="処理するリポジトリ数の上限（動作確認用）")
    parser.add_argument("--out", type=Path, default=ROOT / "reports", help="出力先ディレクトリ")
    parser.add_argument("--workers", type=int, default=3, help="Claude API の並列数")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("weasyprint", "fontTools", "httpx", "httpx2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    cfg = load_config()
    now = datetime.now(JST)
    since = (now - timedelta(days=cfg.days)).strftime("%Y-%m-%d")
    log.info("対象期間: %s 以降 / テーマ: %s", since, cfg.themes)

    gh = GitHubClient()
    repos = select_repos(gh, cfg, since)
    if args.limit:
        repos = repos[: args.limit]
    log.info("選定: %s", [r.full_name for r in repos])

    for repo in repos:
        gh.enrich(repo)

    if args.dry_run:
        summaries = [fallback_summary(r, "dry-run のため Claude API は呼んでいません。") for r in repos]
    else:
        import anthropic

        client = anthropic.Anthropic()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            summaries = list(pool.map(lambda r: summarize(client, r), repos))

    meta = {
        "date": now.strftime("%Y-%m-%d"),
        "since": since,
        "themes": cfg.themes,
        "language": cfg.language,
        "model": "dry-run" if args.dry_run else MODEL,
        "generated_at": now.isoformat(timespec="seconds"),
    }
    entries = []
    for repo, summary in zip(repos, summaries):
        data = asdict(repo)
        # 生データは容量が大きいので保存しない
        for key in ("readme", "tree", "manifests"):
            data.pop(key)
        entries.append({"repo": data, "summary": summary})

    out_dir = args.out / meta["date"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data.json").write_text(
        json.dumps({"meta": meta, "entries": entries}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(to_markdown(meta, entries), encoding="utf-8")

    from digest.render_pdf import render_pdf
    from digest.render_pptx import render_pptx

    render_pdf(meta, entries, out_dir / "report.pdf")
    render_pptx(meta, entries, out_dir / "report.pptx")
    log.info("出力しました: %s", out_dir)
    return 0
