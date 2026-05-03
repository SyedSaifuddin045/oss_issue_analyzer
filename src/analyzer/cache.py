from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.platforms.base import PlatformType


PLATFORM_PREFIX_MAP = {
    PlatformType.GITHUB: "gh",
    PlatformType.GITLAB: "gl",
    PlatformType.BITBUCKET: "bb",
}


def get_cache_dir(repo_root: Path) -> Path:
    cache_dir = repo_root / ".oss-issue-analyzer-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _issue_cache_path(cache_dir: Path, owner: str, repo: str, state: str, platform: Optional[PlatformType] = None) -> Path:
    platform_prefix = PLATFORM_PREFIX_MAP.get(platform, "gh") if platform else "gh"
    name = f"{platform_prefix}_{owner}_{repo}_{state}.json"
    safe_name = hashlib.sha256(name.encode()).hexdigest()[:16] + ".json"
    return cache_dir / "issues" / safe_name


def _analysis_cache_path(cache_dir: Path, owner: str, repo: str, issue_num: int, platform: Optional[PlatformType] = None) -> Path:
    platform_prefix = PLATFORM_PREFIX_MAP.get(platform, "gh") if platform else "gh"
    name = f"{platform_prefix}_{owner}_{repo}_{issue_num}.json"
    safe_name = hashlib.sha256(name.encode()).hexdigest()[:16] + ".json"
    return cache_dir / "analysis" / safe_name


def load_issue_cache(
    repo_root: Path,
    owner: str,
    repo: str,
    state: str,
    platform: Optional[PlatformType] = None,
    ttl_hours: int = 1,
) -> Optional[dict]:
    cache_dir = get_cache_dir(Path(repo_root))
    path = _issue_cache_path(cache_dir, owner, repo, state, platform)
    if not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)

        fetched_at_str = data.get("fetched_at")
        if not fetched_at_str:
            return None

        fetched_at = datetime.fromisoformat(fetched_at_str)
        now = datetime.now(timezone.utc)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)

        age_hours = (now - fetched_at).total_seconds() / 3600
        if age_hours > ttl_hours:
            return None

        return data
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def save_issue_cache(
    repo_root: Path,
    owner: str,
    repo: str,
    state: str,
    issues_data: list[dict],
    platform: Optional[PlatformType] = None,
    ttl_hours: int = 1,
) -> None:
    cache_dir = get_cache_dir(Path(repo_root))
    issues_dir = cache_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)

    path = _issue_cache_path(cache_dir, owner, repo, state, platform)
    platform_prefix = PLATFORM_PREFIX_MAP.get(platform, "gh") if platform else "gh"
    data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ttl_hours": ttl_hours,
        "platform": platform_prefix,
        "repo": f"{owner}/{repo}",
        "state": state,
        "issues": issues_data,
    }

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def load_analysis_cache(
    repo_root: Path,
    owner: str,
    repo: str,
    issue_num: int,
    platform: Optional[PlatformType] = None,
    expected_signature: str | None = None,
) -> Optional[dict]:
    cache_dir = get_cache_dir(Path(repo_root))
    path = _analysis_cache_path(cache_dir, owner, repo, issue_num, platform)
    if not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None

    if expected_signature and data.get("analysis_signature") != expected_signature:
        return None
    return data


def save_analysis_cache(
    repo_root: Path,
    owner: str,
    repo: str,
    issue_num: int,
    result_dict: dict,
    platform: Optional[PlatformType] = None,
    quick_score_original: float | None = None,
    analysis_signature: str | None = None,
    scoring_method: str | None = None,
) -> None:
    cache_dir = get_cache_dir(Path(repo_root))
    analysis_dir = cache_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    path = _analysis_cache_path(cache_dir, owner, repo, issue_num, platform)
    platform_prefix = PLATFORM_PREFIX_MAP.get(platform, "gh") if platform else "gh"
    data = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform_prefix,
        "repo": f"{owner}/{repo}",
        "issue_number": issue_num,
        "analysis_signature": analysis_signature,
        "scoring_method": scoring_method,
        "result": result_dict,
        "quick_score_original": quick_score_original,
        "quick_score_updated": quick_score_original,
    }

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def update_cached_issue_difficulty(
    repo_root: Path,
    owner: str,
    repo: str,
    issue_num: int,
    new_difficulty: str,
    new_score: float,
    platform: Optional[PlatformType] = None,
) -> bool:
    cache_dir = get_cache_dir(Path(repo_root))

    for state in ["open", "all", "closed"]:
        path = _issue_cache_path(cache_dir, owner, repo, state, platform)
        if not path.exists():
            continue

        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)

            updated = False
            for issue in data.get("issues", []):
                if issue.get("number") == issue_num:
                    issue["difficulty"] = new_difficulty
                    issue["quick_score"] = new_score
                    updated = True

            if updated:
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2)
                return True
        except (json.JSONDecodeError, KeyError, OSError):
            continue

    return False


def clear_cache(repo_root: Path) -> None:
    cache_dir = Path(repo_root) / ".oss-issue-analyzer-cache"
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)


__all__ = [
    "get_cache_dir",
    "load_issue_cache",
    "save_issue_cache",
    "load_analysis_cache",
    "save_analysis_cache",
    "update_cached_issue_difficulty",
    "clear_cache",
    "PlatformType",
    "PLATFORM_PREFIX_MAP",
]
