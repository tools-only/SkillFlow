"""Skill fetching module for cloning and extracting skill files."""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import requests
from git import Repo as GitRepo
from git import GitCommandError

from .config import Config
from .github_searcher import FileInfo, RepoInfo


logger = logging.getLogger(__name__)


@dataclass
class SkillContent:
    """Content of a skill file with metadata."""

    content: str
    file_hash: str
    source_repo: str
    source_path: str
    source_url: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SkillFetcher:
    """Fetch skill files from GitHub repositories."""

    def __init__(self, config: Config):
        """Initialize skill fetcher.

        Args:
            config: Configuration object
        """
        self.config = config
        self._temp_dir: Optional[Path] = None

    def _get_temp_dir(self) -> Path:
        """Get or create temporary directory for cloning repos.

        Returns:
            Path to temporary directory
        """
        if self._temp_dir is None or not self._temp_dir.exists():
            self._temp_dir = Path(tempfile.mkdtemp(prefix="skillflow_"))
            logger.debug(f"Created temporary directory: {self._temp_dir}")
        return self._temp_dir

    def cleanup_temp_clone(self) -> None:
        """Clean up temporary cloned repositories."""
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
                logger.debug(f"Cleaned up temporary directory: {self._temp_dir}")
            except Exception as e:
                logger.warning(f"Could not clean up temp directory: {e}")
            finally:
                self._temp_dir = None

    def fetch_skill_file(self, repo_info: RepoInfo, file_info: FileInfo) -> Optional[SkillContent]:
        """Fetch a skill file from a repository.

        Args:
            repo_info: Repository information
            file_info: File information

        Returns:
            SkillContent if successful, None otherwise
        """
        # Try to fetch via GitHub API first (faster, no clone needed)
        content = self._fetch_via_api(repo_info, file_info)
        if content:
            return content

        # Fallback to cloning the repository
        return self._fetch_via_clone(repo_info, file_info)

    def _fetch_via_api(self, repo_info: RepoInfo, file_info: FileInfo) -> Optional[SkillContent]:
        """Fetch file content via GitHub raw URL.

        Args:
            repo_info: Repository information
            file_info: File information

        Returns:
            SkillContent if successful, None otherwise
        """
        try:
            # Construct raw GitHub URL
            raw_url = f"https://raw.githubusercontent.com/{repo_info.full_name}/{repo_info.default_branch}/{file_info.path}"

            response = requests.get(raw_url, timeout=30)
            response.raise_for_status()

            content = response.text
            file_hash = self._compute_hash(content)

            logger.debug(f"Fetched via API: {file_info.path} from {repo_info.full_name}")

            return SkillContent(
                content=content,
                file_hash=file_hash,
                source_repo=repo_info.full_name,
                source_path=file_info.path,
                source_url=file_info.url,
                created_at=file_info.created_at,
                updated_at=file_info.updated_at,
            )

        except requests.RequestException as e:
            logger.debug(f"Could not fetch via API: {e}")
            return None

    def _fetch_via_clone(self, repo_info: RepoInfo, file_info: FileInfo) -> Optional[SkillContent]:
        """Fetch file content by cloning the repository.

        Args:
            repo_info: Repository information
            file_info: File information

        Returns:
            SkillContent if successful, None otherwise
        """
        temp_dir = self._get_temp_dir()
        repo_name = repo_info.full_name.replace("/", "_")
        clone_path = temp_dir / repo_name

        try:
            # Clone repository if not already cloned
            if not clone_path.exists():
                logger.debug(f"Cloning {repo_info.full_name} to {clone_path}")
                GitRepo.clone_from(
                    repo_info.clone_url,
                    clone_path,
                    depth=1,  # Shallow clone for speed
                    single_branch=True,
                    branch=repo_info.default_branch,
                )

            # Read the file
            file_path = clone_path / file_info.path
            if not file_path.exists():
                logger.warning(f"File not found in cloned repo: {file_info.path}")
                return None

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            file_hash = self._compute_hash(content)

            logger.debug(f"Fetched via clone: {file_info.path} from {repo_info.full_name}")

            return SkillContent(
                content=content,
                file_hash=file_hash,
                source_repo=repo_info.full_name,
                source_path=file_info.path,
                source_url=file_info.url,
                created_at=file_info.created_at,
                updated_at=file_info.updated_at,
            )

        except GitCommandError as e:
            logger.error(f"Git error cloning {repo_info.full_name}: {e}")
            return None
        except IOError as e:
            logger.error(f"IO error reading file {file_info.path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching via clone: {e}")
            return None

    def _compute_hash(self, content: str) -> str:
        """Compute hash of content for duplicate detection.

        Args:
            content: File content

        Returns:
            SHA256 hash as hex string
        """
        import hashlib
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def fetch_multiple_skills(
        self,
        repo_info: RepoInfo,
        file_infos: list[FileInfo],
    ) -> list[SkillContent]:
        """Fetch multiple skill files from a repository.

        Args:
            repo_info: Repository information
            file_infos: List of file information

        Returns:
            List of SkillContent objects
        """
        results: list[SkillContent] = []

        for file_info in file_infos:
            skill_content = self.fetch_skill_file(repo_info, file_info)
            if skill_content:
                results.append(skill_content)

        logger.info(f"Fetched {len(results)} skills from {repo_info.full_name}")
        return results

    def __del__(self):
        """Cleanup on destruction."""
        self.cleanup_temp_clone()
