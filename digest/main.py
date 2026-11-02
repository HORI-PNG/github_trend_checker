from __future__ import annotations

import argparse
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from digest.config import Profile, load_profiles
from digest.github_client import GitHubClient, Repo
from digest.summarize import MODEL, fallback_summary, summarize

log = logging.getLogger("digest")

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent


def select_repos(gh: GitHubClient, profile: Profile, since: str) -> list[Repo]:
    lang = f" language:{profile.language}" if profile.language else ""

    themed: dict[str, Repo] = {}
    ranked_names: list[list[str]] = []  # テーマごとのスター順のリポジトリ名
    for theme in profile.themes:
        query = f"{theme} in:name,description,topics created:>={since}{lang}"
        names = []
        for item in gh.search_repos(query):
            repo = themed.setdefault(item["full_name"], Repo.from_api(item, "theme"))
            repo.matched_themes.append(theme)
            names.append(item["full_name"])
        ranked_names.append(names)

    if profile.balanced:
        # 各テーマの上位から1件ずつ順番に取り、特定のテーマに偏らないようにする
        picked: dict[str, Repo] = {}
        for rank in range(max(map(len, ranked_names), default=0)):
            for names in ranked_names:
                if len(picked) < profile.themed_count and rank < len(names):
                    picked.setdefault(names[rank], themed[names[rank]])
        candidates = list(picked.values())
    else:
        candidates = list(themed.values())
    themed_top = sorted(candidates, key=lambda r: r.stars, reverse=True)[: profile.themed_count]

    taken = {r.full_name for r in themed_top}
    general_top: list[Repo] = []
    if profile.general_count:
        for item in gh.search_repos(f"created:>={since}", per_page=50):
            if len(general_top) >= profile.general_count:
                break
            if item["full_name"] not in taken:
                general_top.append(Repo.from_api(item, "general"))

    return themed_top + general_top


def prune_old_reports(reports_dir: Path, keep_days: int, today: date) -> None:
    """フォルダ名先頭の日付（YYYY-MM-DD）が keep_days 日より古いレポートを削除する。"""
    cutoff = today - timedelta(days=keep_days - 1)
    for path in sorted(reports_dir.iterdir()):
        if not path.is_dir():
            continue
        try:
            folder_date = date.fromisoformat(path.name[:10])
        except ValueError:
            continue
        if folder_date < cutoff:
            shutil.rmtree(path)
            log.info("古いレポートを削除しました: %s", path.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub スター上位レポートを作成する")
    parser.add_argument("--dry-run", action="store_true", help="Claude API を呼ばずに出力まで行う")
    parser.add_argument("--limit", type=int, help="設定ごとに処理するリポジトリ数の上限（動作確認用）")
    # 既定はローカル用の tmp/reports（git 管理外）。Actions では --out reports を指定する
    parser.add_argument("--out", type=Path, default=ROOT / "tmp" / "reports", help="出力先ディレクトリ")
    parser.add_argument("--workers", type=int, default=3, help="Claude API の並列数")
    parser.add_argument("--prune-days", type=int, help="この日数より古いレポートフォルダを削除する（例: 14）")
    # 特別実行用: 設定1をベースに、この実行だけ値を上書きして 1 冊だけ作る
    parser.add_argument("--days", type=int, help="対象期間（日）を上書き（1〜3650）")
    parser.add_argument("--themed-count", type=int, help="テーマありの件数を上書き（0〜30）")
    parser.add_argument("--general-count", type=int, help="テーマなしの件数を上書き（0〜30）")
    parser.add_argument("--label", help="出力フォルダ名の末尾に付ける名前（例: special）")
    parser.add_argument("--themes", help="テーマをカンマ区切りで上書き（例: RAG,GraphRAG）")
    parser.add_argument("--balanced", action="store_true", help="テーマごとに均等に選ぶ（スター順で1テーマに偏らせない）")
    args = parser.parse_args(argv)
    for name, lo, hi in (("days", 1, 3650), ("themed_count", 0, 30), ("general_count", 0, 30), ("prune_days", 1, 3650)):
        value = getattr(args, name)
        if value is not None and not lo <= value <= hi:
            parser.error(f"--{name.replace('_', '-')} は {lo}〜{hi} で指定してください")
    if args.label and not all(c.isascii() and (c.isalnum() or c in "-_") for c in args.label):
        parser.error("--label は英数字・ハイフン・アンダースコアのみ使えます")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("weasyprint", "fontTools", "httpx", "httpx2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    profiles = load_profiles()
    overrides: dict = {
        k: v
        for k, v in (("days", args.days), ("themed_count", args.themed_count), ("general_count", args.general_count))
        if v is not None
    }
    if args.themes:
        overrides["themes"] = [t.strip() for t in args.themes.split(",") if t.strip()]
        overrides["name"] = "特別実行"
    if args.balanced:
        overrides["balanced"] = True
    if overrides:
        profiles = [replace(profiles[0], **overrides)]
        log.info("この実行だけ設定を上書きします（1 冊のみ作成）: %s", overrides)

    now = datetime.now(JST)
    gh = GitHubClient()

    # 設定ごとに選定する
    selections: list[tuple[Profile, str, list[Repo]]] = []
    for profile in profiles:
        since = (now - timedelta(days=profile.days)).strftime("%Y-%m-%d")
        repos = select_repos(gh, profile, since)
        if args.limit:
            repos = repos[: args.limit]
        log.info("[%s] %s 以降 / テーマ %s / 選定: %s", profile.name, since, profile.themes, [r.full_name for r in repos])
        selections.append((profile, since, repos))

    # 複数の設定に同じリポジトリが入っても、情報収集と要約は 1 回だけにする
    unique: dict[str, Repo] = {}
    for _, _, repos in selections:
        for repo in repos:
            unique.setdefault(repo.full_name, repo)
    for repo in unique.values():
        gh.enrich(repo)

    if args.dry_run:
        summaries = {n: fallback_summary(r, "dry-run のため Claude API は呼んでいません。") for n, r in unique.items()}
    else:
        import anthropic

        client = anthropic.Anthropic()
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = dict(zip(unique, pool.map(lambda r: summarize(client, r), unique.values())))
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            log.error("Claude API の認証に失敗しました。ANTHROPIC_API_KEY を確認してください: %s", e)
            return 1
        if unique and all(s is None for s in results.values()):
            log.error("全件の解説生成に失敗したため、レポートを出力しません")
            return 1
        summaries = {
            n: s if s is not None else fallback_summary(unique[n], "自動解説の生成に失敗したため、説明文のみ掲載しています。")
            for n, s in results.items()
        }

    folder = f"{now:%Y-%m-%d}_{args.label}" if args.label else f"{now:%Y-%m-%d}"
    out_dir = args.out / folder
    out_dir.mkdir(parents=True, exist_ok=True)

    from digest.render_pdf import render_pdf

    for i, (profile, since, repos) in enumerate(selections, 1):
        meta = {
            "title": profile.name,
            "date": f"{now:%Y-%m-%d}",
            "days": profile.days,
            "since": since,
            "themes": profile.themes,
            "language": profile.language,
            "model": "dry-run" if args.dry_run else MODEL,
        }
        entries = []
        for repo in repos:
            data = asdict(repo)
            # 生データは容量が大きいので渡さない
            for key in ("readme", "tree", "manifests"):
                data.pop(key)
            entries.append({"repo": data, "summary": summaries[repo.full_name]})
        render_pdf(meta, entries, out_dir / f"report_{i}.pdf")
    log.info("出力しました: %s（%d 冊）", out_dir, len(selections))

    if args.prune_days:
        prune_old_reports(args.out, args.prune_days, now.date())
    return 0
