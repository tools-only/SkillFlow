"""GitHub Search API integration for finding skill repositories."""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from github import Github, GithubException, RateLimitExceededException
from github.Repository import Repository

from .config import Config


logger = logging.getLogger(__name__)


@dataclass
class RepoInfo:
    """Information about a GitHub repository."""

    name: str
    full_name: str
    url: str
    clone_url: str
    default_branch: str
    stars: int
    updated_at: str
    language: Optional[str] = None


@dataclass
class FileInfo:
    """Information about a file in a repository."""

    path: str
    name: str
    size: int
    url: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class GitHubSearcher:
    """Search GitHub for repositories containing skill files."""

    def __init__(self, config: Config):
        """Initialize GitHub searcher.

        Args:
            config: Configuration object
        """
        self.config = config
        # Pass None if no token provided (unauthenticated access with lower rate limits)
        token = config.github_token if config.github_token else None
        self.github = Github(token) if token else Github()
        self._request_count = 0
        self._last_request_time = 0
        # Cache for file timestamps to reduce API calls (repo_full_name -> file_path -> (created, updated))
        self._timestamps_cache: Dict[str, Dict[str, tuple[Optional[str], Optional[str]]]] = {}

    def _rate_limit_pause(self) -> None:
        """Pause to respect GitHub API rate limits."""
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time

        # GitHub API allows 5000 requests/hour for authenticated, 60/hour for unauthenticated
        # To be safe, we pause between requests
        if time_since_last_request < 0.5:  # Minimum 0.5 seconds between requests
            time.sleep(0.5 - time_since_last_request)

        self._last_request_time = time.time()
        self._request_count += 1

    def search_repositories(self, max_results: Optional[int] = None) -> List[RepoInfo]:
        """Search GitHub for repositories matching search terms.

        Args:
            max_results: Maximum number of results to return (default: from config)

        Returns:
            List of repository information
        """
        if max_results is None:
            max_results = self.config.github_max_results

        results: List[RepoInfo] = []
        excluded = set(self.config.excluded_repos)

        for search_term in self.config.search_terms:
            try:
                self._rate_limit_pause()

                # Build query with filters
                query = self._build_query(search_term)
                logger.info(f"Searching GitHub with query: {query}")

                # Search repositories
                repos = self.github.search_repositories(
                    query=query,
                    sort=self.config.search_sort_by,
                    order=self.config.search_order,
                )

                count = 0
                for repo in repos:
                    if count >= max_results:
                        break

                    # Skip excluded repos
                    if repo.full_name in excluded:
                        logger.debug(f"Skipping excluded repo: {repo.full_name}")
                        continue

                    # Filter by minimum stars
                    if repo.stargazers_count < self.config.github_min_stars:
                        logger.debug(f"Skipping repo with insufficient stars: {repo.full_name}")
                        continue

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

                    results.append(repo_info)
                    count += 1
                    logger.debug(f"Found repo: {repo_info.full_name} ({repo_info.stars} stars)")

            except RateLimitExceededException:
                logger.warning("GitHub API rate limit exceeded. Waiting...")
                self._wait_for_rate_limit_reset()

            except GithubException as e:
                logger.error(f"GitHub API error: {e}")
                continue

        logger.info(f"Total repositories found: {len(results)}")
        return results

    def _build_query(self, search_term: str) -> str:
        """Build GitHub search query with filters.

        Args:
            search_term: Base search term

        Returns:
            Complete GitHub search query
        """
        # Search for repositories with the search term in name or description
        # We'll filter for markdown files when fetching from each repo
        query = f'{search_term}'

        # Add language filters if specified (only first one for efficiency)
        if self.config.search_languages:
            query = f'{query} language:{self.config.search_languages[0]}'

        return query

    def _wait_for_rate_limit_reset(self) -> None:
        """Wait for GitHub API rate limit to reset."""
        # Get rate limit info
        try:
            rate_limit = self.github.get_rate_limit()
            core_rate_limit = rate_limit.core

            if core_rate_limit.remaining == 0:
                # Calculate wait time until reset
                reset_timestamp = core_rate_limit.reset.timestamp()
                current_timestamp = time.time()
                wait_seconds = max(0, reset_timestamp - current_timestamp + 1)

                logger.warning(f"Rate limit reset in {wait_seconds:.0f} seconds. Waiting...")
                time.sleep(wait_seconds)

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # Default wait time if we can't check
            time.sleep(60)

    def get_skill_files_from_repo(self, repo_info: RepoInfo) -> List[FileInfo]:
        """Get markdown skill files from a repository.

        Args:
            repo_info: Repository information

        Returns:
            List of file information for potential skill files
        """
        try:
            self._rate_limit_pause()

            repo = self.github.get_repo(repo_info.full_name)
            files: List[FileInfo] = []

            # Get all markdown files from the repository
            contents = repo.get_contents("")

            while contents:
                file_content = contents.pop(0)

                if file_content.type == "dir":
                    # Recursively get files from subdirectories
                    try:
                        contents.extend(repo.get_contents(file_content.path))
                    except GithubException as e:
                        logger.debug(f"Could not access directory {file_content.path}: {e}")
                        continue

                elif file_content.type == "file" and file_content.name.endswith(".md"):
                    # Filter out common non-skill markdown files
                    if self._is_skill_file(file_content.name):
                        # Get file timestamps
                        created_at, updated_at = self.get_file_timestamps(repo, file_content.path)
                        files.append(FileInfo(
                            path=file_content.path,
                            name=file_content.name,
                            size=file_content.size,
                            url=file_content.download_url,
                            created_at=created_at,
                            updated_at=updated_at,
                        ))

            logger.debug(f"Found {len(files)} skill files in {repo_info.full_name}")
            return files

        except GithubException as e:
            logger.error(f"Error fetching files from {repo_info.full_name}: {e}")
            return []

    def get_file_timestamps(self, repo: Repository, file_path: str) -> tuple[Optional[str], Optional[str]]:
        """Get the creation and update timestamps for a file.

        Results are cached per repository to reduce redundant API calls.

        Note: This gracefully skips timestamp fetching on rate limit errors (403)
        to avoid long backoff delays that would stall the pipeline.

        Args:
            repo: GitHub Repository object
            file_path: Path to the file in the repository

        Returns:
            Tuple of (created_at, updated_at) as ISO format strings, or (None, None)
        """
        repo_full_name = repo.full_name

        # Check cache first
        if repo_full_name in self._timestamps_cache:
            if file_path in self._timestamps_cache[repo_full_name]:
                logger.debug(f"Cache hit for {repo_full_name}:{file_path}")
                return self._timestamps_cache[repo_full_name][file_path]

        # Check rate limit before making request
        try:
            rate_limit = self.github.get_rate_limit()
            if rate_limit.core.remaining <= 10:
                logger.warning(f"Rate limit low ({rate_limit.core.remaining} remaining), skipping timestamp fetch")
                return None, None
        except Exception:
            pass  # Continue anyway if we can't check rate limit

        try:
            self._rate_limit_pause()

            # Get commits for this file with retry disabled for rate limits
            try:
                commits = repo.get_commits(path=file_path)
            except GithubException as e:
                if e.status == 403:
                    # Rate limit hit - don't retry, just skip timestamps
                    logger.debug(f"Rate limit hit while fetching timestamps for {file_path}, skipping")
                    return None, None
                raise

            if commits.totalCount == 0:
                result = (None, None)
            else:
                # Get the first commit (creation) and last commit (update)
                first_commit = commits[commits.totalCount - 1]  # Oldest
                last_commit = commits[0]  # Newest

                created_at = first_commit.commit.author.date.isoformat() if first_commit else None
                updated_at = last_commit.commit.author.date.isoformat() if last_commit else None
                result = (created_at, updated_at)

            # Cache the result
            if repo_full_name not in self._timestamps_cache:
                self._timestamps_cache[repo_full_name] = {}
            self._timestamps_cache[repo_full_name][file_path] = result

            return result

        except GithubException as e:
            if e.status == 403:
                logger.debug(f"Rate limit error for {file_path}, skipping timestamps")
            else:
                logger.debug(f"Could not get timestamps for {file_path}: {e}")
            return None, None
        except (IndexError, Exception) as e:
            logger.debug(f"Could not get timestamps for {file_path}: {e}")
            return None, None

    def _is_skill_file(self, filename: str) -> bool:
        """Check if a file is likely a skill file.

        Args:
            filename: Name of the file

        Returns:
            True if the file appears to be a skill file
        """
        # Exclude common non-skill markdown files
        excluded_files = {
            "README.md",
            "CONTRIBUTING.md",
            "LICENSE.md",
            "CHANGELOG.md",
            "CODE_OF_CONDUCT.md",
            "PULL_REQUEST_TEMPLATE.md",
            "ISSUE_TEMPLATE.md",
            "SECURITY.md",
            "AUTHORS.md",
            "HISTORY.md",
        }

        filename_upper = filename.upper()
        for excluded in excluded_files:
            if filename_upper == excluded.upper():
                return False

        return True

    def get_raw_file_content(self, repo_info: RepoInfo, file_path: str) -> Optional[str]:
        """Get raw content of a file from GitHub.

        Args:
            repo_info: Repository information
            file_path: Path to the file in the repository

        Returns:
            File content as string, or None if error
        """
        try:
            self._rate_limit_pause()

            repo = self.github.get_repo(repo_info.full_name)
            file_content = repo.get_contents(file_path, ref=repo_info.default_branch)

            if file_content.decoded_content is None:
                # Try using download_url for larger files
                import requests
                response = requests.get(file_content.download_url, timeout=30)
                response.raise_for_status()
                return response.text

            return file_content.decoded_content.decode("utf-8")

        except GithubException as e:
            logger.error(f"GitHub API error fetching {file_path}: {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"HTTP error fetching {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {file_path}: {e}")
            return None
