---
paths:
  - "docs/**"
  - "config/themes.json"
---

# 管理画面・設定ファイルのルール

- `docs/` は GitHub Pages でそのまま配信する静的ファイル。ビルド工程や外部 JS ライブラリは入れない
- 管理画面は「本当に簡潔」が要件。設定は最大 3 セット（`profiles`）で、各セットは名前・テーマ・言語・期間・件数・均等選定に留める
- 書き込みはユーザーが入力した fine-grained PAT（このリポジトリのみ。Contents と Actions の Read and write だけ）で行う。トークンは `localStorage` にだけ保存し、URL やリポジトリには絶対に書かない。`localStorage` アクセスは try/catch で囲む
- `config/themes.json` のキーを変えたら `digest/config.py` の検証と管理画面のフォーム（`profile-template` と `readProfiles`）を両方直す。上限値（件数 0〜20、期間 1〜365、最大 3 セット）も両方で揃える
- 日本語を含む JSON を GitHub API に送るときは UTF-8 → Base64 で変換する（`btoa` を直接使わない）
