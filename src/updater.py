"""Git update module for handling repository updates."""

import logging
from pathlib import Path
from typing import List, Optional

from git import Repo as GitRepo, GitCommandError
from github import Github, GithubException


logger = logging.getLogger(__name__)


class GitUpdater:
    """Handle Git operations for the SkillFlow repository."""

    def __init__(self, repo_path: Path, github_token: Optional[str] = None):
        """Initialize Git updater.

        Args:
            repo_path: Path to the SkillFlow repository
            github_token: Optional GitHub token for authentication
        """
        self.repo_path = repo_path
        self.github_token = github_token

        try:
            self.repo = GitRepo(repo_path)
        except Exception as e:
            logger.error(f"Could not open repository at {repo_path}: {e}")
            self.repo = None

    def commit_skill_updates(self, skill_paths: List[str], message: Optional[str] = None) -> bool:
        """Commit new or updated skill files.

        Args:
            skill_paths: List of skill file paths to commit
            message: Optional commit message (auto-generated if not provided)

        Returns:
            True if commit successful, False otherwise
        """
        if not self.repo:
            logger.error("Repository not initialized")
            return False

        if not skill_paths:
            logger.info("No skills to commit")
            return True

        try:
            # Add files to staging
            for skill_path in skill_paths:
                try:
                    self.repo.git.add(skill_path)
                    logger.debug(f"Staged: {skill_path}")
                except GitCommandError as e:
                    logger.warning(f"Could not stage {skill_path}: {e}")

            # Check if there's anything to commit
            if self.repo.is_dirty() or self.repo.untracked_files:
                # Generate commit message if not provided
                if message is None:
                    message = self._generate_commit_message(skill_paths)

                # Commit changes
                self.repo.index.commit(message)
                logger.info(f"Committed {len(skill_paths)} skill files")
                return True
            else:
                logger.info("No changes to commit")
                return True

        except GitCommandError as e:
            logger.error(f"Git commit error: {e}")
            return False

    def _generate_commit_message(self, skill_paths: List[str]) -> str:
        """Generate a structured commit message.

        Args:
            skill_paths: List of committed file paths

        Returns:
            Formatted commit message
        """
        count = len(skill_paths)

        # Count by category from paths
        category_counts = {}
        for path in skill_paths:
            parts = Path(path).parts
            if len(parts) >= 2 and parts[0] == "skills":
                category = parts[1]
                category_counts[category] = category_counts.get(category, 0) + 1

        # Build message
        message_lines = [
            f"Add {count} new skill(s)",
            "",
            "Categories:",
        ]

        for category, count in sorted(category_counts.items()):
            message_lines.append(f"  - {category}: {count}")

        message_lines.append("")
        message_lines.append("Automated update by SkillFlow")

        return "\n".join(message_lines)

    def push_to_remote(self, remote_name: str = "origin", branch: str = "main") -> bool:
        """Push commits to remote repository.

        Args:
            remote_name: Name of the remote (default: "origin")
            branch: Branch to push (default: "main")

        Returns:
            True if push successful, False otherwise
        """
        if not self.repo:
            logger.error("Repository not initialized")
            return False

        try:
            # Get the remote
            try:
                remote = self.repo.remote(remote_name)
            except ValueError:
                logger.error(f"Remote '{remote_name}' not found")
                return False

            # Push to remote
            push_info = remote.push(branch)

            # Check if push was successful
            for info in push_info:
                if info.flags & info.ERROR:
                    logger.error(f"Push error: {info.name}")
                    return False
                elif info.flags & info.REJECTED:
                    logger.warning(f"Push rejected: {info.name}")
                    return False
                else:
                    logger.info(f"Pushed to {remote_name}/{branch}: {info.name}")
                    return True

            return True

        except GitCommandError as e:
            logger.error(f"Git push error: {e}")
            return False

    def pull_latest(self, remote_name: str = "origin", branch: str = "main") -> bool:
        """Pull latest changes from remote.

        Args:
            remote_name: Name of the remote (default: "origin")
            branch: Branch to pull (default: "main")

        Returns:
            True if pull successful, False otherwise
        """
        if not self.repo:
            logger.error("Repository not initialized")
            return False

        try:
            # Get the remote
            try:
                remote = self.repo.remote(remote_name)
            except ValueError:
                logger.warning(f"Remote '{remote_name}' not found, skipping pull")
                return True

            # Pull from remote
            pull_info = remote.pull(branch)

            # Check if pull was successful
            for info in pull_info:
                if info.flags & info.ERROR:
                    logger.error(f"Pull error: {info.name}")
                    return False
                else:
                    logger.info(f"Pulled from {remote_name}/{branch}: {info.name}")
                    return True

            return True

        except GitCommandError as e:
            logger.error(f"Git pull error: {e}")
            return False

    def get_current_branch(self) -> str:
        """Get the current branch name.

        Returns:
            Current branch name
        """
        if not self.repo:
            return "unknown"

        try:
            return self.repo.active_branch.name
        except Exception as e:
            logger.error(f"Error getting branch: {e}")
            return "unknown"

    def get_uncommitted_changes(self) -> List[str]:
        """Get list of uncommitted changed files.

        Returns:
            List of changed file paths
        """
        if not self.repo:
            return []

        try:
            # Get untracked files
            untracked = self.repo.untracked_files

            # Get modified files
            modified = [item.a_path for item in self.repo.index.diff(None)]

            # Get staged but uncommitted files
            staged = [item.a_path for item in self.repo.index.diff("HEAD")]

            return list(set(untracked + modified + staged))

        except GitCommandError as e:
            logger.error(f"Error getting uncommitted changes: {e}")
            return []

    def create_github_issue(self, title: str, body: str, github_token: str) -> bool:
        """Create a GitHub issue for errors or notifications.

        Args:
            title: Issue title
            body: Issue body
            github_token: GitHub token for authentication

        Returns:
            True if issue created successfully, False otherwise
        """
        try:
            # Get repository info from git remote
            remote_url = list(self.repo.remote("origin").urls)[0]

            # Parse GitHub owner/repo from URL
            if "github.com" in remote_url:
                # Handle both https and ssh URLs
                if remote_url.startswith("git@"):
                    # git@github.com:owner/repo.git
                    repo_name = remote_url.split(":")[-1].replace(".git", "")
                else:
                    # https://github.com/owner/repo.git
                    repo_name = remote_url.split("github.com/")[-1].replace(".git", "")

                # Create issue using GitHub API
                g = Github(github_token)
                repo = g.get_repo(repo_name)
                repo.create_issue(title=title, body=body)

                logger.info(f"Created GitHub issue: {title}")
                return True

            else:
                logger.warning("Not a GitHub repository, cannot create issue")
                return False

        except GithubException as e:
            logger.error(f"GitHub API error creating issue: {e}")
            return False
        except Exception as e:
            logger.error(f"Error creating GitHub issue: {e}")
            return False
