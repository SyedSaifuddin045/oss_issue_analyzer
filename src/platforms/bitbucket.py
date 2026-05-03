from __future__ import annotations

import os
import re
from typing import Optional

import httpx

from src.platforms.base import (
    PlatformClient,
    PlatformType,
    Issue,
    IssueComment,
)


BITBUCKET_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?bitbucket\.org/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/?$"
)
BITBUCKET_HASH_RE = re.compile(
    r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)#(?P<number>\d+)$"
)
BITBUCKET_SLASH_RE = re.compile(
    r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<number>\d+)$"
)
BITBUCKET_NUMBER_RE = re.compile(r"^(?P<number>\d+)$")


class BitbucketClient(PlatformClient):
    BASE_URL = "https://api.bitbucket.org/2.0"

    def __init__(self, token: Optional[str] = None, timeout: float = 30.0):
        self.username = os.environ.get("BITBUCKET_USERNAME")
        self.app_password = os.environ.get("BITBUCKET_APP_PASSWORD")
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers = {
                "Accept": "application/json",
            }
            auth = None
            if self.username and self.app_password:
                auth = (self.username, self.app_password)
            self._client = httpx.Client(
                base_url=self.BASE_URL,
                headers=headers,
                auth=auth,
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

        # Check for platform prefix (bitbucket:owner/repo#123)
        from src.platforms.base import PLATFORM_PREFIX_RE
        prefix_match = PLATFORM_PREFIX_RE.match(normalized)
        if prefix_match:
            rest = prefix_match.group("rest")
            return self.parse_issue_ref(rest, repo_hint)

        for pattern in (BITBUCKET_URL_RE, BITBUCKET_HASH_RE, BITBUCKET_SLASH_RE):
            match = pattern.match(normalized)
            if match:
                return (
                    PlatformType.BITBUCKET,
                    match.group("owner"),
                    match.group("repo"),
                    int(match.group("number")),
                )

        number_match = BITBUCKET_NUMBER_RE.match(normalized)
        if number_match and repo_hint:
            owner, repo = self._parse_repo_hint(repo_hint)
            return PlatformType.BITBUCKET, owner, repo, int(number_match.group("number"))

        raise ValueError(f"Invalid Bitbucket issue reference: {ref}")

    def _parse_repo_hint(self, repo_hint: str) -> tuple[str, str]:
        parts = repo_hint.strip().split("/", maxsplit=1)
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"Invalid repository reference: {repo_hint}")
        return parts[0], parts[1]

    def get_issue(self, owner: str, repo: str, issue_num: int) -> Issue:
        url = f"/repositories/{owner}/{repo}/issues/{issue_num}"
        response = self.client.get(url)
        response.raise_for_status()
        return self._build_issue(response.json())

    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: Optional[list[str]] = None,
    ) -> list[Issue]:
        url = f"/repositories/{owner}/{repo}/issues"
        params: dict[str, str | int] = {"sort": "created_on", "pagelen": 50}

        # Map state to Bitbucket states
        if state == "open":
            params["q"] = 'state="open"'
        elif state == "closed":
            params["q"] = 'state="resolved" OR state="closed"'
        elif state == "all":
            pass

        issues: list[Issue] = []
        next_url = url

        while next_url:
            if next_url == url:
                response = self.client.get(next_url, params=params)
            else:
                response = self.client.get(next_url)
            response.raise_for_status()
            data = response.json()

            for item in data.get("values", []):
                issues.append(self._build_issue(item))

            next_url = data.get("next")

        return issues

    def _build_issue(self, data: dict) -> Issue:
        state_map = {
            "open": "open",
            "resolved": "closed",
            "closed": "closed",
            "wontfix": "closed",
            "invalid": "closed",
            "duplicate": "closed",
        }
        return Issue(
            number=data["id"],
            title=data.get("title", ""),
            body=data.get("content", {}).get("raw", "") or "",
            state=state_map.get(data.get("state", ""), data.get("state", "unknown")),
            html_url=data.get("links", {}).get("html", {}).get("href", ""),
            user_login=data.get("reporter", {}).get("username", "unknown"),
            created_at=data.get("created_on", ""),
            labels=[label.get("name", "") for label in data.get("labels", []) if label.get("name")],
            platform=PlatformType.BITBUCKET,
        )

    def get_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_num: int,
        limit: int = 7,
        issue_author: Optional[str] = None,
    ) -> list[IssueComment]:
        url = f"/repositories/{owner}/{repo}/issues/{issue_num}/comments"
        params: dict[str, str | int] = {"pagelen": 50}

        all_comments: list[IssueComment] = []
        next_url = url

        while next_url:
            if next_url == url:
                response = self.client.get(next_url, params=params)
            else:
                response = self.client.get(next_url)
            response.raise_for_status()
            data = response.json()

            for item in data.get("values", []):
                all_comments.append(self._build_comment(item))

            next_url = data.get("next")

        return self._prioritize_comments(
            all_comments,
            limit=limit,
            repo_owner=owner,
            issue_author=issue_author,
        )

    def _build_comment(self, data: dict) -> IssueComment:
        return IssueComment(
            id=data["id"],
            body=data.get("content", {}).get("raw", "") or "",
            user_login=data.get("user", {}).get("username", "unknown"),
            created_at=data.get("created_on", ""),
            reactions=0,
        )


__all__ = ["BitbucketClient", "BITBUCKET_URL_RE", "BITBUCKET_HASH_RE", "BITBUCKET_SLASH_RE"]
