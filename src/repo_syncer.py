"""Repository Syncer - Tracks and syncs updates from source repositories.

This module provides functionality to:
- Check for skill updates in tracked repositories
- Sync repository metadata (stars, forks, etc.)
- Detect new skills in existing repositories
- Only sync active repositories (stars > threshold)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

from github import Github, GithubException

from .config import Config
from .tracker import Tracker, SkillInfo
from .github_searcher import GitHubSearcher, RepoInfo


logger = logging.getLogger(__name__)


@dataclass
class SkillUpdate:
    """Information about a skill update."""
    file_hash: str
    source_path: str
    old_content_hash: str
    new_content_hash: str
    updated_at: str
    diff_summary: str


@dataclass
class SkillContent:
    """Content of a skill file."""
    file_hash: str
    content: str
    source_repo: str
    source_path: str
    source_url: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RepoSyncer:
    """Tracks and syncs updates from source repositories.

    Only syncs repositories above a certain star threshold to avoid
    wasting resources on inactive repositories.
    """

    # Default threshold for "active" repositories
    DEFAULT_ACTIVE_STARS_THRESHOLD = 100

    def __init__(self, config: Config, github_token: Optional[str] = None):
        """Initialize the repository syncer.

        Args:
            config: Configuration object
            github_token: Optional GitHub token override
        """
        self.config = config
        self.github_token = github_token or config.github_token
        self.github = Github(self.github_token) if self.github_token else None
        self.tracker = Tracker(config)
        self.searcher = GitHubSearcher(config)

    def sync_repo_metadata(self, full_name: str) -> Optional[RepoInfo]:
        """Sync metadata for a single repository.

        Args:
            full_name: Repository full name (e.g., "user/repo")

        Returns:
            Updated RepoInfo or None if failed
        """
        if not self.github:
            logger.error("GitHub token required for syncing metadata")
            return None

        try:
            repo = self.github.get_repo(full_name)

            repo_info = RepoInfo(
                name=repo.name,
                full_name=repo.full_name,
                url=repo.html_url,
                clone_url=repo.clone_url,
                default_branch=repo.default_branch or "main",
                stars=repo.stargazers_count,
                updated_at=repo.updated_at.isoformat() if repo.updated_at else "",
                language=repo.language,
            )

            logger.info(f"Synced metadata for {full_name}: {repo_info.stars} stars")
            return repo_info

        except GithubException as e:
            logger.error(f"Error syncing metadata for {full_name}: {e}")
            return None

    def check_for_skill_updates(self, source_repo: str) -> List[SkillUpdate]:
        """Check for updates to skills from a source repository.

        Args:
            source_repo: Repository full name

        Returns:
            List of skill updates detected
        """
        updates = []

        # Get existing skills from this repo
        existing_skills = self.tracker.get_processed_by_repo(source_repo)

        if not existing_skills:
            logger.debug(f"No existing skills found for {source_repo}")
            return updates

        # Sync repo metadata
        repo_info = self.sync_repo_metadata(source_repo)
        if not repo_info:
            return updates

        # Get current files from repo
        current_files = self.searcher.get_skill_files_from_repo(repo_info)

        # Create a map of source_path to existing skill
        existing_by_path = {skill.source_path: skill for skill in existing_skills}

        for file_info in current_files:
            source_path = file_info.path

            if source_path in existing_by_path:
                existing = existing_by_path[source_path]

                # Fetch current content to check hash
                raw_content = self.searcher.get_raw_file_content(repo_info, source_path)
                if not raw_content:
                    continue

                import hashlib
                current_hash = hashlib.sha256(raw_content.encode('utf-8')).hexdigest()

                if current_hash != existing.file_hash:
                    # Content has changed
                    updates.append(SkillUpdate(
                        file_hash=current_hash,
                        source_path=source_path,
                        old_content_hash=existing.file_hash,
                        new_content_hash=current_hash,
                        updated_at=file_info.updated_at or datetime.utcnow().isoformat(),
                        diff_summary=f"Content changed for {source_path}",
                    ))

        logger.info(f"Found {len(updates)} updates for {source_repo}")
        return updates

    def check_for_new_skills_in_repo(self, source_repo: str) -> List[SkillContent]:
        """Check for new skills in a repository.

        Args:
            source_repo: Repository full name

        Returns:
            List of new skill contents
        """
        new_skills = []

        # Get existing skills from this repo
        existing_skills = self.tracker.get_processed_by_repo(source_repo)
        existing_paths = {skill.source_path for skill in existing_skills}

        # Sync repo metadata
        repo_info = self.sync_repo_metadata(source_repo)
        if not repo_info:
            return new_skills

        # Get current files from repo
        current_files = self.searcher.get_skill_files_from_repo(repo_info)

        for file_info in current_files:
            if file_info.path not in existing_paths:
                # New skill file
                raw_content = self.searcher.get_raw_file_content(repo_info, file_info.path)
                if not raw_content:
                    continue

                import hashlib
                file_hash = hashlib.sha256(raw_content.encode('utf-8')).hexdigest()

                new_skills.append(SkillContent(
                    file_hash=file_hash,
                    content=raw_content,
                    source_repo=source_repo,
                    source_path=file_info.path,
                    source_url=f"{repo_info.url}/blob/{repo_info.default_branch}/{file_info.path}",
                    created_at=file_info.created_at,
                    updated_at=file_info.updated_at,
                ))

        logger.info(f"Found {len(new_skills)} new skills in {source_repo}")
        return new_skills

    def get_stale_repos(self, hours: int = 24, min_stars: int = 0) -> List[str]:
        """Get repositories that need syncing.

        Args:
            hours: Hours since last sync
            min_stars: Minimum stars threshold (0 = all repos)

        Returns:
            List of repository full names that need syncing
        """
        skills = self.tracker.get_all_processed()

        # Group by source repo
        repos: Dict[str, Dict[str, Any]] = {}
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        for skill in skills:
            if skill.source_repo not in repos:
                repos[skill.source_repo] = {
                    'last_synced': skill.repo_last_synced or skill.processed_at,
                    'repo_stars': skill.repo_stars or 0,
                }

        stale_repos = []
        for repo_name, info in repos.items():
            # Skip if below star threshold
            if min_stars > 0 and (info['repo_stars'] or 0) < min_stars:
                continue

            # Check if stale
            try:
                last_synced = datetime.fromisoformat(info['last_synced'])
                if last_synced < cutoff_time:
                    stale_repos.append(repo_name)
            except (ValueError, TypeError):
                # If we can't parse the date, consider it stale
                stale_repos.append(repo_name)

        return stale_repos

    def get_active_repos(self, threshold: int = None) -> List[str]:
        """Get active repositories (stars >= threshold).

        Args:
            threshold: Minimum stars (uses DEFAULT_ACTIVE_STARS_THRESHOLD if None)

        Returns:
            List of active repository full names
        """
        if threshold is None:
            threshold = self.DEFAULT_ACTIVE_STARS_THRESHOLD

        skills = self.tracker.get_all_processed()
        active_repos = set()

        for skill in skills:
            if skill.repo_stars and skill.repo_stars >= threshold:
                active_repos.add(skill.source_repo)

        return sorted(active_repos)

    def sync_active_repos(self, threshold: int = None) -> Dict[str, Any]:
        """Sync all active repositories (stars >= threshold).

        Args:
            threshold: Minimum stars (uses DEFAULT_ACTIVE_STARS_THRESHOLD if None)

        Returns:
            Summary dict with stats
        """
        if threshold is None:
            threshold = self.DEFAULT_ACTIVE_STARS_THRESHOLD

        active_repos = self.get_active_repos(threshold)

        logger.info(f"Syncing {len(active_repos)} active repositories (stars >= {threshold})")

        summary = {
            'repos_processed': 0,
            'updates_found': 0,
            'new_skills': 0,
            'errors': 0,
        }

        for repo_name in active_repos:
            try:
                # Check for updates
                updates = self.check_for_skill_updates(repo_name)
                summary['updates_found'] += len(updates)

                # Check for new skills
                new_skills = self.check_for_new_skills_in_repo(repo_name)
                summary['new_skills'] += len(new_skills)

                # Sync metadata
                repo_info = self.sync_repo_metadata(repo_name)
                if repo_info:
                    summary['repos_processed'] += 1

            except Exception as e:
                logger.error(f"Error syncing {repo_name}: {e}")
                summary['errors'] += 1

        logger.info(f"Sync complete: {summary}")
        return summary
