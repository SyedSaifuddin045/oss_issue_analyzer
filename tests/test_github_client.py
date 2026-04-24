from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.github.client import GitHubClient, load_issue_from_file


class GitHubClientTests(unittest.TestCase):
    def test_parse_issue_ref_supports_common_formats(self) -> None:
        client = GitHubClient()
        cases = [
            (
                "https://github.com/openai/openai-python/issues/123",
                None,
                ("openai", "openai-python", 123),
            ),
            ("openai/openai-python#456", None, ("openai", "openai-python", 456)),
            ("openai/openai-python/789", None, ("openai", "openai-python", 789)),
            ("42", "openai/openai-python", ("openai", "openai-python", 42)),
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


if __name__ == "__main__":
    unittest.main()
