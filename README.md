# github_trend_checker

毎週月曜 10:00（JST）に、直近1週間に作られた GitHub リポジトリをスター順に集め、Claude が日本語で解説した PDF / PPTX を `reports/` に保存します。

- テーマあり: 管理画面で設定したキーワードに関連するもの（既定 5 件）
- テーマなし: 単純にスターが多いもの（既定 5 件）
- 各リポジトリ: リンク → 一言説明 → 概要 → 要点 → 詳細

## 初回セットアップ

1. **Anthropic API キーを登録**
   リポジトリの Settings → Secrets and variables → Actions → New repository secret
   名前 `ANTHROPIC_API_KEY`、値に API キー
2. **GitHub Pages を有効化**
   Settings → Pages → Source: Deploy from a branch → Branch: `main` / フォルダ `/docs`
3. **管理画面用トークンを作成**
   GitHub → Settings → Developer settings → Fine-grained tokens → Generate new token
   - Repository access: このリポジトリのみ
   - Permissions: Contents = Read and write、Actions = Read and write
   作成したトークンを管理画面の「GitHub トークン」に保存

## 使い方

- 管理画面: `https://<ユーザー名>.github.io/github_trend_checker/`
- 手動実行: 管理画面の「今すぐ実行」または Actions タブ → Weekly GitHub Digest → Run workflow
- レポート: `reports/YYYY-MM-DD/`（`report.pdf` / `report.pptx` / `report.md` / `data.json`）

## ローカル実行

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
GITHUB_TOKEN=$(gh auth token) python -m digest --dry-run --limit 2 --out tmp/
```
