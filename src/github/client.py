from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx


ISSUE_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/?$"
)
ISSUE_HASH_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)#(?P<number>\d+)$")
ISSUE_SLASH_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<number>\d+)$")
ISSUE_NUMBER_RE = re.compile(r"^(?P<number>\d+)$")


@dataclass(slots=True)
class GitHubIssue:
    number: int
    title: str
    body: str
    state: str
    html_url: str
    user_login: str
    created_at: str
    labels: list[str]


@dataclass(slots=True)
class GitHubIssueComment:
    id: int
    body: str
    user_login: str
    created_at: str
    reactions: int
    is_maintainer: bool = False


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None, timeout: float = 30.0):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.Client(headers=headers, timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def parse_issue_ref(
        self,
        ref: str,
        repo_hint: str | None = None,
    ) -> tuple[str, str, int]:
        normalized = ref.strip()

        for pattern in (ISSUE_URL_RE, ISSUE_HASH_RE, ISSUE_SLASH_RE):
            match = pattern.match(normalized)
            if match:
                return (
                    match.group("owner"),
                    match.group("repo"),
                    int(match.group("number")),
                )

        number_match = ISSUE_NUMBER_RE.match(normalized)
        if number_match and repo_hint:
            owner, repo = self._parse_repo_hint(repo_hint)
            return owner, repo, int(number_match.group("number"))

        raise ValueError(f"Invalid issue reference: {ref}")

    def _parse_repo_hint(self, repo_hint: str) -> tuple[str, str]:
        parts = repo_hint.strip().split("/", maxsplit=1)
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"Invalid repository reference: {repo_hint}")
        return parts[0], parts[1]

    def get_issue(self, owner: str, repo: str, issue_num: int) -> GitHubIssue:
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{issue_num}"
        response = self.client.get(url)
        response.raise_for_status()
        return self._build_issue(response.json())

    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: list[str] | None = None,
    ) -> list[GitHubIssue]:
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        params: dict[str, str | int] = {"state": state, "per_page": 100}
        if labels:
            params["labels"] = ",".join(labels)

        issues: list[GitHubIssue] = []
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
                issues.append(self._build_issue(item))

            if len(data) < 100:
                break
            page += 1

        return issues

    def _build_issue(self, data: dict) -> GitHubIssue:
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            state=data["state"],
            html_url=data["html_url"],
            user_login=data["user"]["login"],
            created_at=data["created_at"],
            labels=[label["name"] for label in data.get("labels", [])],
        )

    def get_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_num: int,
        limit: int = 7,
        issue_author: str | None = None,
    ) -> list[GitHubIssueComment]:
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{issue_num}/comments"
        params: dict[str, str | int] = {"per_page": 100}

        all_comments: list[GitHubIssueComment] = []
        page = 1

        while True:
            params["page"] = page
            response = self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            for item in data:
                all_comments.append(self._build_comment(item))

            if len(data) < 100:
                break
            page += 1

        return self._prioritize_comments(
            all_comments,
            limit=limit,
            repo_owner=owner,
            issue_author=issue_author,
        )

    def _build_comment(self, data: dict) -> GitHubIssueComment:
        reactions = data.get("reactions", {}).get("total_count", 0)
        return GitHubIssueComment(
            id=data["id"],
            body=data.get("body") or "",
            user_login=data["user"]["login"],
            created_at=data["created_at"],
            reactions=reactions,
        )

    def _prioritize_comments(
        self,
        comments: list[GitHubIssueComment],
        limit: int,
        repo_owner: str = "",
        issue_author: str | None = None,
    ) -> list[GitHubIssueComment]:
        if not comments:
            return []

        maintainer_logins = {repo_owner.lower()}
        if issue_author:
            maintainer_logins.add(issue_author.lower())

        for comment in comments:
            comment.is_maintainer = comment.user_login.lower() in maintainer_logins

        def comment_priority(comment: GitHubIssueComment) -> tuple[int, int, str]:
            return (
                0 if comment.is_maintainer else 1,
                -comment.reactions,
                comment.created_at,
            )

        sorted_comments = sorted(comments, key=comment_priority)
        return sorted_comments[:limit]


def load_issue_from_file(path: str) -> GitHubIssue:
    file_path = Path(path)
    if not file_path.exists():
        raise ValueError(f"File not found: {path}")

    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    title = ""
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if not title and line.startswith("# "):
            title = line[2:].strip()
            in_body = True
            continue
        if in_body:
            body_lines.append(line)

    if not title:
        raise ValueError(f"Issue file must start with a '# ' title heading: {path}")

    body = "\n".join(body_lines).strip()

    return GitHubIssue(
        number=0,
        title=title,
        body=body,
        state="open",
        html_url=file_path.resolve().as_uri(),
        user_login="local",
        created_at="",
        labels=[],
    )


__all__ = ["GitHubClient", "GitHubIssue", "GitHubIssueComment", "load_issue_from_file"]
