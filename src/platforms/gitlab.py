from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from src.platforms.base import (
    PlatformClient,
    PlatformType,
    Issue,
    IssueComment,
)


GITLAB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?gitlab\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/-/issues/(?P<number>\d+)/?$"
)
GITLAB_HASH_RE = re.compile(
    r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)#(?P<number>\d+)$"
)
GITLAB_SLASH_RE = re.compile(
    r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<number>\d+)$"
)
GITLAB_NUMBER_RE = re.compile(r"^(?P<number>\d+)$")


class GitLabClient(PlatformClient):
    BASE_URL = "https://gitlab.com/api/v4"

    def __init__(self, token: Optional[str] = None, timeout: float = 30.0):
        self.token = token or os.environ.get("GITLAB_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers = {
                "Accept": "application/json",
            }
            if self.token:
                headers["PRIVATE-TOKEN"] = self.token
            self._client = httpx.Client(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def parse_issue_ref(
        self,
        ref: str,
        repo_hint: Optional[str] = None,
    ) -> tuple[PlatformType, str, str, int]:
        normalized = ref.strip()

        # Check for platform prefix (gitlab:owner/repo#123)
        from src.platforms.base import PLATFORM_PREFIX_RE
        prefix_match = PLATFORM_PREFIX_RE.match(normalized)
        if prefix_match:
            rest = prefix_match.group("rest")
            return self.parse_issue_ref(rest, repo_hint)

        for pattern in (GITLAB_URL_RE, GITLAB_HASH_RE, GITLAB_SLASH_RE):
            match = pattern.match(normalized)
            if match:
                return (
                    PlatformType.GITLAB,
                    match.group("owner"),
                    match.group("repo"),
                    int(match.group("number")),
                )

        number_match = GITLAB_NUMBER_RE.match(normalized)
        if number_match and repo_hint:
            owner, repo = self._parse_repo_hint(repo_hint)
            return PlatformType.GITLAB, owner, repo, int(number_match.group("number"))

        raise ValueError(f"Invalid GitLab issue reference: {ref}")

    def _parse_repo_hint(self, repo_hint: str) -> tuple[str, str]:
        parts = repo_hint.strip().split("/", maxsplit=1)
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"Invalid repository reference: {repo_hint}")
        return parts[0], parts[1]

    def _encode_project(self, owner: str, repo: str) -> str:
        """Encode project path for GitLab API (URL-encoded)."""
        return f"{owner}%2F{repo}"

    def get_issue(self, owner: str, repo: str, issue_num: int) -> Issue:
        project = self._encode_project(owner, repo)
        url = f"/projects/{project}/issues/{issue_num}"
        response = self.client.get(url)
        response.raise_for_status()
        return self._build_issue(response.json())

    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "opened",
        labels: Optional[list[str]] = None,
    ) -> list[Issue]:
        project = self._encode_project(owner, repo)
        url = f"/projects/{project}/issues"
        params: dict[str, str | int] = {"state": state, "per_page": 100}
        if labels:
            params["labels"] = ",".join(labels)

        issues: list[Issue] = []
        page = 1

        while True:
            params["page"] = page
            response = self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            for item in data:
                issues.append(self._build_issue(item))

            if len(data) < 100:
                break
            page += 1

        return issues

    def _build_issue(self, data: dict) -> Issue:
        return Issue(
            number=data["iid"],
            title=data["title"],
            body=data.get("description") or "",
            state="open" if data.get("state") == "opened" else data.get("state", "unknown"),
            html_url=data.get("web_url", ""),
            user_login=data.get("author", {}).get("username", "unknown"),
            created_at=data.get("created_at", ""),
            labels=[label["name"] if isinstance(label, dict) else label for label in data.get("labels", [])],
            platform=PlatformType.GITLAB,
        )

    def get_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_num: int,
        limit: int = 7,
        issue_author: Optional[str] = None,
    ) -> list[IssueComment]:
        project = self._encode_project(owner, repo)
        url = f"/projects/{project}/issues/{issue_num}/notes"
        params: dict[str, str | int] = {"per_page": 100}

        all_comments: list[IssueComment] = []
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

    def _build_comment(self, data: dict) -> IssueComment:
        return IssueComment(
            id=data["id"],
            body=data.get("body") or "",
            user_login=data.get("author", {}).get("username", "unknown"),
            created_at=data.get("created_at", ""),
            reactions=data.get("upvotes", 0) + data.get("downvotes", 0),
        )


__all__ = ["GitLabClient", "GITLAB_URL_RE", "GITLAB_HASH_RE", "GITLAB_SLASH_RE"]
