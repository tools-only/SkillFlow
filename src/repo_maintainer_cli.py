#!/usr/bin/env python3
"""CLI wrapper for the Repo Maintainer functionality.

This module provides a command-line interface for the repo maintainer agent,
which can be used either standalone or as a reference for the Claude Code subagent.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import from src package when run as module
try:
    from src.repo_maintainer import RepoMaintainerAgent, Skill, process_skills
    from src.config import Config
    from src.repo_syncer import RepoSyncer
except ImportError:
    from repo_maintainer import RepoMaintainerAgent, Skill, process_skills
    from config import Config
    from repo_syncer import RepoSyncer


logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Setup logging configuration.

    Args:
        verbose: Enable debug logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def load_skills_from_json(json_file: str) -> List[Dict[str, Any]]:
    """Load skill data from a JSON file.

    Args:
        json_file: Path to JSON file containing skills array

    Returns:
        List of skill dictionaries
    """
    path = Path(json_file)
    if not path.exists():
        logger.error(f"Skills file not found: {json_file}")
        sys.exit(1)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "skills" in data:
            return data["skills"]
        else:
            logger.error(f"Invalid JSON format. Expected list or object with 'skills' key.")
            sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        sys.exit(1)


def create_skill_from_markdown(md_file: str) -> Dict[str, Any]:
    """Create a skill dictionary from a markdown file.

    Args:
        md_file: Path to markdown skill file

    Returns:
        Skill dictionary
    """
    path = Path(md_file)
    if not path.exists():
        logger.error(f"File not found: {md_file}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8")

    # Try to extract YAML frontmatter
    metadata = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                metadata = yaml.safe_load(parts[1]) or {}
                # Keep the content after frontmatter
                # But for skills, we usually want to keep everything
            except ImportError:
                logger.warning("pyyaml not installed, skipping metadata extraction")
            except Exception as e:
                logger.debug(f"Could not parse YAML: {e}")

    # Generate simple hash for the content
    import hashlib
    file_hash = hashlib.sha256(content.encode()).hexdigest()

    return {
        "name": metadata.get("name", path.stem),
        "content": content,
        "source_repo": metadata.get("source_repo", "local"),
        "source_path": str(path),
        "source_url": metadata.get("source", ""),
        "file_hash": file_hash,
        "metadata": metadata,
        "created_at": metadata.get("created_at"),
        "updated_at": metadata.get("updated_at"),
    }


def cmd_process(args):
    """Handle the 'process' command.

    Args:
        args: Parsed arguments
    """
    # Load skills
    skills_data = []

    if args.json_input:
        # Load from JSON file
        for json_file in args.skills:
            skills_data.extend(load_skills_from_json(json_file))
    else:
        # Load from markdown files
        for md_file in args.skills:
            if md_file.endswith(".json"):
                logger.warning(f"Skipping JSON file {md_file} (use --json-input flag)")
                continue
            skills_data.append(create_skill_from_markdown(md_file))

    if not skills_data:
        logger.error("No skills to process")
        sys.exit(1)

    logger.info(f"Processing {len(skills_data)} skill(s)")

    # Process skills
    try:
        repo_path = process_skills(
            skills_data=skills_data,
            github_token=None,  # Will read from GITHUB_TOKEN env var
            org=args.org,
            repo_name=args.repo,
            push=not args.dry_run,
            force_rebuild=args.force_rebuild,
        )

        logger.info(f"✓ Skills organized into: {repo_path}")

        if args.dry_run:
            logger.info("(Dry run - not pushed to GitHub)")
        else:
            logger.info(f"Repository: https://github.com/{args.org}/{args.repo}")

    except Exception as e:
        logger.error(f"Error processing skills: {e}", exc_info=args.verbose)
        sys.exit(1)


def cmd_sync(args):
    """Handle the 'sync-repos' command.

    Args:
        args: Parsed arguments
    """
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
        elif args.active_only:
            threshold = args.threshold or 100
            logger.info(f"Syncing active repositories (stars >= {threshold})")
        else:
            threshold = args.threshold or 100
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


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Repo Maintainer - Organize AI skills into categorized repositories"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Process command
    process_parser = subparsers.add_parser(
        "process",
        help="Process skill files and organize them into repository"
    )
    process_parser.add_argument(
        "skills",
        nargs="+",
        help="Skill files (.md) or JSON file containing skills array",
    )
    process_parser.add_argument(
        "--org",
        default="tools-only",
        help="GitHub organization or username (default: tools-only)",
    )
    process_parser.add_argument(
        "--repo",
        default="X-Skills",
        help="Target repository name (default: X-Skills)",
    )
    process_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't push to GitHub",
    )
    process_parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Clear all content and rebuild from scratch",
    )
    process_parser.add_argument(
        "--json-input",
        action="store_true",
        help="Treat input as JSON file containing skills array",
    )
    process_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    # Sync-repos command
    sync_parser = subparsers.add_parser(
        "sync-repos",
        help="Sync repository updates from source repositories"
    )
    sync_parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only sync active repositories (stars >= 100)"
    )
    sync_parser.add_argument(
        "--all",
        action="store_true",
        help="Sync all repositories regardless of star count"
    )
    sync_parser.add_argument(
        "--threshold",
        type=int,
        default=100,
        help="Star threshold for active repos (default: 100)"
    )
    sync_parser.add_argument(
        "--repo",
        type=str,
        help="Sync a specific repository (e.g., user/repo)"
    )
    sync_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without making changes"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.command:
        # Default to old behavior for backward compatibility
        # Check if first arg looks like a file
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
            # Re-parse with process command
            sys.argv.insert(1, 'process')
            args = parser.parse_args()
            setup_logging(args.verbose)

    if args.command == "process":
        cmd_process(args)
    elif args.command == "sync-repos":
        cmd_sync(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
