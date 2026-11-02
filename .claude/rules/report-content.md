---
paths:
  - "digest/summarize.py"
  - "digest/render_pdf.py"
  - "digest/templates/**"
---

# レポート内容のルール

- 出力は PDF のみ（PPTX・Markdown・JSON は出さない方針）
- 出力言語は日本語。固有名詞・コマンド・ライブラリ名は原文のまま
- 各リポジトリは「リンク → 一言説明 → 概要 → 要点 → 詳細」の順で、最初に簡潔、後で詳しく
- 解説 JSON のスキーマ（`SCHEMA`）を変えたら、`render_pdf.py`・`templates/report.html.j2`・`summarize.fallback_summary` を追従させる
- README に書かれていないことを推測で断定させない（プロンプトで「不明なら不明と書く」を維持する）
- PDF の見た目を変えたら `python -m digest --dry-run --limit 2` で確認する（出力は `tmp/reports/`）
