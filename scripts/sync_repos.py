#!/usr/bin/env python3
"""Repository Sync Script - Syncs updates from source repositories.

This script can be run manually or via cron to sync repository updates.
By default, it only syncs active repositories (stars > 100) to save resources.

Usage:
    python scripts/sync_repos.py                    # Sync active repos only
    python scripts/sync_repos.py --all             # Sync all repos
    python scripts/sync_repos.py --threshold 50    # Use custom threshold
    python scripts/sync_repos.py --repo user/repo  # Sync specific repo

Cron (hourly sync of active repos):
    0 * * * * cd /root/SkillFlow && .venv/bin/python scripts/sync_repos.py --active-only >> logs/sync.log 2>&1
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.repo_syncer import RepoSyncer


def setup_logging(verbose: bool = False):
    """Setup logging configuration.

    Args:
        verbose: Enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync repository updates from source repositories"
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only sync active repositories (stars >= 100, default behavior)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync all repositories regardless of star count"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=100,
        help="Star threshold for active repos (default: 100)"
    )
    parser.add_argument(
        "--repo",
        type=str,
        help="Sync a specific repository (e.g., user/repo)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without making changes"
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    config = Config()
    syncer = RepoSyncer(config)

    if args.repo:
        # Sync specific repository
        logger.info(f"Syncing specific repository: {args.repo}")

        if args.dry_run:
            logger.info("DRY RUN - Would sync:")
            logger.info(f"  Repository: {args.repo}")
            return

        repo_info = syncer.sync_repo_metadata(args.repo)
        if repo_info:
            updates = syncer.check_for_skill_updates(args.repo)
            new_skills = syncer.check_for_new_skills_in_repo(args.repo)

            logger.info(f"Repository: {args.repo}")
            logger.info(f"  Stars: {repo_info.stars}")
            logger.info(f"  Updated: {repo_info.updated_at}")
            logger.info(f"  Skill updates found: {len(updates)}")
            logger.info(f"  New skills found: {len(new_skills)}")
        else:
            logger.error(f"Failed to sync {args.repo}")
            sys.exit(1)

    else:
        # Sync multiple repositories
        if args.all:
            threshold = 0
            logger.info("Syncing ALL repositories")
        else:
            threshold = args.threshold
            logger.info(f"Syncing active repositories (stars >= {threshold})")

        active_repos = syncer.get_active_repos(threshold)
        logger.info(f"Found {len(active_repos)} repositories to sync")

        if args.dry_run:
            logger.info("DRY RUN - Would sync:")
            for repo in active_repos[:10]:
                logger.info(f"  - {repo}")
            if len(active_repos) > 10:
                logger.info(f"  ... and {len(active_repos) - 10} more")
            return

        summary = syncer.sync_active_repos(threshold)

        logger.info("\n" + "=" * 50)
        logger.info("Sync Summary")
        logger.info("=" * 50)
        logger.info(f"Repositories processed: {summary['repos_processed']}")
        logger.info(f"Skill updates found: {summary['updates_found']}")
        logger.info(f"New skills found: {summary['new_skills']}")
        logger.info(f"Errors: {summary['errors']}")


if __name__ == "__main__":
    main()
