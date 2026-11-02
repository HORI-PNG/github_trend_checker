# github_trend_checker

GitHub で「直近 N 日に作成されたリポジトリ」をスター数順に集め、Claude API で日本語の解説を付けて PDF にまとめる週次レポートツール。収集設定は最大 3 セットで、設定ごとに 1 冊の PDF を作る。

## 全体像

- **収集・要約・出力**: `digest/`（Python パッケージ。`python -m digest` で実行）
  - `config.py` … `config/themes.json` の読み込みと検証（`Profile` = 1 冊分の設定）
  - `github_client.py` … GitHub REST API（検索・README・ファイルツリー・マニフェスト取得）
  - `summarize.py` … Claude API（`claude-opus-5-5`、構造化出力）で解説 JSON を生成
  - `render_pdf.py` / `templates/report.html.j2` … WeasyPrint で PDF 化
  - `main.py` … 全体の流れ（設定ごとに選定 → 重複を除いて情報収集・要約 → 設定ごとに PDF → 古いフォルダ削除）
- **設定**: `config/themes.json` の `profiles`（1〜3 個）。各要素は `name` `themes` `language` `days` `themed_count` `general_count` `balanced`。管理画面から編集される
- **管理画面**: `docs/index.html`（GitHub Pages、静的 HTML + 素の JS）。GitHub API で `config/themes.json` を読み書きし、`reports/` の一覧を表示する
- **定期実行**: `.github/workflows/weekly-digest.yml`（毎週月曜 8:50 JST = `50 23 * * 0` UTC。毎時 0 分は取りこぼしが起きやすいので避ける）。生成物を `reports/YYYY-MM-DD/` にコミットし、`--prune-days 14` で 2 週間より古いフォルダを削除する
- **出力**: `reports/YYYY-MM-DD/report_1.pdf` 〜 `report_3.pdf`（設定の順番と対応）。PDF 以外は出力しない

## 選定ルール（設定ごと）

- 対象期間: 実行日（JST）から `days` 日前以降に作成されたリポジトリ（`created:>=`）
- テーマあり: キーワードごとに検索 → 重複除去 → スター順で上位 `themed_count` 件（`balanced` なら各キーワードの上位から順番に取る）
- テーマなし: 期間内の全リポジトリをスター順 → テーマありと重複しないものから上位 `general_count` 件
- 複数の設定に同じリポジトリが入っても、README 取得と Claude での要約は 1 回だけ

## コマンド

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
GITHUB_TOKEN=$(gh auth token) python -m digest --dry-run --limit 2   # Claude を呼ばずに出力まで確認
GITHUB_TOKEN=$(gh auth token) ANTHROPIC_API_KEY=... python -m digest # 本番と同じ処理
```

- `--dry-run` は Claude API を呼ばず、リポジトリの説明文でダミーの解説を作る（費用ゼロで PDF の見た目を確認できる）
- 出力先の既定は `tmp/reports/`（git 管理外）。Actions だけが `--out reports --prune-days 14` で `reports/` に書く
- 特別実行用の上書き: `--days` `--themed-count` `--general-count` `--themes "A,B"` `--balanced`（テーマごとに均等に選ぶ）`--label`（出力フォルダ名の末尾）。上書きがあると設定 1 をベースに 1 冊だけ作る。Actions の Run workflow の入力欄からも同じ指定ができる

## ローカルの reports/

- ローカルのクローンは sparse-checkout で `reports/` を除外している（レポートを手元に置かない方針）。`git pull` しても `reports/` は展開されない
- レポートを見るときは管理画面か GitHub 上で見る。解除する場合は `git sparse-checkout disable`

## 環境

- 開発は WSL (Ubuntu) 上。Windows 側の PowerShell からは `wsl -d ubuntu -- bash -lc '...'` で実行する
- PDF には日本語フォント `Noto Sans CJK JP`（`fonts-noto-cjk`）と pango が必要
- シークレット: `ANTHROPIC_API_KEY`（リポジトリの Actions Secrets）。`GITHUB_TOKEN` は Actions が自動付与
- リポジトリは公開（GitHub Pages を無料プランで使うため）。シークレットやトークンをコミットしないこと
