#!/usr/bin/env python3
"""Regenerate README from disk scan - standalone script.

This script scans all skill directories on disk and regenerates the README.md
to include ALL skills, not just those in .index.json.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class READMERegenerator:
    """Regenerate README from disk scan."""

    def __init__(self, repo_path: Path):
        """Initialize regenerator.

        Args:
            repo_path: Path to the X-Skills repository
        """
        self.repo_path = repo_path

    def regenerate(self) -> None:
        """Regenerate README from disk scan."""
        logger.info("Regenerating README from disk scan...")

        skills_by_category = {}

        # Scan all category directories (can be top-level or subcategories)
        def scan_category_dir(category_dir: Path, category_path: str) -> None:
            """Recursively scan a category directory for skills."""
            for item in category_dir.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    # Check if this is a skill directory (contains README.md or skill.md)
                    if (item / "README.md").exists() or (item / "skill.md").exists():
                        # This is a skill directory
                        readme_path = item / "README.md"
                        category = category_path
                        if readme_path.exists():
                            skill_info = self._extract_skill_info_from_readme(
                                readme_path, item.name, category
                            )
                            if skill_info:
                                if category not in skills_by_category:
                                    skills_by_category[category] = []
                                skills_by_category[category].append(skill_info)
                    else:
                        # This might be a subcategory, recurse into it
                        new_category_path = f"{category_path}/{item.name}" if category_path else item.name
                        scan_category_dir(item, new_category_path)

        for category_dir in self.repo_path.iterdir():
            if category_dir.name.startswith('.') or not category_dir.is_dir():
                continue

            scan_category_dir(category_dir, category_dir.name)

        # Build and write README
        readme_content = self._build_readme_with_tables(skills_by_category)
        readme_path = self.repo_path / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")

        total_skills = sum(len(s) for s in skills_by_category.values())
        logger.info(f"Regenerated README with {total_skills} skills from disk")

    def _extract_skill_info_from_readme(self, readme_path: Path, dir_name: str, category: str) -> Optional[Dict[str, Any]]:
        """Extract skill information from its README.md.

        Args:
            readme_path: Path to the README
            dir_name: Directory name
            category: Category name

        Returns:
            Dictionary with skill info or None
        """
        try:
            content = readme_path.read_text(encoding="utf-8")
            lines = content.split('\n')

            info = {
                'name': dir_name,
                'display_name': dir_name,
                'category': category,
                'source': 'Unknown',
                'source_url': '#',
                'tags': [],
            }

            # Extract from metadata table
            in_table = False
            for i, line in enumerate(lines):
                if '| Property | Value |' in line or '| Property |' in line:
                    in_table = True
                    continue

                if in_table:
                    if line.strip().startswith('|') and not line.strip().startswith('|---'):
                        parts = [p.strip() for p in line.split('|')[1:-1]]
                        if len(parts) >= 2:
                            key = parts[0].replace('*', '').strip().lower()
                            value = parts[1].strip()

                            if key == 'name':
                                info['display_name'] = value
                            elif key == 'source' and value != 'N/A':
                                # Extract repo name from markdown link
                                if '[' in value and '](' in value:
                                    info['source'] = value.split(']')[0].replace('[', '').strip()
                                    info['source_url'] = value.split('](')[1].replace(')', '').strip()
                    elif not line.strip():
                        break

            # Extract tags from metadata
            tags_line = next((l for l in lines if '**Tags:**' in l or 'Tags:' in l), '')
            if tags_line:
                tags = re.findall(r'`([^`]+)`', tags_line)
                info['tags'] = tags[:3]  # Limit to 3 tags for table

            return info

        except Exception as e:
            logger.debug(f"Could not read README {readme_path}: {e}")
            return None

    def _format_stars(self, stars: Optional[int]) -> str:
        """Format star count for display."""
        if stars is None or stars == 0:
            return ''
        if stars >= 1000:
            return f"⭐ {stars / 1000:.1f}k"
        return f"⭐ {stars}"

    def _build_skill_table_row(self, skill: Dict[str, Any], category: str) -> str:
        """Build a table row for a skill."""
        name = skill['display_name']
        rel_path = f"{category}/{skill['name']}"
        tags = ' '.join(f"`{t}`" for t in skill['tags']) if skill['tags'] else ''
        popularity = self._format_stars(skill.get('repo_stars'))

        return f"| [{name}]({rel_path}/) | [{skill['source']}]({skill['source_url']}) | {popularity} | {tags} |"

    def _build_readme_with_tables(self, skills_by_category: Dict[str, List[Dict[str, Any]]]) -> str:
        """Build main README content with skill tables."""
        total_skills = sum(len(skills) for skills in skills_by_category.values())

        # Count by category
        category_counts = {
            cat: len(skills)
            for cat, skills in skills_by_category.items()
        }

        # Build category overview
        category_overview = []
        for cat in sorted(skills_by_category.keys()):
            count = category_counts[cat]
            # Handle subcategories in display name
            display_parts = cat.replace("-", " ").title().split("/")
            display = " / ".join(display_parts)
            category_overview.append(f"- **{display}** ({count} skill{'s' if count != 1 else ''})")

        # Build skill tables by category
        skill_tables = []
        for category in sorted(skills_by_category.keys()):
            skills = skills_by_category[category]
            # Handle subcategories in display name
            display_parts = cat.replace("-", " ").title().split("/")
            display = " / ".join(display_parts)

            table_header = f"""
### {display} ({len(skills)} skills)

| Skill | Source | Popularity | Tags |
|-------|--------|------------|------|
"""
            table_rows = '\n'.join(self._build_skill_table_row(s, category) for s in skills)
            skill_tables.append(table_header + table_rows)

        return f"""# X-Skills

A curated collection of **{total_skills} AI-powered skills** organized into {len(skills_by_category)} categories.

## Overview

This repository contains automatically aggregated skills from various open-source projects. Each skill is designed to work with AI assistants like Claude Code to automate specific tasks.

## Categories

{chr(10).join(category_overview)}

## Skills Directory

{chr(10).join(skill_tables)}

## How Skills Are Organized

Skills are automatically categorized based on their purpose:

- **Development**: Coding, debugging, testing, and developer tools
- **Daily Assistant**: Task management, scheduling, and reminders
- **Content Creation**: Writing, editing, and content generation
- **Data Analysis**: Visualization, statistics, and data processing
- **Automation**: Workflows, scripts, and task automation
- **Research**: Academic tools, citations, and literature
- **Communication**: Email, messaging, and collaboration
- **Productivity**: Efficiency tools and optimization
- **Commercial**: E-commerce and business tools
- **Investment**: Trading, stocks, and financial analysis

## Usage

These skills can be used with AI coding assistants:

1. Browse the category folders to find relevant skills
2. Navigate to a skill's subdirectory
3. Read the skill's README.md for metadata and description
4. Use the skill's .md file content with Claude Code or similar AI assistants

## File Naming Convention

Each skill is stored in a subdirectory named: `source_name_hashprefix/`

- `source_name`: The original filename (sanitized)
- `hashprefix`: First 8 characters of the content hash (ensures uniqueness)

The hash-based naming ensures that:
- The same skill content always maps to the same directory
- Updated skills automatically replace old versions
- No duplicate directories for the same content

## Skill Index

This repository includes a `.index.json` file that tracks all skills and their locations.
This index enables:
- Incremental updates (only writing changed skills)
- Efficient change detection
- Proper handling of skill updates from source repositories

## Contributing

This repository is automatically maintained by [SkillFlow](https://github.com/tools-only/SkillFlow). Skills are aggregated from open-source repositories.

---

*Last updated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}*
*Automatically maintained by SkillFlow*
"""


if __name__ == "__main__":
    # Find the X-Skills repository
    repo_path = Path.cwd() / "skillflow_repos" / "X-Skills"

    if not repo_path.exists():
        logger.error(f"Repository not found at: {repo_path}")
        exit(1)

    regenerator = READMERegenerator(repo_path)
    regenerator.regenerate()
    logger.info(f"README regenerated at: {repo_path / 'README.md'}")
