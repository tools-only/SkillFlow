#!/usr/bin/env python3
"""Filter skills, renumber directories, and organize subcategories."""

import hashlib
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# Content validation configuration
FILTER_KEYWORDS = [
    'test', 'example', 'demo', 'template', '_map', '_template',
    'sample', 'mock'
]
MIN_CONTENT_LENGTH = 200


# Category structure with subcategories
CATEGORY_STRUCTURE = {
    "development": {
        "subcategories": ["web", "frontend", "backend", "mobile", "devops", "cloud",
                         "testing", "python", "javascript", "rust", "go", "tools",
                         "git", "architecture", "database", "security"],
        "keywords": ["development", "coding", "programming", "developer", "debug", "api"],
    },
    "automation": {
        "subcategories": ["workflow", "scripting"],
        "keywords": ["automation", "workflow", "script"],
    },
}


class SkillOrganizer:
    """Organize skills with filtering, numbering, and subcategories."""

    def __init__(self, repo_path: Path, dry_run: bool = False):
        """Initialize organizer.

        Args:
            repo_path: Path to the X-Skills repository
            dry_run: If True, only print what would be done
        """
        self.repo_path = repo_path
        self.dry_run = dry_run
        self.numbering_file = repo_path.parent / ".category_numbering.json"
        self.category_numbering: Dict[str, Dict] = {}
        self._load_numbering_state()

    def _load_numbering_state(self) -> None:
        """Load category numbering state from file."""
        if not self.numbering_file.exists():
            return

        try:
            data = json.loads(self.numbering_file.read_text())
            self.category_numbering = data
        except Exception as e:
            logger.warning(f"Could not load numbering state: {e}")

    def _save_numbering_state(self) -> None:
        """Save category numbering state to file."""
        if not self.dry_run:
            self.numbering_file.write_text(json.dumps(self.category_numbering, indent=2))

    def _get_or_assign_number(self, category: str, sanitized_name: str) -> int:
        """Get existing number or assign new number for a skill name."""
        if category not in self.category_numbering:
            self.category_numbering[category] = {
                'next_number': 1,
                'name_to_number': {}
            }

        state = self.category_numbering[category]

        if sanitized_name in state['name_to_number']:
            return state['name_to_number'][sanitized_name]

        number = state['next_number']
        state['name_to_number'][sanitized_name] = number
        state['next_number'] += 1

        self._save_numbering_state()
        return number

    def _should_filter_skill(self, skill_dir: Path) -> Tuple[bool, str]:
        """Check if a skill should be filtered out."""
        skill_md = skill_dir / "skill.md"
        if not skill_md.exists():
            return False, ""

        content = skill_md.read_text(encoding="utf-8")

        # Check 1: Filename keywords
        name_lower = skill_dir.name.lower()

        for keyword in FILTER_KEYWORDS:
            if keyword in name_lower:
                return True, f"Contains filter keyword: {keyword}"

        # Check 2: Content length
        content_stripped = content.strip()
        if len(content_stripped) < MIN_CONTENT_LENGTH:
            return True, f"Content too short: {len(content_stripped)} chars"

        # Check 3: Meaningful content
        meaningful_chars = re.sub(r'[\s#*`\-_\[\](){}]', '', content_stripped)
        if len(meaningful_chars) < MIN_CONTENT_LENGTH // 2:
            return True, f"Insufficient meaningful content"

        return False, ""

    def _determine_subcategory(self, skill_dir: Path, category: str) -> str:
        """Determine subcategory for a skill based on content."""
        if category not in CATEGORY_STRUCTURE:
            return ""

        subcategories = CATEGORY_STRUCTURE[category].get("subcategories", [])
        if not subcategories:
            return ""

        skill_md = skill_dir / "skill.md"
        if not skill_md.exists():
            return ""

        content = skill_md.read_text(encoding="utf-8").lower()
        dir_name = skill_dir.name.lower()

        # Score each subcategory
        best_subcategory = ""
        best_score = 0

        for subcategory in subcategories:
            keywords = self._get_subcategory_keywords(subcategory)
            score = sum(1 for kw in keywords if kw in content or kw in dir_name)

            if score > best_score:
                best_score = score
                best_subcategory = subcategory

        return best_subcategory if best_score > 0 else ""

    def _get_subcategory_keywords(self, subcategory: str) -> List[str]:
        """Get keywords for a subcategory."""
        keywords_map = {
            "web": ["web", "html", "css", "http", "api", "rest", "graphql"],
            "frontend": ["javascript", "typescript", "react", "vue", "angular", "ui", "css"],
            "backend": ["server", "backend", "api", "rest", "endpoint", "microservice"],
            "mobile": ["mobile", "ios", "android", "flutter", "app"],
            "devops": ["devops", "deploy", "ci/cd", "docker", "kubernetes"],
            "cloud": ["cloud", "aws", "azure", "gcp", "lambda", "serverless"],
            "testing": ["test", "testing", "pytest", "jest", "unit test"],
            "python": ["python", "pip", "django", "flask", "fastapi"],
            "javascript": ["javascript", "typescript", "node", "npm", "react", "vue"],
            "rust": ["rust", "cargo"],
            "go": ["go", "golang"],
            "tools": ["tool", "utility", "helper", "cli"],
            "git": ["git", "github", "commit"],
            "architecture": ["architecture", "design pattern"],
            "database": ["database", "sql", "mysql", "mongodb"],
            "security": ["security", "auth", "authentication"],
            "workflow": ["workflow", "automate"],
            "scripting": ["script", "bash", "shell"],
        }
        return keywords_map.get(subcategory, [subcategory])

    def _sanitize_name(self, name: str) -> str:
        """Clean a name for use in directory names."""
        name = name.strip().lower()
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'[-\s]+', '-', name)
        return name[:80] if len(name) > 80 else name

    def process_all(self) -> None:
        """Process all skills: filter, renumber, and organize subcategories."""
        logger.info(f"{'[DRY RUN] ' if self.dry_run else ''}Processing all skills...")

        filtered_count = 0
        renumbered_count = 0
        moved_to_subcategory_count = 0

        # Clear numbering state for fresh start
        self.category_numbering.clear()

        for category_dir in sorted(self.repo_path.iterdir()):
            if category_dir.name.startswith('.') or not category_dir.is_dir():
                continue

            category = category_dir.name
            logger.info(f"\nProcessing category: {category}")

            # Collect all skills in this category
            skills_to_process = []

            for skill_dir in category_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                # Check if should be filtered
                should_filter, reason = self._should_filter_skill(skill_dir)
                if should_filter:
                    filtered_count += 1
                    if self.dry_run:
                        logger.info(f"  Would filter: {skill_dir.name} ({reason})")
                    else:
                        logger.info(f"  Filtering: {skill_dir.name} ({reason})")
                        shutil.rmtree(skill_dir)
                    continue

                # Extract sanitized name from existing directory
                match = re.match(r'^(\d+-)?(.+?)_[a-f0-9]{8}$', skill_dir.name)
                if match:
                    sanitized_name = match.group(2)
                else:
                    sanitized_name = self._sanitize_name(skill_dir.name)

                # Get file hash
                skill_md = skill_dir / "skill.md"
                if skill_md.exists():
                    content = skill_md.read_text()
                    file_hash = hashlib.sha256(content.encode()).hexdigest()
                    hash_prefix = file_hash[:8]
                else:
                    hash_prefix = "unknown"

                skills_to_process.append({
                    'dir': skill_dir,
                    'sanitized_name': sanitized_name,
                    'hash_prefix': hash_prefix,
                })

            # Determine subcategories for Development category
            if category == "development":
                for skill_info in skills_to_process:
                    subcategory = self._determine_subcategory(skill_info['dir'], category)
                    skill_info['subcategory'] = subcategory

                    if subcategory:
                        moved_to_subcategory_count += 1
                        if self.dry_run:
                            logger.info(f"  Would move to subcategory {subcategory}: {skill_info['dir'].name}")
            else:
                for skill_info in skills_to_process:
                    skill_info['subcategory'] = ""

            # Sort alphabetically by sanitized name for consistent numbering
            skills_to_process.sort(key=lambda x: x['sanitized_name'])

            # Renumber and potentially move to subcategory
            for skill_info in skills_to_process:
                sanitized_name = skill_info['sanitized_name']
                hash_prefix = skill_info['hash_prefix']
                subcategory = skill_info.get('subcategory', "")
                old_dir = skill_info['dir']

                # Determine target category path
                if subcategory:
                    target_category_dir = category_dir / subcategory
                else:
                    target_category_dir = category_dir

                # Get new number
                number = self._get_or_assign_number(category, sanitized_name)
                new_name = f"{number:03d}-{sanitized_name}_{hash_prefix}"
                new_path = target_category_dir / new_name

                # Skip if already in correct place
                if old_dir == new_path:
                    continue

                renumbered_count += 1

                if self.dry_run:
                    if subcategory:
                        logger.info(f"  Would rename and move: {old_dir.name} -> {subcategory}/{new_name}")
                    else:
                        logger.info(f"  Would rename: {old_dir.name} -> {new_name}")
                else:
                    # Create subcategory directory if needed
                    if subcategory:
                        target_category_dir.mkdir(parents=True, exist_ok=True)

                    # Handle move/rename
                    if old_dir.parent != target_category_dir:
                        # Need to move to subcategory
                        shutil.move(str(old_dir), str(new_path))
                        logger.debug(f"  Moved and renamed: {old_dir.name} -> {subcategory}/{new_name}")
                    elif old_dir.name != new_name:
                        # Just rename
                        old_dir.rename(new_path)
                        logger.debug(f"  Renamed: {old_dir.name} -> {new_name}")

        # Save final numbering state
        self._save_numbering_state()

        logger.info(f"\n{'[DRY RUN] ' if self.dry_run else ''}Processing complete!")
        logger.info(f"  Filtered: {filtered_count} skills")
        logger.info(f"  Renumbered: {renumbered_count} skills")
        logger.info(f"  Moved to subcategory: {moved_to_subcategory_count} skills")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Filter, renumber, and organize skills")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be done")
    args = parser.parse_args()

    repo_path = Path.cwd() / "skillflow_repos" / "X-Skills"

    if not repo_path.exists():
        logger.error(f"Repository not found at: {repo_path}")
        exit(1)

    organizer = SkillOrganizer(repo_path, dry_run=args.dry_run)
    organizer.process_all()
