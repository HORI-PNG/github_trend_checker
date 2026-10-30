---
paths:
  - "digest/summarize.py"
  - "digest/render_*.py"
  - "digest/templates/**"
---

# レポート内容のルール

- 出力言語は日本語。固有名詞・コマンド・ライブラリ名は原文のまま
- 各リポジトリは「リンク → 一言説明 → 概要 → 要点 → 詳細」の順で、最初に簡潔、後で詳しく
- 解説 JSON のスキーマ（`SCHEMA`）を変えたら、`render_pdf.py`・`render_pptx.py`・`templates/report.html.j2`・`main.py` の Markdown 出力をすべて追従させる
- README に書かれていないことを推測で断定させない（プロンプトで「不明なら不明と書く」を維持する）
- PPTX はテキストがはみ出さないよう、詳細は文字数で分割して複数スライドにする
- PDF / PPTX の見た目を変えたら `python -m digest --dry-run --limit 2 --out tmp/` で確認する
