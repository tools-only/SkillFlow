"""Main orchestration module for SkillFlow."""

import logging
import os
import sys
from pathlib import Path
from typing import List

from .config import Config
from .github_searcher import GitHubSearcher, RepoInfo, FileInfo
from .skill_fetcher import SkillFetcher, SkillContent
from .skill_analyzer import SkillAnalyzer
from .organizer import SkillOrganizer
from .tracker import Tracker, SkillInfo
from .updater import GitUpdater


def setup_logging(config: Config) -> logging.Logger:
    """Set up logging configuration.

    Args:
        config: Configuration object

    Returns:
        Configured logger
    """
    log_dir = config.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "skillflow.log"

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )

    return logging.getLogger(__name__)


class SkillFlowOrchestrator:
    """Main orchestrator for the SkillFlow workflow."""

    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize orchestrator.

        Args:
            config_path: Path to configuration file
        """
        self.config = Config(config_path)
        self.logger = setup_logging(self.config)

        # Validate required configuration
        if not self.config.github_token:
            self.logger.warning("GITHUB_TOKEN not set - GitHub API features will be limited")

        # Note: Using local rule-based analysis, no API key required

        # Initialize modules
        self.github_searcher = GitHubSearcher(self.config)
        self.skill_fetcher = SkillFetcher(self.config)
        self.skill_analyzer = SkillAnalyzer(self.config)
        self.skill_organizer = SkillOrganizer(self.config)
        self.tracker = Tracker(self.config)
        self.git_updater = GitUpdater(Path.cwd(), self.config.github_token)

    def run_update_cycle(self) -> int:
        """Run a complete update cycle.

        Returns:
            Number of new skills added
        """
        self.logger.info("Starting SkillFlow update cycle")

        try:
            # Step 1: Pull latest changes
            self.logger.info("Pulling latest changes from remote")
            self.git_updater.pull_latest()

            # Step 2: Search GitHub for repositories
            self.logger.info("Searching GitHub for skill repositories")
            repos = self.github_searcher.search_repositories()

            if not repos:
                self.logger.warning("No repositories found")
                return 0

            self.logger.info(f"Found {len(repos)} repositories")

            # Step 3: Process each repository
            new_skills_count = 0
            processed_files_count = 0

            for repo_info in repos:
                self.logger.info(f"Processing repository: {repo_info.full_name}")

                # Get skill files from repository
                skill_files = self.github_searcher.get_skill_files_from_repo(repo_info)

                if not skill_files:
                    self.logger.debug(f"No skill files found in {repo_info.full_name}")
                    continue

                self.logger.info(f"Found {len(skill_files)} skill files in {repo_info.full_name}")

                # Process each skill file
                for file_info in skill_files:
                    try:
                        result = self._process_skill_file(repo_info, file_info)
                        if result:
                            new_skills_count += 1
                        processed_files_count += 1

                    except Exception as e:
                        self.logger.error(f"Error processing skill {file_info.path}: {e}")
                        continue

            # Step 4: Commit and push changes
            if new_skills_count > 0:
                self.logger.info(f"Committing {new_skills_count} new skills")
                uncommitted = self.git_updater.get_uncommitted_changes()
                if uncommitted:
                    self.git_updater.commit_skill_updates(uncommitted)
                    self.git_updater.push_to_remote()

            # Cleanup
            self.skill_fetcher.cleanup_temp_clone()

            # Log summary
            stats = self.tracker.get_stats()
            self.logger.info(f"Update cycle complete")
            self.logger.info(f"Repositories processed: {len(repos)}")
            self.logger.info(f"Files processed: {processed_files_count}")
            self.logger.info(f"New skills added: {new_skills_count}")
            self.logger.info(f"Total skills tracked: {stats.get('total_skills', 0)}")

            return new_skills_count

        except Exception as e:
            self.logger.error(f"Error in update cycle: {e}", exc_info=True)
            return 0

    def _process_skill_file(self, repo_info: RepoInfo, file_info: FileInfo) -> bool:
        """Process a single skill file.

        Args:
            repo_info: Repository information
            file_info: File information

        Returns:
            True if skill was new and added, False otherwise
        """
        # Fetch the skill content
        skill_content = self.skill_fetcher.fetch_skill_file(repo_info, file_info)

        if not skill_content:
            return False

        # Check if already processed
        if self.tracker.is_already_processed(skill_content.file_hash):
            self.logger.debug(f"Skill already processed: {file_info.path}")
            return False

        # Analyze the skill with AI
        metadata = self.skill_analyzer.analyze_skill(
            skill_content.content,
            skill_content.source_repo
        )

        if not metadata:
            self.logger.warning(f"Could not analyze skill: {file_info.path}")
            return False

        # Organize the skill file
        source_info = {
            "source_repo": skill_content.source_repo,
            "source_path": skill_content.source_path,
            "source_url": skill_content.source_url,
            "file_hash": skill_content.file_hash,
        }

        skill_path = self.skill_organizer.organize_skill(
            metadata,
            skill_content.content,
            source_info
        )

        if not skill_path:
            return False

        # Track as processed
        skill_info = SkillInfo(
            file_hash=skill_content.file_hash,
            source_repo=skill_content.source_repo,
            source_path=skill_content.source_path,
            source_url=skill_content.source_url,
            skill_name=metadata.name,
            category=metadata.category,
            subcategory=metadata.subcategory,
            processed_at=skill_path.stat().st_mtime.isoformat(),
            local_path=str(skill_path),
        )

        self.tracker.mark_as_processed(skill_info)

        self.logger.info(f"Added new skill: {metadata.name} ({metadata.category}/{metadata.subcategory})")
        return True

    def print_stats(self) -> None:
        """Print statistics about tracked skills."""
        stats = self.tracker.get_stats()

        print("\n=== SkillFlow Statistics ===")
        print(f"Total skills tracked: {stats.get('total_skills', 0)}")
        print("\nBy category:")
        for category, count in stats.get('by_category', {}).items():
            print(f"  {category}: {count}")

        print("\nTop source repositories:")
        for repo, count in list(stats.get('top_repos', {}).items())[:5]:
            print(f"  {repo}: {count}")

        # Print category stats from organizer
        category_stats = self.skill_organizer.get_category_stats()
        if category_stats:
            print("\nCategory structure:")
            for category, subcategories in sorted(category_stats.items()):
                print(f"  {category}/")
                for subcategory, count in sorted(subcategories.items()):
                    print(f"    {subcategory}/: {count} skills")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="SkillFlow - Automated GitHub Skill Aggregator")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics and exit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without committing changes"
    )

    args = parser.parse_args()

    try:
        orchestrator = SkillFlowOrchestrator(args.config)

        if args.stats:
            orchestrator.print_stats()
            return 0

        if args.dry_run:
            logging.info("Dry run mode - changes will not be committed")

        count = orchestrator.run_update_cycle()
        return 0 if count >= 0 else 1

    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
