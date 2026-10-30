---
paths:
  - "docs/**"
  - "config/themes.json"
---

# 管理画面・設定ファイルのルール

- `docs/` は GitHub Pages でそのまま配信する静的ファイル。ビルド工程や外部 JS ライブラリは入れない
- 管理画面は「本当に簡潔」が要件。設定項目はテーマ・言語・件数程度に留める
- 書き込みはユーザーが入力した fine-grained PAT（このリポジトリのみ。Contents と Actions の Read and write だけ）で行う。トークンは `localStorage` にだけ保存し、URL やリポジトリには絶対に書かない。`localStorage` アクセスは try/catch で囲む
- `config/themes.json` のキーを変えたら `digest/config.py` の検証と管理画面のフォームを両方直す
- 日本語を含む JSON を GitHub API に送るときは UTF-8 → Base64 で変換する（`btoa` を直接使わない）
