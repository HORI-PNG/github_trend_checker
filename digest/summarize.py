from __future__ import annotations

import json
import logging

import anthropic

from digest.github_client import Repo

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
EFFORT = "high"
MAX_TOKENS = 32_000

SCHEMA = {
    "type": "object",
    "properties": {
        "one_liner": {"type": "string", "description": "何のリポジトリかを一文（60字程度）で"},
        "summary": {"type": "string", "description": "3〜4文の概要"},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要点を3〜5個。各40字程度",
        },
        "details": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["heading", "body"],
                "additionalProperties": False,
            },
            "description": "詳細解説のセクション。4〜6個",
        },
        "tech_stack": {"type": "array", "items": {"type": "string"}},
        "target_users": {"type": "string", "description": "どんな人・用途に向いているか"},
    },
    "required": ["one_liner", "summary", "key_points", "details", "tech_stack", "target_users"],
    "additionalProperties": False,
}

SYSTEM = """あなたは GitHub のリポジトリを日本のエンジニア・学生向けに紹介する技術ライターです。
与えられたリポジトリ情報（メタデータ・README・ファイル一覧・マニフェスト）だけを根拠に、日本語で解説を書いてください。

書き方:
- one_liner: 何のリポジトリかを一文で。
- summary: 何を解決するのか、誰のためのものか、どこが新しいのかを 3〜4 文で。
- key_points: 読み手が最初に知るべき要点を 3〜5 個。
- details: 次の観点から、情報があるものを 4〜6 セクションにまとめる。各セクションの body は 200〜400 字程度。
  「何をするものか」「主な機能」「仕組み・アーキテクチャ」「技術構成」「使い方・導入方法」「注目ポイント・注意点」
- tech_stack: 使われている言語・フレームワーク・主要ライブラリ。
- target_users: 向いている人や用途。

注意:
- 資料に書かれていないことを推測で断定しない。不明な点は「README からは不明」と書く。
- 固有名詞・コマンド・ライブラリ名は原文のまま書く。
- Markdown 記法（#, **, ``` など）は使わず、プレーンな文章で書く。"""


def _build_prompt(repo: Repo) -> str:
    manifests = "\n\n".join(f"--- {name} ---\n{body}" for name, body in repo.manifests.items())
    return f"""<metadata>
名前: {repo.full_name}
URL: {repo.html_url}
説明: {repo.description or "（なし）"}
スター: {repo.stars} / フォーク: {repo.forks}
主要言語: {repo.language or "不明"}
トピック: {", ".join(repo.topics) or "（なし）"}
ライセンス: {repo.license or "不明"}
作成日時: {repo.created_at}
</metadata>

<readme>
{repo.readme or "（README なし）"}
</readme>

<file_tree>
{chr(10).join(repo.tree) or "（取得できず）"}
</file_tree>

<manifests>
{manifests or "（なし）"}
</manifests>

上記のリポジトリを解説してください。"""


def fallback_summary(repo: Repo, reason: str) -> dict:
    """Claude を使えない・失敗したときの簡易解説。"""
    desc = repo.description or "説明文はありません。"
    return {
        "one_liner": desc[:80],
        "summary": desc,
        "key_points": [f"スター数: {repo.stars}", f"主要言語: {repo.language or '不明'}"],
        "details": [{"heading": "注記", "body": reason}],
        "tech_stack": [repo.language] if repo.language else [],
        "target_users": "README からは不明",
    }


def summarize(client: anthropic.Anthropic, repo: Repo) -> dict | None:
    """解説 JSON を返す。失敗時は None。API キーの問題は全件に影響するので例外のまま投げる。"""
    try:
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content": _build_prompt(repo)}],
        ) as stream:
            message = stream.get_final_message()
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise
    except anthropic.APIError as e:
        log.error("%s: Claude API エラー: %s", repo.full_name, e)
        return None

    usage = message.usage
    log.info(
        "%s: input=%d output=%d stop=%s",
        repo.full_name,
        usage.input_tokens,
        usage.output_tokens,
        message.stop_reason,
    )
    if message.stop_reason != "end_turn":
        log.error("%s: 想定外の stop_reason=%s", repo.full_name, message.stop_reason)
        return None

    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.error("%s: 応答が JSON として読めませんでした", repo.full_name)
        return None
