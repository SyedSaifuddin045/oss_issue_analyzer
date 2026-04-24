from __future__ import annotations
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx


@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str
    state: str
    html_url: str
    user_login: str
    created_at: str
    labels: list[str]


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.Client(
                headers=headers,
                timeout=30.0,
            )
        return self._client

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def parse_issue_ref(self, ref: str) -> tuple[str, str, int]:
        """Parse issue reference into owner, repo, number.
        
        Supports:
        - https://github.com/owner/repo/issues/123
        - owner/repo#123
        - owner/repo/123
        - 123 (requires --repo flag)
        """
        # URL pattern
        url_match = re.match(
            r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)",
            ref,
        )
        if url_match:
            return (
                url_match.group("owner"),
                url_match.group("repo"),
                int(url_match.group("number")),
            )

        # Hashtag pattern
        hash_match = re.match(r"(?P<owner>[^/]+)/(?P<repo>[^/]+)#(?P<number>\d+)", ref)
        if hash_match:
            return (
                hash_match.group("owner"),
                hash_match.group("repo"),
                int(hash_match.group("number")),
            )

        # Slash pattern
        slash_match = re.match(r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<number>\d+)", ref)
        if slash_match:
            return (
                slash_match.group("owner"),
                slash_match.group("repo"),
                int(slash_match.group("number")),
            )

        raise ValueError(f"Invalid issue reference: {ref}")

    def get_issue(self, owner: str, repo: str, issue_num: int) -> GitHubIssue:
        """Fetch a single issue from a repository."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{issue_num}"
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()

        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body", ""),
            state=data["state"],
            html_url=data["html_url"],
            user_login=data["user"]["login"],
            created_at=data["created_at"],
            labels=[label["name"] for label in data.get("labels", [])],
        )

    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: Optional[list[str]] = None,
    ) -> list[GitHubIssue]:
        """Fetch issues from a repository."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        params = {"state": state, "per_page": 100}
        if labels:
            params["labels"] = ",".join(labels)

        issues = []
        page = 1
        while True:
            params["page"] = page
            response = self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            for item in data:
                if "pull_request" in item:
                    continue
                issues.append(
                    GitHubIssue(
                        number=item["number"],
                        title=item["title"],
                        body=item.get("body", ""),
                        state=item["state"],
                        html_url=item["html_url"],
                        user_login=item["user"]["login"],
                        created_at=item["created_at"],
                        labels=[label["name"] for label in item.get("labels", [])],
                    )
                )

            if len(data) < 100:
                break
            page += 1

        return issues


def load_issue_from_file(path: str) -> GitHubIssue:
    """Load an issue from a local markdown file."""
    file_path = Path(path)
    if not file_path.exists():
        raise ValueError(f"File not found: {path}")

    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    title = ""
    body_lines = []
    in_body = False

    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            in_body = True
            continue
        if in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    return GitHubIssue(
        number=0,
        title=title,
        body=body,
        state="open",
        html_url=f"file://{path}",
        user_login="local",
        created_at="",
        labels=[],
    )


__all__ = [
    "GitHubClient",
    "GitHubIssue",
    "load_issue_from_file",
]