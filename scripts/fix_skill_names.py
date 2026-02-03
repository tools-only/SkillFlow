#!/usr/bin/env python3
"""Fix skill display names in X-Skills repository.

This script updates the display names in skill READMEs to use the filename
from the Original Path, ensuring consistency across all skills.
"""

import logging
import re
from pathlib import Path
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def extract_original_path_from_readme(readme_path: Path) -> Optional[str]:
    """Extract the original path from a skill's README.md.

    Args:
        readme_path: Path to the README.md

    Returns:
        Original source path or None
    """
    try:
        content = readme_path.read_text(encoding="utf-8")
        # Look for "Original Path" in the metadata table
        match = re.search(r'\*\*Original Path\*\*\s*\|\s*`([^`]+)`', content)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f"Could not read README {readme_path}: {e}")
    return None


def get_name_from_original_path(original_path: str) -> str:
    """Extract the display name from the original path filename.

    Uses the filename (without extension) from the original path,
    converting underscores and hyphens to spaces and title-casing.

    Args:
        original_path: Original file path (e.g., "skills/xxx/references/input-validation.md")

    Returns:
        Formatted display name (e.g., "Input Validation")
    """
    # Get filename from path
    filename = Path(original_path).name
    # Remove .md extension if present
    name = filename.replace(".md", "")
    # Replace underscores and hyphens with spaces
    name = name.replace("_", " ").replace("-", " ")
    # Title case
    name = name.strip().title()
    return name


def fix_skill_readme(readme_path: Path, new_name: str, correct_name: str) -> bool:
    """Update the name in a skill's README.md.

    Args:
        readme_path: Path to the README.md
        new_name: New display name (formatted)
        correct_name: The correct name to enforce

    Returns:
        True if updated
    """
    try:
        content = readme_path.read_text(encoding="utf-8")

        # Replace the title (first heading)
        lines = content.split('\n')
        if lines and lines[0].startswith('# '):
            lines[0] = f"# {new_name}"

        # Replace the Name in the metadata table
        content = '\n'.join(lines)
        content = re.sub(
            r'\|\s*\*\*Name\*\*\s*\|\s*\[?[^\n\|]*\]?\s*\|',
            f'| **Name** | {new_name} |',
            content
        )

        readme_path.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"Error updating {readme_path}: {e}")
        return False


def fix_all_skills(repo_path: Path) -> None:
    """Fix all skill names in the repository.

    Args:
        repo_path: Path to the X-Skills repository
    """
    logger.info(f"Fixing skill names in {repo_path}...")

    fixed_count = 0
    already_correct_count = 0
    error_count = 0

    # Scan all category directories
    for category_dir in repo_path.iterdir():
        if category_dir.name.startswith('.') or not category_dir.is_dir():
            continue

        # Scan all skill directories in category
        for skill_dir in category_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            readme_path = skill_dir / "README.md"
            if not readme_path.exists():
                continue

            # Get the original path
            original_path = extract_original_path_from_readme(readme_path)
            if not original_path:
                logger.debug(f"No original path found for: {skill_dir.name}")
                error_count += 1
                continue

            # Get the correct name from original path
            correct_name = get_name_from_original_path(original_path)

            # Get the current name from the title
            try:
                content = readme_path.read_text(encoding="utf-8")
                first_line = content.split('\n')[0]
                if first_line.startswith('# '):
                    current_name = first_line[2:].strip()
                else:
                    current_name = None
            except:
                current_name = None

            # Check if current name matches the correct name (case-insensitive)
            if current_name and current_name.lower() == correct_name.lower():
                already_correct_count += 1
                continue

            # Fix the name
            if fix_skill_readme(readme_path, correct_name, correct_name):
                fixed_count += 1
                logger.debug(f"Fixed: {skill_dir.name} -> {correct_name}")
            else:
                error_count += 1

    logger.info(f"\nSummary:")
    logger.info(f"  Fixed: {fixed_count}")
    logger.info(f"  Already correct: {already_correct_count}")
    logger.info(f"  Errors: {error_count}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        repo_path = Path(sys.argv[1])
    else:
        repo_path = Path.cwd() / "skillflow_repos" / "X-Skills"

    if not repo_path.exists():
        logger.error(f"Repository not found at: {repo_path}")
        sys.exit(1)

    fix_all_skills(repo_path)
