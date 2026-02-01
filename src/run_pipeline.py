#!/usr/bin/env python3
"""Integrated pipeline: Fetch skills + Repo Maintainer agent.

This script:
1. Runs SkillFlow to search GitHub and fetch skills
2. Passes new skills to Repo Maintainer agent
3. Agent organizes into "X Skills" repos and pushes to GitHub
"""

import logging
import sys
from pathlib import Path

from src.config import Config
from src.github_searcher import GitHubSearcher
from src.skill_fetcher import SkillFetcher
from src.skill_analyzer import SkillAnalyzer
from src.tracker import Tracker, SkillInfo
from src.repo_maintainer import RepoMaintainerAgent, Skill, process_skills


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("logs/skillflow.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_pipeline(push_to_github: bool = True, force_rebuild: bool = False):
    """Run the complete pipeline.

    Args:
        push_to_github: Whether to push repos to GitHub
        force_rebuild: Whether to clear all content and rebuild from scratch
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("SkillFlow Pipeline Started")
    logger.info("=" * 60)

    if force_rebuild:
        logger.warning("Force rebuild enabled - all existing content will be cleared!")

    config = Config()

    # Step 1: Search and fetch skills
    logger.info("\n[Step 1/4] Searching GitHub for skills...")
    searcher = GitHubSearcher(config)
    fetcher = SkillFetcher(config)
    tracker = Tracker(config)
    analyzer = SkillAnalyzer(config)

    repos = searcher.search_repositories(max_results=5)
    logger.info(f"Found {len(repos)} repositories")

    if not repos:
        logger.warning("No repositories found. Exiting.")
        return

    # Step 2: Fetch and analyze skills
    logger.info("\n[Step 2/4] Fetching and analyzing skills...")
    new_skills = []

    for repo_info in repos:
        logger.info(f"Processing: {repo_info.full_name}")

        skill_files = searcher.get_skill_files_from_repo(repo_info)
        if not skill_files:
            continue

        for file_info in skill_files:  # Process all skill files from repository
            skill_content = fetcher.fetch_skill_file(repo_info, file_info)
            if not skill_content:
                continue

            # Check if already processed (skip only on incremental builds)
            if not force_rebuild and tracker.is_already_processed(skill_content.file_hash):
                continue

            # Analyze skill
            metadata = analyzer.analyze_skill(skill_content.content, skill_content.source_repo)
            if not metadata:
                continue

            # Create Skill object for repo maintainer
            skill = Skill(
                name=metadata.name,
                content=skill_content.content,
                source_repo=skill_content.source_repo,
                source_path=skill_content.source_path,
                source_url=skill_content.source_url,
                file_hash=skill_content.file_hash,
                metadata={
                    "category": metadata.category,
                    "subcategory": metadata.subcategory,
                    "tags": metadata.tags,
                    "primary_purpose": metadata.primary_purpose,
                },
                created_at=skill_content.created_at,
                updated_at=skill_content.updated_at,
                repo_stars=repo_info.stars,
            )
            new_skills.append(skill)

            # Track as processed
            from datetime import datetime
            skill_info = SkillInfo(
                file_hash=skill_content.file_hash,
                source_repo=skill_content.source_repo,
                source_path=skill_content.source_path,
                source_url=skill_content.source_url,
                skill_name=metadata.name,
                category=metadata.category,
                subcategory=metadata.subcategory,
                processed_at=datetime.utcnow().isoformat(),
                local_path=None,  # Will be set by repo maintainer
                source_created_at=skill_content.created_at,
                source_updated_at=skill_content.updated_at,
                repo_stars=repo_info.stars,
            )
            tracker.mark_as_processed(skill_info)

    logger.info(f"Fetched {len(new_skills)} new skills")

    if not new_skills:
        logger.info("No new skills to process. Pipeline complete.")
        return

    # Step 3: Repo Maintainer organizes skills into X-Skills repo
    logger.info("\n[Step 3/4] Repo Maintainer organizing skills into X-Skills...")
    agent = RepoMaintainerAgent(
        github_token=config.github_token,
        base_org="tools-only",
        repo_name="X-Skills"
    )

    plan = agent.analyze_and_plan(new_skills)
    logger.info(f"Organizing {len(plan.skills)} skills into {len(plan.folder_structure)} categories")

    for folder, skills in plan.folder_structure.items():
        logger.info(f"  - {folder}: {len(skills)} skills")

    # Step 4: Execute and push to X-Skills repo
    logger.info("\n[Step 4/4] Executing plan...")
    repo_path = agent.execute_plan(plan, push=push_to_github, force_rebuild=force_rebuild)
    skill_count = len(plan.skills)
    folder_count = len(plan.folder_structure)

    if push_to_github:
        logger.info(f"✓ X-Skills: {skill_count} skills in {folder_count} categories")
        logger.info(f"  Repository: https://github.com/tools-only/X-Skills")
    else:
        logger.info(f"✓ X-Skills: {skill_count} skills (dry run, not pushed)")

    # Cleanup
    fetcher.cleanup_temp_clone()

    logger.info("\n" + "=" * 60)
    logger.info("Pipeline Complete!")
    logger.info("=" * 60)

    # Summary
    logger.info(f"\nSummary:")
    logger.info(f"  Repositories searched: {len(repos)}")
    logger.info(f"  New skills found: {len(new_skills)}")
    logger.info(f"  Skills added to X-Skills repo: {len(plan.skills)}")
    logger.info(f"  Categories in X-Skills: {len(plan.folder_structure)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SkillFlow Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Don't push to GitHub")
    parser.add_argument("--force-rebuild", action="store_true", help="Clear all content and rebuild from scratch")
    args = parser.parse_args()

    setup_logging()
    run_pipeline(push_to_github=not args.dry_run, force_rebuild=args.force_rebuild)
