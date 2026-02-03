#!/usr/bin/env python3
"""Fix skill display names in X-Skills repository.

This script updates the display names in skill READMEs to use the original
filename instead of template variables extracted from content.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional

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


def sanitize_display_name(filename: str) -> str:
    """Convert filename to a nice display name.

    Args:
        filename: Filename (with or without extension)

    Returns:
        Formatted display name
    """
    # Remove .md extension if present
    name = filename.replace(".md", "")
    # Replace underscores and hyphens with spaces
    name = name.replace("_", " ").replace("-", " ")
    # Title case
    name = name.strip().title()
    return name


def is_template_variable(name: str) -> bool:
    """Check if a name looks like a template variable.

    Args:
        name: Name to check

    Returns:
        True if it looks like a template variable
    """
    name = name.strip()
    return name.startswith("{") or name.endswith("}") or "{" in name


def fix_skill_readme(readme_path: Path, new_name: str) -> bool:
    """Update the name in a skill's README.md.

    Args:
        readme_path: Path to the README.md
        new_name: New display name

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
    skipped_count = 0
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

            # Get the original path
            original_path = extract_original_path_from_readme(readme_path)
            if not original_path:
                if current_name and is_template_variable(current_name):
                    logger.warning(f"Could not find original path for: {skill_dir.name}")
                skipped_count += 1
                continue

            # Extract filename from original path
            original_filename = Path(original_path).name
            new_name = sanitize_display_name(original_filename)

            # Check if current name is a template variable or differs from filename
            if current_name and not is_template_variable(current_name):
                # Name looks good, skip
                skipped_count += 1
                continue

            # Fix the name
            if fix_skill_readme(readme_path, new_name):
                fixed_count += 1
                logger.info(f"Fixed: {skill_dir.name} -> {new_name}")
            else:
                error_count += 1

    logger.info(f"\nSummary:")
    logger.info(f"  Fixed: {fixed_count}")
    logger.info(f"  Skipped: {skipped_count}")
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
