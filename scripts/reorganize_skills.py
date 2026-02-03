#!/usr/bin/env python3
"""Reorganize existing skill directories with meaningful names.

This script scans existing skill directories and renames them using
the improved naming logic that generates meaningful names from metadata
instead of generic "skill" names.
"""

import sys
import logging
import json
import hashlib
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.repo_maintainer import RepoMaintainerAgent, Skill

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_yaml_frontmatter(content: str) -> Tuple[dict, str]:
    """Parse YAML frontmatter from content.

    Returns:
        Tuple of (metadata_dict, content_without_frontmatter)
    """
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        import yaml
        metadata = yaml.safe_load(parts[1]) or {}
        content_without = parts[2]
        return metadata, content_without
    except Exception as e:
        logger.warning(f"Failed to parse YAML: {e}")
        return {}, content


def compute_file_hash(content: str) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def read_skill_file(skill_dir: Path) -> Optional[dict]:
    """Read skill.md file and extract metadata.

    Returns:
        Dictionary with skill data or None if not found
    """
    skill_md = skill_dir / "skill.md"
    if not skill_md.exists():
        return None

    content = skill_md.read_text(encoding='utf-8')
    metadata, _ = parse_yaml_frontmatter(content)

    return {
        'content': content,
        'metadata': metadata,
        'file_hash': compute_file_hash(content),
    }


def get_current_numbering(dirname: str) -> int:
    """Extract current numbering from directory name."""
    match = re.match(r'(\d+)-', dirname)
    if match:
        return int(match.group(1))
    return 0


def generate_new_dirname(
    old_dirname: str,
    skill_data: dict,
    category: str,
    agent: RepoMaintainerAgent
) -> str:
    """Generate new directory name using the improved naming logic.

    Returns:
        New directory name
    """
    # Create a temporary Skill object to use the naming logic
    metadata = skill_data['metadata']
    content = skill_data['content']

    # Get the current number
    current_number = get_current_numbering(old_dirname)

    # Create Skill object
    skill = Skill(
        name=metadata.get('name', old_dirname.split('_')[0]),
        content=content,
        source_repo=metadata.get('source_repo', 'unknown'),
        source_path=metadata.get('original_path', old_dirname),
        source_url=metadata.get('source', ''),
        file_hash=skill_data['file_hash'],
        metadata=metadata,
    )

    # Use the agent's method to generate the base name
    base_name = agent._generate_meaningful_name(skill, category)

    # Remove the "-skill" suffix if present for cleaner directory names
    if base_name.endswith('-skill'):
        base_name = base_name[:-6]

    # Sanitize the base name
    base_name = agent._clean_name(base_name)

    # Get hash prefix
    hash_prefix = skill_data['file_hash'][:8]

    # Preserve the numbering if it existed
    if current_number > 0:
        return f"{current_number:03d}-{base_name}_{hash_prefix}"
    else:
        return f"{base_name}_{hash_prefix}"


def reorganize_category(
    category_dir: Path,
    agent: RepoMaintainerAgent,
    dry_run: bool = False
) -> List[dict]:
    """Reorganize all skill directories in a category.

    Returns:
        List of rename operations performed
    """
    category = category_dir.name
    operations = []

    logger.info(f"Processing category: {category}")

    # Get all skill directories
    skill_dirs = [d for d in category_dir.iterdir()
                  if d.is_dir() and not d.name.startswith('.')]

    for skill_dir in skill_dirs:
        old_dirname = skill_dir.name

        # Skip if already has meaningful name (not "skill")
        # Check if it's a generic "XXX-skill_hash" pattern
        if '-skill_' in old_dirname:
            # This might be a generic name, check if we should rename
            pass

        # Read skill data
        skill_data = read_skill_file(skill_dir)
        if not skill_data:
            logger.warning(f"  No skill.md found in {old_dirname}, skipping")
            continue

        # Generate new name
        new_dirname = generate_new_dirname(
            old_dirname,
            skill_data,
            category,
            agent
        )

        # Check if rename is needed
        if new_dirname == old_dirname:
            logger.debug(f"  {old_dirname}: no change needed")
            continue

        new_path = category_dir / new_dirname

        # Check if target already exists
        if new_path.exists():
            logger.warning(f"  Target {new_dirname} already exists, skipping rename")
            operations.append({
                'old': old_dirname,
                'new': new_dirname,
                'status': 'skipped-target-exists',
                'category': category,
            })
            continue

        # Perform rename
        if dry_run:
            logger.info(f"  Would rename: {old_dirname} -> {new_dirname}")
            operations.append({
                'old': old_dirname,
                'new': new_dirname,
                'status': 'dry-run',
                'category': category,
            })
        else:
            logger.info(f"  Renaming: {old_dirname} -> {new_dirname}")
            try:
                shutil.move(str(skill_dir), str(new_path))
                operations.append({
                    'old': old_dirname,
                    'new': new_dirname,
                    'status': 'success',
                    'category': category,
                })
            except Exception as e:
                logger.error(f"  Failed to rename: {e}")
                operations.append({
                    'old': old_dirname,
                    'new': new_dirname,
                    'status': f'error: {e}',
                    'category': category,
                })

    return operations


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Reorganize skill directories with meaningful names"
    )
    parser.add_argument(
        "--repo-path",
        default="/root/SkillFlow/skillflow_repos/X-Skills",
        help="Path to X-Skills repository"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--category",
        help="Only process specific category (default: all)"
    )

    args = parser.parse_args()

    repo_path = Path(args.repo_path)

    if not repo_path.exists():
        logger.error(f"Repository path does not exist: {repo_path}")
        return 1

    # Create agent instance
    agent = RepoMaintainerAgent()

    # Backup current state
    if not args.dry_run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = repo_path / f".index.json.backup.{timestamp}"
        index_file = repo_path / ".index.json"
        if index_file.exists():
            shutil.copy(index_file, backup_file)
            logger.info(f"Backed up index to: {backup_file}")

    # Get categories to process
    if args.category:
        category_dirs = [repo_path / args.category]
        if not category_dirs[0].exists():
            logger.error(f"Category not found: {args.category}")
            return 1
    else:
        category_dirs = [d for d in repo_path.iterdir()
                         if d.is_dir() and not d.name.startswith('.')]

    # Process each category
    all_operations = []
    for category_dir in sorted(category_dirs):
        ops = reorganize_category(category_dir, agent, args.dry_run)
        all_operations.extend(ops)

    # Summary
    logger.info("=" * 60)
    logger.info("Summary:")
    logger.info(f"  Total directories processed: {len(all_operations)}")

    by_status = {}
    for op in all_operations:
        status = op['status']
        by_status[status] = by_status.get(status, 0) + 1

    for status, count in sorted(by_status.items()):
        logger.info(f"  {status}: {count}")

    if args.dry_run:
        logger.info("")
        logger.info("This was a dry run. Run without --dry-run to apply changes.")
    else:
        # Rebuild index after reorganization
        logger.info("")
        logger.info("Rebuilding index from reorganized directories...")
        agent.rebuild_index_from_disk(repo_path)

        # Regenerate README
        logger.info("Regenerating README.md...")
        from src.repo_maintainer import RepoPlan
        empty_plan = RepoPlan(
            repo_name="X-Skills",
            category="all",
            description="Collection of AI-powered skills",
            skills=[],
            create_new=False,
            folder_structure={}
        )
        agent._generate_readme(repo_path, plan=empty_plan)

        logger.info("")
        logger.info("Reorganization complete!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
