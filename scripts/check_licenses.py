#!/usr/bin/env python3
"""Standalone script to check licenses for skills in X-Skills repository.

This script scans all skills in the repository and identifies any with
incompatible or missing licenses.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.license_checker import LicenseChecker, LicenseInfo
from src.config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def check_repository(repo_path: Path) -> Dict[str, LicenseInfo]:
    """Check all skills in a repository.

    Args:
        repo_path: Path to the X-Skills repository

    Returns:
        Dict mapping skill path to LicenseInfo
    """
    config = Config()
    checker = LicenseChecker(config)
    results = {}

    # Scan all category directories
    for category_dir in repo_path.iterdir():
        if category_dir.name.startswith('.') or not category_dir.is_dir():
            continue

        # Scan all skill directories in category
        for skill_dir in category_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "skill.md"
            if not skill_md.exists():
                continue

            try:
                content = skill_md.read_text(encoding="utf-8")
                license_info = checker.check_skill(content, str(skill_dir.relative_to(repo_path)))

                if license_info:
                    results[str(skill_dir.relative_to(repo_path))] = license_info

            except Exception as e:
                logger.error(f"Error checking {skill_dir}: {e}")

    return results


def print_report(license_results: Dict[str, LicenseInfo]) -> None:
    """Print a report of license check results.

    Args:
        license_results: Dict of skill path to LicenseInfo
    """
    total = len(license_results)
    compatible = sum(1 for info in license_results.values() if info.is_compatible)
    incompatible = total - compatible

    print("\n" + "=" * 60)
    print("LICENSE CHECK REPORT")
    print("=" * 60)
    print(f"\nTotal skills with license info: {total}")
    print(f"Compatible licenses: {compatible}")
    print(f"Incompatible licenses: {incompatible}")
    print("\n" + "-" * 60)

    # Group by license type
    by_type: Dict[str, List[str]] = {
        "permissive": [],
        "weak_copyleft": [],
        "strong_copyleft": [],
        "proprietary": [],
        "unknown": [],
    }

    for path, info in license_results.items():
        lic_type = info.license_type.value
        by_type[lic_type].append(f"  - {path}: {info.license_name}")

    for lic_type, paths in by_type.items():
        if paths:
            display_name = lic_type.replace("_", " ").title()
            print(f"\n{display_name} ({len(paths)} skills):")
            for path in paths[:10]:  # Show max 10 per category
                print(path)
            if len(paths) > 10:
                print(f"  ... and {len(paths) - 10} more")

    print("\n" + "=" * 60)

    # Show incompatible skills
    incompatible_skills = [
        (path, info) for path, info in license_results.items()
        if not info.is_compatible
    ]

    if incompatible_skills:
        print("\n⚠️  INCOMPATIBLE LICENSES (should be removed):")
        for path, info in incompatible_skills[:20]:  # Show max 20
            print(f"  ❌ {path}")
            print(f"     License: {info.license_name}")
            print(f"     Type: {info.license_type.value}")
        if len(incompatible_skills) > 20:
            print(f"\n  ... and {len(incompatible_skills) - 20} more incompatible skills")
        print()


def filter_repository(repo_path: Path, dry_run: bool = False) -> int:
    """Remove skills with incompatible licenses.

    Args:
        repo_path: Path to the X-Skills repository
        dry_run: If True, only print what would be done

    Returns:
        Number of skills removed
    """
    import shutil

    config = Config()
    checker = LicenseChecker(config)
    removed_count = 0

    # Scan all category directories
    for category_dir in repo_path.iterdir():
        if category_dir.name.startswith('.') or not category_dir.is_dir():
            continue

        # Scan all skill directories in category
        for skill_dir in category_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "skill.md"
            if not skill_md.exists():
                continue

            try:
                content = skill_md.read_text(encoding="utf-8")
                should_filter, reason = checker.should_filter_skill(
                    content, str(skill_dir.relative_to(repo_path))
                )

                if should_filter:
                    relative_path = skill_dir.relative_to(repo_path)
                    if dry_run:
                        print(f"Would remove: {relative_path} ({reason})")
                    else:
                        print(f"Removing: {relative_path} ({reason})")
                        shutil.rmtree(skill_dir)
                    removed_count += 1

            except Exception as e:
                logger.error(f"Error checking {skill_dir}: {e}")

    return removed_count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check licenses for skills")
    parser.add_argument("--repo", type=str, help="Path to X-Skills repository")
    parser.add_argument("--filter", action="store_true", help="Remove incompatible skills")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be filtered")

    args = parser.parse_args()

    if args.repo:
        repo_path = Path(args.repo)
    else:
        repo_path = Path.cwd() / "skillflow_repos" / "X-Skills"

    if not repo_path.exists():
        logger.error(f"Repository not found at: {repo_path}")
        sys.exit(1)

    if args.filter or args.dry_run:
        removed = filter_repository(repo_path, dry_run=args.dry_run)
        print(f"\nRemoved {removed} skills with incompatible licenses")
    else:
        results = check_repository(repo_path)
        print_report(results)
