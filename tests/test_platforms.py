from __future__ import annotations

import unittest
from src.platforms.base import (
    PlatformType,
    detect_platform_from_url,
    detect_platform_from_remote,
    get_platform_client,
    GITLAB_URL_RE,
    BITBUCKET_URL_RE,
    HASH_RE,
    PLATFORM_PREFIX_RE,
)


class PlatformDetectionTests(unittest.TestCase):
    def test_detect_platform_from_github_url(self) -> None:
        self.assertEqual(
            detect_platform_from_url("https://github.com/owner/repo/issues/123"),
            PlatformType.GITHUB
        )
        self.assertEqual(
            detect_platform_from_url("https://www.github.com/owner/repo/issues/123"),
            PlatformType.GITHUB
        )

    def test_detect_platform_from_gitlab_url(self) -> None:
        self.assertEqual(
            detect_platform_from_url("https://gitlab.com/owner/repo/-/issues/123"),
            PlatformType.GITLAB
        )
        self.assertEqual(
            detect_platform_from_url("https://www.gitlab.com/owner/repo/-/issues/123"),
            PlatformType.GITLAB
        )

    def test_detect_platform_from_bitbucket_url(self) -> None:
        self.assertEqual(
            detect_platform_from_url("https://bitbucket.org/owner/repo/issues/123"),
            PlatformType.BITBUCKET
        )

    def test_detect_platform_from_unknown_url(self) -> None:
        self.assertIsNone(detect_platform_from_url("https://example.com/owner/repo/issues/123"))

    def test_detect_platform_from_github_remote(self) -> None:
        self.assertEqual(
            detect_platform_from_remote("https://github.com/owner/repo.git"),
            PlatformType.GITHUB
        )
        self.assertEqual(
            detect_platform_from_remote("git@github.com:owner/repo.git"),
            PlatformType.GITHUB
        )

    def test_detect_platform_from_gitlab_remote(self) -> None:
        self.assertEqual(
            detect_platform_from_remote("https://gitlab.com/owner/repo.git"),
            PlatformType.GITLAB
        )
        self.assertEqual(
            detect_platform_from_remote("git@gitlab.com:owner/repo.git"),
            PlatformType.GITLAB
        )

    def test_detect_platform_from_bitbucket_remote(self) -> None:
        self.assertEqual(
            detect_platform_from_remote("https://bitbucket.org/owner/repo.git"),
            PlatformType.BITBUCKET
        )
        self.assertEqual(
            detect_platform_from_remote("git@bitbucket.org:owner/repo.git"),
            PlatformType.BITBUCKET
        )


class PlatformRegexTests(unittest.TestCase):
    def test_gitlab_url_regex(self) -> None:
        match = GITLAB_URL_RE.match("https://gitlab.com/owner/repo/-/issues/123")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("owner"), "owner")
        self.assertEqual(match.group("repo"), "repo")
        self.assertEqual(match.group("number"), "123")

    def test_bitbucket_url_regex(self) -> None:
        match = BITBUCKET_URL_RE.match("https://bitbucket.org/owner/repo/issues/123")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("owner"), "owner")
        self.assertEqual(match.group("repo"), "repo")
        self.assertEqual(match.group("number"), "123")

    def test_hash_regex(self) -> None:
        match = HASH_RE.match("owner/repo#123")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("owner"), "owner")
        self.assertEqual(match.group("repo"), "repo")
        self.assertEqual(match.group("number"), "123")

    def test_platform_prefix_regex(self) -> None:
        match = PLATFORM_PREFIX_RE.match("gitlab:owner/repo#123")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("platform"), "gitlab")
        self.assertEqual(match.group("rest"), "owner/repo#123")

        match = PLATFORM_PREFIX_RE.match("bitbucket:owner/repo#123")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("platform"), "bitbucket")


class PlatformClientFactoryTests(unittest.TestCase):
    def test_get_github_client(self) -> None:
        client = get_platform_client(PlatformType.GITHUB)
        self.assertIsNotNone(client)
        from src.github.client import GitHubClient
        self.assertIsInstance(client, GitHubClient)

    def test_get_gitlab_client(self) -> None:
        client = get_platform_client(PlatformType.GITLAB)
        self.assertIsNotNone(client)
        from src.platforms.gitlab import GitLabClient
        self.assertIsInstance(client, GitLabClient)

    def test_get_bitbucket_client(self) -> None:
        client = get_platform_client(PlatformType.BITBUCKET)
        self.assertIsNotNone(client)
        from src.platforms.bitbucket import BitbucketClient
        self.assertIsInstance(client, BitbucketClient)


if __name__ == "__main__":
    unittest.main()
