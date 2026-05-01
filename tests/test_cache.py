from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone


class TestCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.repo_root = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_cache_dir_creates_directory(self):
        from src.analyzer.cache import get_cache_dir
        cache_dir = get_cache_dir(self.repo_root)
        
        self.assertTrue(cache_dir.exists())
        self.assertTrue(cache_dir.name, ".oss-issue-analyzer-cache")

    def test_save_and_load_issue_cache(self):
        from src.analyzer.cache import (
            save_issue_cache, load_issue_cache,
        )

        issues_data = [
            {"number": 1, "title": "Issue 1", "difficulty": "easy", "confidence": 0.8},
            {"number": 2, "title": "Issue 2", "difficulty": "hard", "confidence": 0.7},
        ]

        save_issue_cache(self.repo_root, "owner", "repo", "open", issues_data, ttl_hours=1)

        loaded = load_issue_cache(self.repo_root, "owner", "repo", "open", ttl_hours=1)
        
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded["issues"]), 2)
        self.assertEqual(loaded["repo"], "owner/repo")

    def test_load_expired_cache_returns_none(self):
        from src.analyzer.cache import (
            save_issue_cache, load_issue_cache,
        )

        issues_data = [{"number": 1, "title": "Test"}]

        save_issue_cache(self.repo_root, "owner", "repo", "open", issues_data, ttl_hours=1)

        loaded = load_issue_cache(self.repo_root, "owner", "repo", "open", ttl_hours=0)
        
        self.assertIsNone(loaded)

    def test_save_and_load_analysis_cache(self):
        from src.analyzer.cache import (
            save_analysis_cache, load_analysis_cache,
        )

        result_dict = {
            "issue_title": "Test Issue",
            "overall_difficulty": {"raw_score": 0.3, "difficulty": "easy", "confidence": 0.85},
        }

        save_analysis_cache(self.repo_root, "owner", "repo", 123, result_dict)

        loaded = load_analysis_cache(self.repo_root, "owner", "repo", 123)
        
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["issue_number"], 123)
        self.assertEqual(loaded["result"]["issue_title"], "Test Issue")

    def test_update_cached_issue_difficulty(self):
        from src.analyzer.cache import (
            save_issue_cache, update_cached_issue_difficulty,
        )

        issues_data = [
            {"number": 123, "title": "Issue 123", "difficulty": "easy", "quick_score": 0.3},
        ]

        save_issue_cache(self.repo_root, "owner", "repo", "open", issues_data, ttl_hours=1)

        result = update_cached_issue_difficulty(
            self.repo_root, "owner", "repo", 123, "hard", 0.8
        )
        
        self.assertTrue(result)

        from src.analyzer.cache import load_issue_cache
        loaded = load_issue_cache(self.repo_root, "owner", "repo", "open", ttl_hours=1)
        
        issue = next(i for i in loaded["issues"] if i["number"] == 123)
        self.assertEqual(issue["difficulty"], "hard")
        self.assertEqual(issue["quick_score"], 0.8)

    def test_update_nonexistent_issue_returns_false(self):
        from src.analyzer.cache import update_cached_issue_difficulty
        
        result = update_cached_issue_difficulty(
            self.repo_root, "owner", "repo", 999, "hard", 0.8
        )
        
        self.assertFalse(result)

    def test_clear_cache(self):
        from src.analyzer.cache import save_issue_cache, clear_cache
        
        issues_data = [{"number": 1, "title": "Test"}]
        save_issue_cache(self.repo_root, "owner", "repo", "open", issues_data, ttl_hours=1)
        
        clear_cache(self.repo_root)
        
        cache_dir = self.repo_root / ".oss-issue-analyzer-cache"
        self.assertFalse(cache_dir.exists())


if __name__ == "__main__":
    unittest.main()