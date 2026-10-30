from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

API = "https://api.github.com"

# 技術構成を把握するために読む代表的なマニフェスト
MANIFESTS = [
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "composer.json",
    "Dockerfile",
]
README_MAX_CHARS = 60_000
MANIFEST_MAX_CHARS = 4_000
TREE_MAX_PATHS = 300


@dataclass
class Repo:
    full_name: str
    html_url: str
    description: str
    stars: int
    forks: int
    language: str
    topics: list[str]
    created_at: str
    default_branch: str
    license: str
    category: str  # "theme" or "general"
    matched_themes: list[str] = field(default_factory=list)
    readme: str = ""
    tree: list[str] = field(default_factory=list)
    manifests: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_api(cls, item: dict, category: str) -> Repo:
        return cls(
            full_name=item["full_name"],
            html_url=item["html_url"],
            description=item.get("description") or "",
            stars=item.get("stargazers_count", 0),
            forks=item.get("forks_count", 0),
            language=item.get("language") or "",
            topics=item.get("topics") or [],
            created_at=item.get("created_at", ""),
            default_branch=item.get("default_branch") or "main",
            license=(item.get("license") or {}).get("spdx_id") or "",
            category=category,
        )


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            log.warning("GITHUB_TOKEN が未設定のため、未認証（低いレート制限）で実行します")

    def _get(self, path: str, **kwargs) -> requests.Response:
        for attempt in range(3):
            resp = self.session.get(f"{API}{path}", timeout=30, **kwargs)
            # 検索 API のレート制限（403/429）は少し待って再試行する
            if resp.status_code in (403, 429) and attempt < 2:
                wait = int(resp.headers.get("retry-after", "20"))
                log.warning("GitHub のレート制限に達しました。%d 秒待機します", wait)
                time.sleep(wait)
                continue
            return resp
        return resp

    def search_repos(self, query: str, per_page: int = 30) -> list[dict]:
        resp = self._get(
            "/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": per_page},
        )
        resp.raise_for_status()
        return resp.json().get("items", [])

    def fetch_readme(self, full_name: str) -> str:
        resp = self._get(
            f"/repos/{full_name}/readme", headers={"Accept": "application/vnd.github.raw+json"}
        )
        if resp.status_code != 200:
            return ""
        return resp.text[:README_MAX_CHARS]

    def fetch_tree(self, full_name: str, branch: str) -> list[str]:
        resp = self._get(f"/repos/{full_name}/git/trees/{branch}", params={"recursive": "1"})
        if resp.status_code != 200:
            return []
        paths = [e["path"] for e in resp.json().get("tree", []) if e.get("type") == "blob"]
        return paths[:TREE_MAX_PATHS]

    def fetch_file(self, full_name: str, path: str) -> str:
        resp = self._get(f"/repos/{full_name}/contents/{path}")
        if resp.status_code != 200:
            return ""
        data = resp.json()
        if data.get("encoding") != "base64":
            return ""
        text = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return text[:MANIFEST_MAX_CHARS]

    def enrich(self, repo: Repo) -> None:
        """README・ファイル一覧・ルート直下のマニフェストを取得して repo に詰める。"""
        repo.readme = self.fetch_readme(repo.full_name)
        repo.tree = self.fetch_tree(repo.full_name, repo.default_branch)
        for name in MANIFESTS:
            if name in repo.tree:
                content = self.fetch_file(repo.full_name, name)
                if content:
                    repo.manifests[name] = content
