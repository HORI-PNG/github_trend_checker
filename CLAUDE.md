# github_trend_checker

GitHub で「直近1週間に作成されたリポジトリ」をスター数順に集め、Claude API で日本語の解説を付けて PDF / PPTX にまとめる週次レポートツール。

## 全体像

- **収集・要約・出力**: `digest/`（Python パッケージ。`python -m digest` で実行）
  - `config.py` … `config/themes.json` の読み込みと検証
  - `github_client.py` … GitHub REST API（検索・README・ファイルツリー・マニフェスト取得）
  - `summarize.py` … Claude API（`claude-opus-5-5`、構造化出力）で解説 JSON を生成
  - `render_pdf.py` / `templates/report.html.j2` … WeasyPrint で PDF 化
  - `render_pptx.py` … python-pptx でスライド化
  - `main.py` … 全体の流れ（選定 → 情報収集 → 要約 → 出力）
- **設定**: `config/themes.json`（テーマのキーワード・言語・件数）。管理画面から編集される
- **管理画面**: `docs/index.html`（GitHub Pages、静的 HTML + 素の JS）。GitHub API で `config/themes.json` を読み書きし、`reports/` の一覧を表示する
- **定期実行**: `.github/workflows/weekly-digest.yml`（毎週月曜 10:00 JST = `0 1 * * 1` UTC）。生成物を `reports/YYYY-MM-DD/` にコミットする
- **出力**: `reports/YYYY-MM-DD/` に `report.pdf` `report.pptx` `report.md` `data.json`

## 選定ルール

- 対象期間: 実行日（JST）から `days` 日前以降に作成されたリポジトリ（`created:>=`）
- テーマあり: キーワードごとに検索 → 重複除去 → スター順で上位 `themed_count` 件
- テーマなし: 期間内の全リポジトリをスター順 → テーマありと重複しないものから上位 `general_count` 件

## コマンド

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
GITHUB_TOKEN=$(gh auth token) python -m digest --dry-run --limit 2   # Claude を呼ばずに出力まで確認
GITHUB_TOKEN=$(gh auth token) ANTHROPIC_API_KEY=... python -m digest # 本番と同じ処理
```

- `--dry-run` は Claude API を呼ばず、リポジトリの説明文でダミーの解説を作る（費用ゼロで PDF/PPTX の見た目を確認できる）
- 出力先は `--out` で変更可能。ローカル確認時は `--out tmp/` を使い、`reports/` を汚さない

## 環境

- 開発は WSL (Ubuntu) 上。Windows 側の PowerShell からは `wsl -d ubuntu -- bash -lc '...'` で実行する
- PDF には日本語フォント `Noto Sans CJK JP`（`fonts-noto-cjk`）と pango が必要
- シークレット: `ANTHROPIC_API_KEY`（リポジトリの Actions Secrets）。`GITHUB_TOKEN` は Actions が自動付与
- リポジトリは公開（GitHub Pages を無料プランで使うため）。シークレットやトークンをコミットしないこと
