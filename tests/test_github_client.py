from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from src.github.client import GitHubClient, GitHubIssueComment, load_issue_from_file
from src.platforms.base import PlatformType


class GitHubClientTests(unittest.TestCase):
    def test_parse_issue_ref_supports_common_formats(self) -> None:
        client = GitHubClient()
        cases = [
            (
                "https://github.com/openai/openai-python/issues/123",
                None,
                (PlatformType.GITHUB, "openai", "openai-python", 123),
            ),
            ("openai/openai-python#456", None, (PlatformType.GITHUB, "openai", "openai-python", 456)),
            ("openai/openai-python/789", None, (PlatformType.GITHUB, "openai", "openai-python", 789)),
            ("42", "openai/openai-python", (PlatformType.GITHUB, "openai", "openai-python", 42)),
        ]

        for ref, repo_hint, expected in cases:
            with self.subTest(ref=ref):
                self.assertEqual(client.parse_issue_ref(ref, repo_hint=repo_hint), expected)

    def test_parse_issue_ref_rejects_plain_number_without_repo_hint(self) -> None:
        client = GitHubClient()

        with self.assertRaisesRegex(ValueError, "Invalid issue reference"):
            client.parse_issue_ref("42")

    def test_load_issue_from_file_reads_title_and_body(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            temp_dir = Path(tmp_dir)
            issue_file = temp_dir / "issue.md"
            issue_file.write_text("# Fix flaky parser\n\nBody line 1\nBody line 2\n", encoding="utf-8")

            issue = load_issue_from_file(str(issue_file))

            self.assertEqual(issue.title, "Fix flaky parser")
            self.assertEqual(issue.body, "Body line 1\nBody line 2")
            self.assertEqual(issue.html_url, issue_file.resolve().as_uri())

    def test_load_issue_from_file_requires_markdown_heading(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            temp_dir = Path(tmp_dir)
            issue_file = temp_dir / "issue.md"
            issue_file.write_text("No heading here\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "must start with a '# ' title heading"):
                load_issue_from_file(str(issue_file))

    def test_comment_prioritization_sorts_by_reactions(self) -> None:
        client = GitHubClient()
        
        comments = [
            GitHubIssueComment(id=1, body="Zero reactions", user_login="user1", created_at="", reactions=0),
            GitHubIssueComment(id=2, body="Ten reactions", user_login="user2", created_at="", reactions=10),
            GitHubIssueComment(id=3, body="Five reactions", user_login="user3", created_at="", reactions=5),
        ]
        
        prioritized = client._prioritize_comments(comments, limit=7)
        
        self.assertEqual(prioritized[0].reactions, 10)
        self.assertEqual(prioritized[1].reactions, 5)
        self.assertEqual(prioritized[2].reactions, 0)

    def test_comment_prioritization_respects_limit(self) -> None:
        client = GitHubClient()
        
        comments = [
            GitHubIssueComment(id=i, body=f"Comment {i}", user_login=f"user{i}", created_at="", reactions=i)
            for i in range(15)
        ]
        
        prioritized = client._prioritize_comments(comments, limit=5)
        
        self.assertEqual(len(prioritized), 5)


if __name__ == "__main__":
    unittest.main()
