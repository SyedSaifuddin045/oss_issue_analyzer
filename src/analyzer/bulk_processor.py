from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.analyzer.quick_scorer import QuickHeuristicScorer
from src.analyzer.preprocessor import IssuePreprocessor
from src.analyzer.retriever import HybridRetriever, RetrievalResult
from src.github.client import GitHubIssue


def _make_worker_state(db_path: str, repo_id: str):
    """Initialize per-worker state (one per thread)."""
    preprocessor = IssuePreprocessor()
    retriever = HybridRetriever(db_path=db_path)
    retriever.set_repo(repo_id)
    scorer = QuickHeuristicScorer()
    return preprocessor, retriever, scorer


def _process_single_issue(issue: GitHubIssue, worker_state) -> dict:
    """Process a single issue (called by each worker)."""
    preprocessor, retriever, scorer = worker_state
    
    try:
        processed = preprocessor.process(issue.title, issue.body)
        retrieval = retriever.search(processed, retriever._repo_id, limit=3)
        result = scorer.score(processed, retrieval, labels=issue.labels)
        
        return {
            "number": issue.number,
            "title": issue.title,
            "labels": issue.labels,
            "difficulty": result.difficulty.value,
            "confidence": result.confidence,
            "quick_score": result.raw_score,
            "issue_type": processed.issue_type.value,
        }
    except Exception:
        return {
            "number": issue.number,
            "title": issue.title,
            "labels": issue.labels,
            "difficulty": "unknown",
            "confidence": 0.0,
            "quick_score": 0.5,
            "issue_type": "unknown",
        }


class BulkProcessor:
    """Process multiple issues in parallel with quick heuristic scoring."""
    
    def __init__(
        self,
        db_path: str,
        repo_id: str,
        max_workers: Optional[int] = None,
    ):
        self.db_path = db_path
        self.repo_id = repo_id
        self.max_workers = max_workers or min((os.cpu_count() or 4), 8)
    
    def process_issues(
        self,
        issues: list[GitHubIssue],
        limit: int = 0,
    ) -> list[dict]:
        """Process issues in parallel and return sorted results."""
        if limit > 0:
            issues = issues[:limit]
        
        if not issues:
            return []
        
        results = []
        failed = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            worker_state = _make_worker_state(self.db_path, self.repo_id)
            
            future_to_issue = {
                executor.submit(_process_single_issue, issue, worker_state): issue
                for issue in issues
            }
            
            for future in as_completed(future_to_issue):
                issue = future_to_issue[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception:
                    failed.append({
                        "number": issue.number,
                        "title": issue.title,
                        "labels": issue.labels,
                        "difficulty": "unknown",
                        "confidence": 0.0,
                        "quick_score": 0.5,
                        "issue_type": "unknown",
                    })
        
        results.sort(key=lambda x: (x["quick_score"], x["number"]))
        return results


__all__ = ["BulkProcessor", "QuickHeuristicScorer"]