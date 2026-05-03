from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PlatformType(Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"


@dataclass(slots=True)
class Issue:
    number: int
    title: str
    body: str
    state: str
    html_url: str
    user_login: str
    created_at: str
    labels: list[str]
    platform: PlatformType = PlatformType.GITHUB


@dataclass(slots=True)
class IssueComment:
    id: int
    body: str
    user_login: str
    created_at: str
    reactions: int
    is_maintainer: bool = False


class PlatformClient(ABC):
    @abstractmethod
    def parse_issue_ref(
        self,
        ref: str,
        repo_hint: Optional[str] = None,
    ) -> tuple[PlatformType, str, str, int]:
        """Parse issue reference and return (platform, owner, repo, issue_number)."""
        pass

    @abstractmethod
    def get_issue(self, owner: str, repo: str, issue_num: int) -> Issue:
        """Fetch a single issue by number."""
        pass

    @abstractmethod
    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: Optional[list[str]] = None,
    ) -> list[Issue]:
        """List issues for a repository."""
        pass

    @abstractmethod
    def get_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_num: int,
        limit: int = 7,
        issue_author: Optional[str] = None,
    ) -> list[IssueComment]:
        """Fetch comments for an issue."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the client and release resources."""
        pass

    def _prioritize_comments(
        self,
        comments: list[IssueComment],
        limit: int,
        repo_owner: str = "",
        issue_author: Optional[str] = None,
    ) -> list[IssueComment]:
        """Prioritize comments by maintainer status and reactions."""
        if not comments:
            return []

        maintainer_logins = {repo_owner.lower()}
        if issue_author:
            maintainer_logins.add(issue_author.lower())

        for comment in comments:
            comment.is_maintainer = comment.user_login.lower() in maintainer_logins

        def comment_priority(comment: IssueComment) -> tuple[int, int, str]:
            return (
                0 if comment.is_maintainer else 1,
                -comment.reactions,
                comment.created_at,
            )

        sorted_comments = sorted(comments, key=comment_priority)
        return sorted_comments[:limit]


# Platform detection patterns
GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/?$"
)
GITLAB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?gitlab\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/-/issues/(?P<number>\d+)/?$"
)
BITBUCKET_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?bitbucket\.org/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/?$"
)

# Shorthand patterns (platform:owner/repo#number or owner/repo#number)
HASH_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)#(?P<number>\d+)$")
# Slash pattern (owner/repo/number)
SLASH_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<number>\d+)$")
# Just number pattern
NUMBER_RE = re.compile(r"^(?P<number>\d+)$")

# Platform prefix pattern (e.g., gitlab:owner/repo#123)
PLATFORM_PREFIX_RE = re.compile(
    r"^(?P<platform>github|gitlab|bitbucket):(?P<rest>.+)$"
)


def detect_platform_from_url(url: str) -> Optional[PlatformType]:
    """Detect platform type from a URL."""
    if "github.com" in url:
        return PlatformType.GITHUB
    elif "gitlab.com" in url or "gitlab." in url:
        return PlatformType.GITLAB
    elif "bitbucket.org" in url:
        return PlatformType.BITBUCKET
    return None


def detect_platform_from_remote(remote_url: str) -> Optional[PlatformType]:
    """Detect platform type from a git remote URL."""
    remote_url = remote_url.lower()
    if "github.com" in remote_url:
        return PlatformType.GITHUB
    elif "gitlab.com" in remote_url or "gitlab." in remote_url:
        return PlatformType.GITLAB
    elif "bitbucket.org" in remote_url:
        return PlatformType.BITBUCKET
    return None


def get_platform_client(
    platform: PlatformType,
    token: Optional[str] = None,
) -> PlatformClient:
    """Factory function to get the appropriate platform client."""
    if platform == PlatformType.GITHUB:
        from src.github.client import GitHubClient
        return GitHubClient(token=token)
    elif platform == PlatformType.GITLAB:
        from src.platforms.gitlab import GitLabClient
        return GitLabClient(token=token)
    elif platform == PlatformType.BITBUCKET:
        from src.platforms.bitbucket import BitbucketClient
        return BitbucketClient(token=token)
    else:
        raise ValueError(f"Unsupported platform: {platform}")


__all__ = [
    "PlatformType",
    "Issue",
    "IssueComment",
    "PlatformClient",
    "detect_platform_from_url",
    "detect_platform_from_remote",
    "get_platform_client",
    "GITHUB_URL_RE",
    "GITLAB_URL_RE",
    "BITBUCKET_URL_RE",
    "HASH_RE",
    "SLASH_RE",
    "NUMBER_RE",
    "PLATFORM_PREFIX_RE",
]
