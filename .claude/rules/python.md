---
paths:
  - "digest/**/*.py"
---

# Python コードのルール

- Python 3.12。型ヒントを付け、`from __future__ import annotations` を使う
- 依存は `requirements.txt` に固定バージョンで追加する。標準ライブラリで足りるものは追加しない
- Claude API は公式 SDK（`anthropic`）経由のみ。モデルは `summarize.py` の `MODEL` 定数で一元管理する
- Claude の応答は必ず `stop_reason` を確認してから読む（`refusal` / `max_tokens` は失敗として扱う）
- 1 件の要約失敗でレポート全体を止めない。失敗したリポジトリは説明文ベースの簡易解説に置き換え、ログに残す
- ただし認証エラー（401/403）や全件失敗のときは終了コード 1 で止め、レポートを出力しない（Actions を「失敗」にして気づけるようにする）
- GitHub API 呼び出しは `github_client.py` に集約し、他のモジュールから直接 HTTP を叩かない
- シークレットは環境変数からのみ読む。ログやファイルに出力しない
