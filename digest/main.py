from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from digest.config import Config, load_config
from digest.github_client import GitHubClient, Repo
from digest.summarize import MODEL, fallback_summary, summarize

log = logging.getLogger("digest")

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent


def select_repos(gh: GitHubClient, cfg: Config, since: str, balanced: bool = False) -> list[Repo]:
    lang = f" language:{cfg.language}" if cfg.language else ""

    themed: dict[str, Repo] = {}
    ranked_names: list[list[str]] = []  # テーマごとのスター順のリポジトリ名
    for theme in cfg.themes:
        query = f"{theme} in:name,description,topics created:>={since}{lang}"
        names = []
        for item in gh.search_repos(query):
            repo = themed.setdefault(item["full_name"], Repo.from_api(item, "theme"))
            repo.matched_themes.append(theme)
            names.append(item["full_name"])
        ranked_names.append(names)

    if balanced:
        # 各テーマの上位から1件ずつ順番に取り、特定のテーマに偏らないようにする
        picked: dict[str, Repo] = {}
        for rank in range(max(map(len, ranked_names), default=0)):
            for names in ranked_names:
                if len(picked) < cfg.themed_count and rank < len(names):
                    picked.setdefault(names[rank], themed[names[rank]])
        candidates = list(picked.values())
    else:
        candidates = list(themed.values())
    themed_top = sorted(candidates, key=lambda r: r.stars, reverse=True)[: cfg.themed_count]

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
        f"# {meta['title']}（{meta['date']}）",
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
    # 既定はローカル用の tmp/reports（git 管理外）。Actions では --out reports を指定する
    parser.add_argument("--out", type=Path, default=ROOT / "tmp" / "reports", help="出力先ディレクトリ")
    parser.add_argument("--workers", type=int, default=3, help="Claude API の並列数")
    # 特別実行用: 設定ファイルの値をこの実行だけ上書きする
    parser.add_argument("--days", type=int, help="対象期間（日）を上書き（1〜3650）")
    parser.add_argument("--themed-count", type=int, help="テーマありの件数を上書き（0〜30）")
    parser.add_argument("--general-count", type=int, help="テーマなしの件数を上書き（0〜30）")
    parser.add_argument("--label", help="出力フォルダ名の末尾に付ける名前（例: special）")
    parser.add_argument("--themes", help="テーマをカンマ区切りで上書き（例: RAG,GraphRAG）")
    parser.add_argument("--balanced", action="store_true", help="テーマごとに均等に選ぶ（スター順で1テーマに偏らせない）")
    args = parser.parse_args(argv)
    for name, lo, hi in (("days", 1, 3650), ("themed_count", 0, 30), ("general_count", 0, 30)):
        value = getattr(args, name)
        if value is not None and not lo <= value <= hi:
            parser.error(f"--{name.replace('_', '-')} は {lo}〜{hi} で指定してください")
    if args.label and not all(c.isascii() and (c.isalnum() or c in "-_") for c in args.label):
        parser.error("--label は英数字・ハイフン・アンダースコアのみ使えます")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("weasyprint", "fontTools", "httpx", "httpx2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    cfg = load_config()
    overrides = {
        k: v
        for k, v in (("days", args.days), ("themed_count", args.themed_count), ("general_count", args.general_count))
        if v is not None
    }
    if args.themes:
        overrides["themes"] = [t.strip() for t in args.themes.split(",") if t.strip()]
    if overrides:
        cfg = replace(cfg, **overrides)
        log.info("この実行だけ設定を上書きします: %s", overrides)
    now = datetime.now(JST)
    since = (now - timedelta(days=cfg.days)).strftime("%Y-%m-%d")
    log.info("対象期間: %s 以降 / テーマ: %s", since, cfg.themes)

    gh = GitHubClient()
    repos = select_repos(gh, cfg, since, balanced=args.balanced)
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
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(lambda r: summarize(client, r), repos))
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            log.error("Claude API の認証に失敗しました。ANTHROPIC_API_KEY を確認してください: %s", e)
            return 1
        failed = sum(s is None for s in results)
        if repos and failed == len(repos):
            log.error("全件の解説生成に失敗したため、レポートを出力しません")
            return 1
        summaries = [
            s if s is not None else fallback_summary(r, "自動解説の生成に失敗したため、説明文のみ掲載しています。")
            for r, s in zip(repos, results)
        ]

    meta = {
        "title": "GitHub 週間スター上位レポート" if cfg.days == 7 else f"GitHub スター上位レポート（過去 {cfg.days} 日）",
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

    out_dir = args.out / (f"{meta['date']}_{args.label}" if args.label else meta["date"])
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
