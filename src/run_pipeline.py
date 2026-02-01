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


def run_pipeline(push_to_github: bool = True, force_rebuild: bool = False, batch_size: int = 3):
    """Run the complete pipeline with incremental processing and real-time updates.

    Args:
        push_to_github: Whether to push repos to GitHub
        force_rebuild: Whether to clear all content and rebuild from scratch
        batch_size: Number of repositories to process before pushing to GitHub (default: 3)
                   Lower values = more frequent updates, better rate limit handling
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("SkillFlow Pipeline Started (Incremental Mode)")
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

    # Initialize Repo Maintainer agent once (for incremental updates)
    agent = RepoMaintainerAgent(
        github_token=config.github_token,
        base_org="tools-only",
        repo_name="X-Skills"
    )

    repos = searcher.search_repositories(max_results=5)
    logger.info(f"Found {len(repos)} repositories")

    if not repos:
        logger.warning("No repositories found. Exiting.")
        return

    # Step 2: Fetch and analyze skills incrementally
    logger.info("\n[Step 2/4] Fetching and analyzing skills (batch mode)...")
    logger.info(f"Batch size: {batch_size} repositories per update")

    all_new_skills = []
    batch_skills = []
    repos_processed = 0
    total_skills_found = 0

    for repo_idx, repo_info in enumerate(repos, 1):
        # Check rate limit before processing each repository
        if searcher.is_rate_limit_low(threshold=50):
            remaining, limit = searcher.check_rate_limit()
            logger.warning(f"\n{'='*60}")
            logger.warning(f"Rate limit low: {remaining}/{limit} remaining")
            logger.warning(f"Stopping to preserve API quota.")
            logger.warning(f"Progress saved - next run will resume from here.")
            logger.warning(f"{'='*60}\n")
            break

        logger.info(f"Processing [{repo_idx}/{len(repos)}]: {repo_info.full_name}")

        try:
            # Check rate limit before getting files
            if searcher.is_rate_limit_low(threshold=30):
                logger.warning(f"Rate limit too low, skipping {repo_info.full_name}")
                continue

            skill_files = searcher.get_skill_files_from_repo(repo_info)
            if not skill_files:
                logger.info(f"  No skill files found in {repo_info.full_name}")
                continue

            repo_skills = []
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
                repo_skills.append(skill)
                batch_skills.append(skill)
                all_new_skills.append(skill)

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
                    local_path=None,
                    source_created_at=skill_content.created_at,
                    source_updated_at=skill_content.updated_at,
                    repo_stars=repo_info.stars,
                )
                tracker.mark_as_processed(skill_info)

            total_skills_found += len(repo_skills)
            logger.info(f"  Found {len(repo_skills)} new skills from {repo_info.full_name}")
            repos_processed += 1

            # Push batch to GitHub when batch size is reached or on last repo
            if len(batch_skills) >= 1 and (repos_processed % batch_size == 0 or repo_idx == len(repos)):
                if batch_skills:
                    logger.info(f"\n[Step 3/4] Pushing batch of {len(batch_skills)} skills to GitHub...")

                    try:
                        plan = agent.analyze_and_plan(batch_skills)
                        agent.execute_plan(plan, push=push_to_github, force_rebuild=force_rebuild)

                        for folder, skills in plan.folder_structure.items():
                            logger.info(f"  - {folder}: {len(skills)} skills")

                        logger.info(f"✓ Batch pushed: {len(batch_skills)} skills")
                        if push_to_github:
                            logger.info(f"  Repository: https://github.com/tools-only/X-Skills")

                    except Exception as e:
                        logger.error(f"Error pushing batch: {e}")
                        logger.info("Batch saved locally, will retry on next run")
                        # Continue processing - skills are tracked, will be included next time

                    batch_skills = []  # Clear batch for next iteration

        except Exception as e:
            logger.error(f"Error processing repository {repo_info.full_name}: {e}")
            logger.info("Continuing with next repository...")
            continue

    logger.info(f"\n[Step 2/4] Complete! Fetched {total_skills_found} new skills from {repos_processed} repositories")

    # Final push for any remaining skills
    if batch_skills and push_to_github:
        logger.info(f"\n[Step 3/4] Pushing final batch of {len(batch_skills)} skills...")
        try:
            plan = agent.analyze_and_plan(batch_skills)
            agent.execute_plan(plan, push=push_to_github, force_rebuild=force_rebuild)
            logger.info(f"✓ Final batch pushed: {len(batch_skills)} skills")
        except Exception as e:
            logger.error(f"Error pushing final batch: {e}")

    # Cleanup
    fetcher.cleanup_temp_clone()

    logger.info("\n" + "=" * 60)
    logger.info("Pipeline Complete!")
    logger.info("=" * 60)

    # Summary
    logger.info(f"\nSummary:")
    logger.info(f"  Repositories searched: {len(repos)}")
    logger.info(f"  Repositories processed: {repos_processed}")
    logger.info(f"  New skills found: {total_skills_found}")
    logger.info(f"  Total skills in X-Skills: {len(all_new_skills)}")
    logger.info(f"\nNote: Skills are tracked locally. Next run will only fetch new/updated skills.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SkillFlow Pipeline - Incremental Mode")
    parser.add_argument("--dry-run", action="store_true", help="Don't push to GitHub")
    parser.add_argument("--force-rebuild", action="store_true", help="Clear all content and rebuild from scratch")
    parser.add_argument("--batch-size", type=int, default=3, help="Number of repos to process before pushing (default: 3)")
    args = parser.parse_args()

    setup_logging()
    run_pipeline(push_to_github=not args.dry_run, force_rebuild=args.force_rebuild, batch_size=args.batch_size)
