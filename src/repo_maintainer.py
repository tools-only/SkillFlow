"""Repo Maintainer Agent - Manages and organizes skills into a single GitHub repository.

This agent manages the X-Skills repository with category-based folder organization.
"""

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from git import Repo as GitRepo, GitCommandError
from github import Github


logger = logging.getLogger(__name__)


@dataclass
class CategoryNumbering:
    """Track numbering state for a category."""
    category: str
    next_number: int
    name_to_number: Dict[str, int]  # Maps sanitized name to assigned number


@dataclass
class Skill:
    """A skill to be organized."""
    name: str
    content: str
    source_repo: str
    source_path: str
    source_url: str
    file_hash: str
    metadata: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    repo_stars: Optional[int] = None
    repo_forks: Optional[int] = None
    repo_updated: Optional[str] = None


@dataclass
class SkillIndexEntry:
    """An entry in the skill index file."""
    file_hash: str
    source_path: str
    source_repo: str
    local_path: str
    category: str
    name: str
    indexed_at: str
    repo_stars: Optional[int] = None
    repo_updated_at: Optional[str] = None
    source_url: Optional[str] = None  # Full source URL for README
    display_name: Optional[str] = None  # Display name for README
    tags: Optional[str] = None  # Tags as JSON string for README


@dataclass
class RepoPlan:
    """Plan for managing the skills repository."""
    repo_name: str
    category: str
    description: str
    skills: List[Skill]
    create_new: bool
    folder_structure: Dict[str, List[Skill]]


class RepoMaintainerAgent:
    """Agent that manages and organizes skills into a single X-Skills repository.

    All skills are organized by category folders within one repository.
    """

    # Single repository for all skills
    REPO_NAME = "X-Skills"

    # Category structure with subcategories
    CATEGORY_STRUCTURE = {
        "development": {
            "subcategories": ["web", "frontend", "backend", "mobile", "devops", "cloud",
                             "testing", "python", "javascript", "rust", "go", "tools",
                             "git", "architecture", "database", "security"],
            "keywords": ["development", "coding", "programming", "developer", "debug", "test", "api", "git"],
            "fallback_to_flat": True
        },
        "automation": {
            "subcategories": ["workflow", "scripting"],
            "keywords": ["automation", "workflow", "script", "batch", "cron"],
            "fallback_to_flat": True
        },
        "daily-assistant": {
            "subcategories": [],
            "keywords": ["daily-assistant", "scheduling", "task", "todo", "reminder", "calendar"],
            "fallback_to_flat": True
        },
        "content-creation": {
            "subcategories": [],
            "keywords": ["content-creation", "writing", "blog", "article", "edit", "draft"],
            "fallback_to_flat": True
        },
        "data-analysis": {
            "subcategories": [],
            "keywords": ["data-analysis", "chart", "graph", "statistics", "visualization", "csv", "json"],
            "fallback_to_flat": True
        },
        "research": {
            "subcategories": [],
            "keywords": ["research", "academic", "paper", "citation", "literature", "study"],
            "fallback_to_flat": True
        },
        "communication": {
            "subcategories": [],
            "keywords": ["communication", "email", "message", "chat", "slack", "discord"],
            "fallback_to_flat": True
        },
        "productivity": {
            "subcategories": [],
            "keywords": ["productivity", "efficient", "optimize", "focus", "timer", "pomodoro"],
            "fallback_to_flat": True
        },
        "commercial": {
            "subcategories": [],
            "keywords": ["commercial", "ecommerce", "shop", "store", "business", "invoice"],
            "fallback_to_flat": True
        },
        "investment": {
            "subcategories": [],
            "keywords": ["investment", "trading", "stock", "crypto", "finance", "portfolio"],
            "fallback_to_flat": True
        },
    }

    # Legacy category mappings for backwards compatibility
    CATEGORY_FOLDERS = {
        cat: data["keywords"] for cat, data in CATEGORY_STRUCTURE.items()
    }

    # Content validation configuration
    FILTER_KEYWORDS = [
        'test', 'example', 'demo', 'template', '_map', '_template',
        'sample', 'mock'
    ]
    MIN_CONTENT_LENGTH = 200

    def __init__(self, github_token: Optional[str] = None, base_org: str = "tools-only", repo_name: str = None):
        """Initialize the Repo Maintainer Agent.

        Args:
            github_token: GitHub token for API operations
            base_org: GitHub organization or username
            repo_name: Name of the skills repository (default: X-Skills)
        """
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.base_org = base_org
        self.repo_name = repo_name or self.REPO_NAME
        self.github = Github(self.github_token) if self.github_token else None
        self.work_dir = Path.cwd() / "skillflow_repos"
        self.work_dir.mkdir(exist_ok=True)
        self._numbering_file = self.work_dir / ".category_numbering.json"
        self._category_numbering: Dict[str, CategoryNumbering] = {}
        self._load_numbering_state()

    def analyze_and_plan(self, skills: List[Skill]) -> RepoPlan:
        """Analyze skills and create a plan for the X-Skills repository.

        Args:
            skills: List of skills to organize

        Returns:
            Single repository plan with category folder structure
        """
        # Check if repo exists
        create_new = not self._repo_exists(self.repo_name)

        # Organize skills into category folders
        folder_structure = self._organize_by_category(skills)

        return RepoPlan(
            repo_name=self.repo_name,
            category="all",
            description="Collection of AI-powered skills organized by category",
            skills=skills,
            create_new=create_new,
            folder_structure=folder_structure
        )

    def _organize_by_category(self, skills: List[Skill]) -> Dict[str, List[Skill]]:
        """Organize skills into category folders with subcategory support.

        Args:
            skills: List of skills to organize

        Returns:
            Dict mapping folder paths to skill lists (can include subcategories)
        """
        folders: Dict[str, List[Skill]] = {}

        for skill in skills:
            category, subcategory = self._determine_category_with_subcategory(skill)

            # Build folder path
            if subcategory and subcategory in self.CATEGORY_STRUCTURE.get(category, {}).get("subcategories", []):
                folder_path = f"{category}/{subcategory}"
            else:
                folder_path = category

            if folder_path not in folders:
                folders[folder_path] = []
            folders[folder_path].append(skill)

        return folders

    def _determine_category(self, skill: Skill) -> str:
        """Determine the category folder for a skill.

        Args:
            skill: Skill to categorize

        Returns:
            Category name
        """
        content_lower = skill.content.lower()
        skill_name_lower = skill.name.lower()

        # Check metadata first
        metadata_category = skill.metadata.get("category", "")
        if metadata_category:
            # Map metadata category to folder
            for folder, keywords in self.CATEGORY_FOLDERS.items():
                cat_lower = metadata_category.lower().replace("-", "").replace("_", "")
                if folder in cat_lower or any(kw in cat_lower for kw in keywords):
                    return folder

        # Search content for keywords
        best_category = "other"
        best_score = 0

        for category, keywords in self.CATEGORY_FOLDERS.items():
            score = sum(1 for kw in keywords if kw in content_lower or kw in skill_name_lower)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    def _determine_category_with_subcategory(self, skill: Skill) -> tuple[str, str]:
        """Determine category and subcategory for a skill.

        Returns:
            Tuple of (category, subcategory)
        """
        # Check metadata first
        metadata_category = skill.metadata.get("category", "")
        metadata_subcategory = skill.metadata.get("subcategory", "")

        if metadata_category:
            category = self._normalize_category(metadata_category)
            if metadata_subcategory:
                subcategory = self._normalize_subcategory(metadata_subcategory)
                if subcategory in self.CATEGORY_STRUCTURE.get(category, {}).get("subcategories", []):
                    return category, subcategory
            return category, ""

        # Fall back to content analysis
        return self._analyze_category_from_content(skill)

    def _normalize_category(self, category: str) -> str:
        """Normalize category name to match our category structure.

        Args:
            category: Category name from metadata

        Returns:
            Normalized category name
        """
        category_lower = category.lower().replace("-", "").replace("_", "")

        for folder in self.CATEGORY_STRUCTURE.keys():
            folder_normalized = folder.lower().replace("-", "").replace("_", "")
            if folder_normalized in category_lower or category_lower in folder_normalized:
                return folder

        # Check keywords
        for folder, structure in self.CATEGORY_STRUCTURE.items():
            keywords = structure.get("keywords", [])
            if any(kw in category_lower for kw in keywords):
                return folder

        return "other"

    def _normalize_subcategory(self, subcategory: str) -> str:
        """Normalize subcategory name.

        Args:
            subcategory: Subcategory name from metadata

        Returns:
            Normalized subcategory name
        """
        return subcategory.lower().strip().replace(" ", "-").replace("_", "-")

    def _analyze_category_from_content(self, skill: Skill) -> tuple[str, str]:
        """Analyze skill content to determine category and subcategory.

        Returns:
            Tuple of (category, subcategory)
        """
        content_lower = skill.content.lower()
        skill_name_lower = skill.name.lower()

        best_category = "other"
        best_subcategory = ""
        best_score = 0

        for category, structure in self.CATEGORY_STRUCTURE.items():
            keywords = structure.get("keywords", [])
            subcategories = structure.get("subcategories", [])

            if not subcategories:
                # Simple keyword match for flat categories
                score = sum(1 for kw in keywords if kw in content_lower)
                if score > best_score:
                    best_score = score
                    best_category = category
                continue

            # Score each subcategory
            best_sub_for_category = ""
            best_sub_score = 0

            for subcategory in subcategories:
                sub_keywords = self._get_keywords_for_subcategory(category, subcategory)
                sub_score = sum(1 for kw in sub_keywords if kw in content_lower or kw in skill_name_lower)

                if sub_score > best_sub_score:
                    best_sub_score = sub_score
                    best_sub_for_category = subcategory

            # Also score main category keywords
            cat_score = sum(1 for kw in keywords if kw in content_lower)
            total_score = cat_score + best_sub_score

            if total_score > best_score:
                best_score = total_score
                best_category = category
                best_subcategory = best_sub_for_category

        return best_category, best_subcategory

    def _get_keywords_for_subcategory(self, category: str, subcategory: str) -> List[str]:
        """Get keywords for a specific subcategory.

        Args:
            category: Parent category
            subcategory: Subcategory name

        Returns:
            List of keywords for this subcategory
        """
        # Subcategory keyword mappings
        subcategory_keywords = {
            "web": ["web", "html", "css", "http", "api", "rest", "graphql", "frontend", "fullstack"],
            "frontend": ["javascript", "typescript", "react", "vue", "angular", "frontend", "ui", "css", "html"],
            "backend": ["server", "backend", "api", "rest", "graphql", "endpoint", "microservice"],
            "mobile": ["mobile", "ios", "android", "react native", "flutter", "app"],
            "devops": ["devops", "deploy", "ci/cd", "docker", "kubernetes", "infrastructure"],
            "cloud": ["cloud", "aws", "azure", "gcp", "lambda", "serverless"],
            "testing": ["test", "testing", "pytest", "jest", "unit test", "integration"],
            "python": ["python", "pip", "poetry", "django", "flask", "fastapi"],
            "javascript": ["javascript", "typescript", "node", "npm", "yarn"],
            "rust": ["rust", "cargo", "crates"],
            "go": ["go", "golang", "goroutine"],
            "tools": ["tool", "utility", "helper", "cli"],
            "git": ["git", "github", "commit", "branch", "repository"],
            "architecture": ["architecture", "design pattern", "structure", "scalability"],
            "database": ["database", "sql", "nosql", "mysql", "postgresql", "mongodb"],
            "security": ["security", "auth", "authentication", "authorization", "encryption"],
            "workflow": ["workflow", "automate", "automation"],
            "scripting": ["script", "bash", "shell", "python script"],
        }

        return subcategory_keywords.get(subcategory, [subcategory])

    def _repo_exists(self, repo_name: str) -> bool:
        """Check if a repository already exists.

        Args:
            repo_name: Name of the repository

        Returns:
            True if repo exists
        """
        if not self.github:
            # Check if local clone exists
            return (self.work_dir / repo_name).exists()

        try:
            self.github.get_repo(f"{self.base_org}/{repo_name}")
            return True
        except Exception:
            return False

    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize a name for use as a folder name.

        Args:
            name: Name to sanitize

        Returns:
            Sanitized folder name
        """
        name = name.lower().strip()
        name = name.replace(" ", "-").replace("_", "-")
        name = "".join(c for c in name if c.isalnum() or c in "-.")
        return name or "other"

    def _load_numbering_state(self) -> None:
        """Load category numbering state from file."""
        if not self._numbering_file.exists():
            return

        try:
            data = json.loads(self._numbering_file.read_text())
            for cat, state in data.items():
                self._category_numbering[cat] = CategoryNumbering(
                    category=cat,
                    next_number=state.get('next_number', 1),
                    name_to_number=state.get('name_to_number', {})
                )
        except Exception as e:
            logger.warning(f"Could not load numbering state: {e}")

    def _save_numbering_state(self) -> None:
        """Save category numbering state to file."""
        data = {
            cat: {
                'next_number': state.next_number,
                'name_to_number': state.name_to_number
            }
            for cat, state in self._category_numbering.items()
        }
        self._numbering_file.write_text(json.dumps(data, indent=2))

    def _get_or_assign_number(self, category: str, sanitized_name: str) -> int:
        """Get existing number or assign new number for a skill name.

        Args:
            category: Category folder name
            sanitized_name: Sanitized skill name (without hash)

        Returns:
            Assigned number for this skill in its category
        """
        if category not in self._category_numbering:
            self._category_numbering[category] = CategoryNumbering(
                category=category,
                next_number=1,
                name_to_number={}
            )

        state = self._category_numbering[category]

        if sanitized_name in state.name_to_number:
            return state.name_to_number[sanitized_name]

        number = state.next_number
        state.name_to_number[sanitized_name] = number
        state.next_number += 1

        self._save_numbering_state()
        return number

    def execute_plan(self, plan: RepoPlan, push: bool = True, force_rebuild: bool = False) -> str:
        """Execute a repository plan.

        Args:
            plan: Repository plan to execute
            push: Whether to push to GitHub
            force_rebuild: Whether to clear all content and rebuild from scratch

        Returns:
            Path to the local repository
        """
        repo_path = self.work_dir / plan.repo_name

        # Clone or open repo
        if plan.create_new:
            logger.info(f"Remote repository doesn't exist, will create new: {plan.repo_name}")
        else:
            logger.info(f"Using existing repo: {plan.repo_name}")

        repo = self._clone_repo(repo_path, plan.repo_name)

        # Only clear content when explicitly requested (force_rebuild=True)
        if force_rebuild:
            logger.info("Force rebuild requested, clearing existing content")
            self._clear_repo_content(repo_path)

        # Load existing skill index for incremental updates
        existing_index = self._load_skill_index(repo_path)

        # Organize skills into folders
        for folder_name, skills in plan.folder_structure.items():
            folder_path = repo_path / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)

            for skill in skills:
                # Validate skill before processing
                should_filter, filter_reason = self._should_filter_skill(skill)
                if should_filter:
                    logger.info(f"Filtering skill '{skill.name}': {filter_reason}")
                    continue
                # Check if this is an update to an existing skill
                existing_location = self._find_existing_skill_location(repo_path, skill)

                if existing_location:
                    # Existing skill with same source_path - check if content changed
                    old_category, old_dir = existing_location
                    if skill.file_hash in existing_index:
                        # Content is the same, skip writing
                        continue
                    else:
                        # Content changed - remove old version (different hash means different content)
                        if old_category != folder_name or old_dir != self._sanitize_filename_for_dir(skill, folder_name):
                            self._cleanup_old_skill_version(repo_path, old_category, old_dir)

                # Write the skill file
                self._write_skill_file(folder_path, skill)

                # Update the index
                skill_dir_name = self._sanitize_filename_for_dir(skill, folder_name)
                self._update_skill_index(repo_path, skill, folder_name, skill_dir_name)

        # Clean up skills that are no longer in the plan (optional - disabled for now)
        # self._cleanup_orphaned_skills(repo_path, plan)

        # Generate/update README
        self._generate_readme(repo_path, plan)

        # Commit changes
        self._commit_changes(repo, plan)

        # Push if requested
        if push:
            self._push_to_remote(repo, plan.repo_name)

        return str(repo_path)

    def _clone_repo(self, repo_path: Path, repo_name: str) -> GitRepo:
        """Clone or open an existing repository.

        Args:
            repo_path: Local path for the repo
            repo_name: Name of the repository

        Returns:
            GitRepo object
        """
        clone_url = f"git@github.com:{self.base_org}/{repo_name}.git"

        if repo_path.exists():
            # Already cloned, pull latest changes
            repo = GitRepo(repo_path)
            try:
                repo.remotes.origin.pull()
                logger.info(f"Pulled latest changes for {repo_name}")
            except Exception as e:
                logger.warning(f"Could not pull: {e}")
            return repo

        # Clone the repository
        repo = GitRepo.clone_from(clone_url, repo_path)
        logger.info(f"Cloned {clone_url}")
        return repo

    def _clear_repo_content(self, repo_path: Path) -> None:
        """Clear all repository content except .git directory.

        Args:
            repo_path: Path to the repository
        """
        logger.info(f"Clearing existing content in {repo_path}")

        for item in repo_path.iterdir():
            if item.name != ".git":
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        logger.debug(f"Content cleared in {repo_path}")

    def _clean_name(self, name: str) -> str:
        """Clean a name for use in directory names.

        Args:
            name: Name to clean

        Returns:
            Cleaned name
        """
        name = name.strip().lower()
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'[-\s]+', '-', name)
        return name[:80] if len(name) > 80 else name

    def _format_timestamp(self, timestamp: Optional[str]) -> str:
        """Format a timestamp as YYYYMMDD.

        Args:
            timestamp: ISO format timestamp string

        Returns:
            Formatted date string or empty string
        """
        if not timestamp:
            return ""

        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.strftime("%Y%m%d")
        except (ValueError, AttributeError):
            return ""

    def _sanitize_filename_for_dir(self, skill: Skill, category: str = "") -> str:
        """Generate directory name with numbering prefix.

        Format: {number}-{sanitized-name}_{hash}
        - number: Sequential number per category (001, 002, etc.)
        - sanitized-name: The original filename (sanitized)
        - hash: First 8 characters of file_hash for uniqueness

        This ensures the same skill content always maps to the same directory,
        preventing duplicates when the same skill is reprocessed.

        Args:
            skill: Skill object
            category: Category folder name (for numbering)

        Returns:
            Sanitized directory name with number prefix and hash suffix
        """
        source_name = Path(skill.source_path).stem
        sanitized = self._clean_name(source_name)

        # Get or assign number for this skill name in category
        number = self._get_or_assign_number(category, sanitized) if category else 0

        hash_prefix = skill.file_hash[:8] if skill.file_hash else "unknown"

        # Format: 001-name_hashprefix (e.g., 001-workflow_a1b2c3d4)
        if number > 0:
            return f"{number:03d}-{sanitized}_{hash_prefix}"
        else:
            return f"{sanitized}_{hash_prefix}"

    def _write_skill_file(self, category_path: Path, skill: Skill) -> None:
        """Create skill subdirectory with skill.md and README.md.

        The directory name is based on the file_hash, so the same content
        will always map to the same directory. If the directory already exists,
        we update the README with current metadata.

        Args:
            category_path: Path to the category folder (can include subcategory)
            skill: Skill to write
        """
        # Extract category from path for numbering
        # Handle subcategory paths like "development/web" -> use "development" for numbering
        path_parts = category_path.relative_to(self.work_dir).parts
        if len(path_parts) >= 2:
            category = path_parts[-2]  # Parent category
        else:
            category = category_path.name

        # Create subdirectory for the skill (name includes hash for uniqueness)
        skill_dir_name = self._sanitize_filename_for_dir(skill, category)
        skill_dir = category_path / skill_dir_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write original content to skill.md (simplified name)
        skill_file = skill_dir / "skill.md"
        skill_file.write_text(skill.content, encoding="utf-8")
        logger.debug(f"Wrote skill file: {skill_file}")

        # Write README.md with metadata (always update to get latest metadata)
        readme_file = skill_dir / "README.md"
        self._write_skill_readme(readme_file, skill)

    def _build_metadata_table(self, skill: Skill) -> str:
        """Build metadata table for skill README.

        Args:
            skill: Skill object

        Returns:
            Markdown table string
        """
        tags = skill.metadata.get('tags', [])
        if isinstance(tags, list):
            tags_str = ', '.join(tags) if tags else 'N/A'
        else:
            tags_str = str(tags) if tags else 'N/A'

        created = self._format_timestamp(skill.created_at) or 'N/A'
        updated = self._format_timestamp(skill.updated_at) or 'N/A'

        # Format dates for display
        created_display = self._format_date_for_display(skill.created_at) or 'N/A'
        updated_display = self._format_date_for_display(skill.updated_at) or 'N/A'

        # Format stars
        stars_display = self._format_stars(skill.repo_stars)

        # Build repo row with stars if available
        if skill.repo_stars:
            repo_row = f"| **Repository** | [{skill.source_repo}]({skill.source_url}) ({stars_display}) |"
        else:
            repo_row = f"| **Repository** | [{skill.source_repo}]({skill.source_url}) |"

        return f"""| Property | Value |
|----------|-------|
| **Name** | {skill.name} |
{repo_row}
| **Original Path** | `{skill.source_path}` |
| **Category** | {skill.metadata.get('category', 'N/A')} |
| **Subcategory** | {skill.metadata.get('subcategory', 'N/A')} |
| **Tags** | {tags_str} |
| **Created** | {created_display} |
| **Updated** | {updated_display} |
| **File Hash** | `{skill.file_hash[:16]}...` |"""

    def _format_date_for_display(self, timestamp: Optional[str]) -> Optional[str]:
        """Format timestamp for display (YYYY-MM-DD).

        Args:
            timestamp: ISO format timestamp

        Returns:
            Formatted date string or None
        """
        if not timestamp:
            return None
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return None

    def _format_stars(self, stars: Optional[int]) -> str:
        """Format star count for display.

        Args:
            stars: Number of stars

        Returns:
            Formatted star string (e.g., "⭐ 234", "⭐ 1.2k", "🔥 12.3k")
        """
        if stars is None or stars == 0:
            return "N/A"

        # Determine heat indicator
        if stars >= 5000:
            heat = "🔥"
        elif stars >= 1000:
            heat = "⭐"
        else:
            heat = "⭐"

        # Format number
        if stars >= 1000:
            formatted = f"{stars / 1000:.1f}k"
        else:
            formatted = str(stars)

        return f"{heat} {formatted}"

    def _should_filter_skill(self, skill: Skill) -> tuple[bool, str]:
        """Check if a skill should be filtered out.

        Args:
            skill: Skill to validate

        Returns:
            Tuple of (should_filter, reason)
        """
        # Check 1: Filename keywords
        name_lower = skill.name.lower()
        source_path_lower = skill.source_path.lower()

        for keyword in self.FILTER_KEYWORDS:
            if keyword in name_lower or keyword in source_path_lower:
                return True, f"Contains filter keyword: {keyword}"

        # Check 2: Content length
        content_stripped = skill.content.strip()
        if len(content_stripped) < self.MIN_CONTENT_LENGTH:
            return True, f"Content too short: {len(content_stripped)} chars < {self.MIN_CONTENT_LENGTH}"

        # Check 3: Meaningful content (not just whitespace/headers)
        meaningful_chars = re.sub(r'[\s#*`\-_\[\](){}]', '', content_stripped)
        if len(meaningful_chars) < self.MIN_CONTENT_LENGTH // 2:
            return True, f"Insufficient meaningful content: {len(meaningful_chars)} chars"

        return False, ""

    def renumber_existing_skills(self, repo_path: Path, dry_run: bool = False) -> None:
        """Renumber existing skill directories with new naming scheme.

        Args:
            repo_path: Path to the repository
            dry_run: If True, only print what would be done
        """
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Renumbering existing skills...")

        self._category_numbering.clear()

        for category_dir in repo_path.iterdir():
            if category_dir.name.startswith('.') or not category_dir.is_dir():
                continue

            category = category_dir.name
            skills_in_category = []

            for skill_dir in category_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                # Parse existing name to extract sanitized name
                match = re.match(r'^(\d+-)?(.+?)_[a-f0-9]{8}$', skill_dir.name)
                if match:
                    sanitized_name = match.group(2)
                    skills_in_category.append((sanitized_name, skill_dir))

            # Sort alphabetically by sanitized name
            skills_in_category.sort(key=lambda x: x[0])

            # Rename with new numbering
            for sanitized_name, old_dir in skills_in_category:
                new_number = self._get_or_assign_number(category, sanitized_name)

                skill_md = old_dir / "skill.md"
                if not skill_md.exists():
                    continue

                content = skill_md.read_text()
                import hashlib
                file_hash = hashlib.sha256(content.encode()).hexdigest()
                hash_prefix = file_hash[:8]

                new_name = f"{new_number:03d}-{sanitized_name}_{hash_prefix}"
                new_path = category_dir / new_name

                if dry_run:
                    print(f"Would rename: {old_dir.name} -> {new_name}")
                elif old_dir.name != new_name:
                    old_dir.rename(new_path)
                    logger.debug(f"Renamed: {old_dir.name} -> {new_name}")

        self._save_numbering_state()
        logger.info("Renumbering complete")

    def _get_or_generate_description(self, skill: Skill) -> str:
        """Extract or generate a description for the skill.

        Args:
            skill: Skill object

        Returns:
            Description string
        """
        # Check metadata first
        primary_purpose = skill.metadata.get('primary_purpose', '')
        if primary_purpose:
            return primary_purpose

        # Extract from content
        content = skill.content

        # Try to find first paragraph (after initial headers)
        lines = content.split('\n')
        description_lines = []
        in_description = False

        for line in lines:
            line = line.strip()
            if not line:
                if description_lines:
                    break
                continue

            # Skip YAML frontmatter
            if line.startswith('---'):
                continue

            # Skip headers at the start
            if line.startswith('#') and not description_lines:
                continue

            # Start collecting description
            if not in_description:
                in_description = True

            description_lines.append(line)

            # Stop after collecting a reasonable paragraph
            if len(description_lines) >= 3:
                break

        if description_lines:
            return ' '.join(description_lines[:2])

        # Fallback: generate from name and category
        category = skill.metadata.get('category', 'AI assistant')
        return f"A {category} skill for AI assistants like Claude Code."

    def _write_skill_readme(self, readme_path: Path, skill: Skill) -> None:
        """Write skill's README.md with metadata and description.

        Only writes if content has changed to avoid unnecessary file operations.

        Args:
            readme_path: Path to write the README
            skill: Skill object
        """
        metadata_table = self._build_metadata_table(skill)
        description = self._get_or_generate_description(skill)

        tags = skill.metadata.get('tags', [])
        if isinstance(tags, list):
            tags_str = ' '.join(f'`{tag}`' for tag in tags[:5]) if tags else ''
        else:
            tags_str = ''

        content = f"""# {skill.name}

{metadata_table}

## Description

{description}

{f"**Tags:** {tags_str}" if tags_str else ""}

---

*This skill is maintained by [SkillFlow](https://github.com/tools-only/SkillFlow)*
*Source: [{skill.source_repo}]({skill.source_url})*
"""

        # Only write if content changed
        if readme_path.exists():
            existing_content = readme_path.read_text(encoding="utf-8")
            if existing_content == content:
                logger.debug(f"README unchanged, skipping write: {readme_path}")
                return

        readme_path.write_text(content, encoding="utf-8")
        logger.debug(f"Wrote skill README: {readme_path}")

    def _scan_all_skills(self, repo_path: Path) -> List[Dict[str, Any]]:
        """Scan all skill directories in the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            List of skill information dictionaries
        """
        skills = []

        for category_dir in repo_path.iterdir():
            if category_dir.name.startswith('.') or not category_dir.is_dir():
                continue

            category = category_dir.name

            for skill_dir in category_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                readme_path = skill_dir / "README.md"
                skill_md_path = skill_dir / "skill.md"

                if readme_path.exists():
                    # Read README to extract metadata
                    skill_info = self._extract_skill_info_from_readme(readme_path, skill_dir.name, category)
                    if skill_info:
                        skills.append(skill_info)
                elif skill_md_path.exists():
                    # Fallback: create basic info from directory name
                    skills.append({
                        'name': skill_dir.name,
                        'display_name': skill_dir.name,
                        'category': category,
                        'source': 'Unknown',
                        'source_url': '#',
                        'tags': [],
                    })

        return skills

    def _regenerate_readme_from_disk(self, repo_path: Path) -> None:
        """Regenerate README by scanning all skill directories on disk.

        This ensures README includes ALL skills, not just those in .index.json.
        Supports subcategory structure like development/web/.

        Args:
            repo_path: Path to the repository
        """
        logger.info("Regenerating README from disk scan...")

        skills_by_category = {}

        # Scan all category directories (can be top-level or subcategories)
        def scan_category_dir(category_dir: Path, category_path: str) -> None:
            """Recursively scan a category directory for skills."""
            has_subdirs = False

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
                        has_subdirs = True
                        new_category_path = f"{category_path}/{item.name}" if category_path else item.name
                        scan_category_dir(item, new_category_path)

        for category_dir in repo_path.iterdir():
            if category_dir.name.startswith('.') or not category_dir.is_dir():
                continue

            scan_category_dir(category_dir, category_dir.name)

        # Build and write README
        readme_content = self._build_readme_with_tables(skills_by_category)
        readme_path = repo_path / "README.md"
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
                import re
                tags = re.findall(r'`([^`]+)`', tags_line)
                info['tags'] = tags[:3]  # Limit to 3 tags for table

            return info

        except Exception as e:
            logger.debug(f"Could not read README {readme_path}: {e}")
            return None

    def _group_by_category(self, skills: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group skills by category.

        Args:
            skills: List of skill information

        Returns:
            Dict mapping category to list of skills
        """
        grouped: Dict[str, List[Dict[str, Any]]] = {}

        for skill in skills:
            category = skill['category']
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(skill)

        return grouped

    def _build_skill_table_row(self, skill: Dict[str, Any], category: str) -> str:
        """Build a table row for a skill.

        Args:
            skill: Skill information dictionary
            category: Category name

        Returns:
            Markdown table row
        """
        name = skill['display_name']
        rel_path = f"{category}/{skill['name']}"
        tags = ' '.join(f"`{t}`" for t in skill['tags']) if skill['tags'] else ''
        popularity = self._format_stars(skill.get('repo_stars'))

        return f"| [{name}]({rel_path}/) | [{skill['source']}]({skill['source_url']}) | {popularity} | {tags} |"

    def _build_readme_with_tables(self, skills_by_category: Dict[str, List[Dict[str, Any]]]) -> str:
        """Build main README content with skill tables.

        Args:
            skills_by_category: Dict of category to skills list

        Returns:
            Complete README markdown content
        """
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
            display = cat.replace("-", " ").title()
            category_overview.append(f"- **{display}** ({count} skill{'s' if count != 1 else ''})")

        # Build skill tables by category
        skill_tables = []
        for category in sorted(skills_by_category.keys()):
            skills = skills_by_category[category]
            display = category.replace("-", " ").title()

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

## Repository Structure

```
X-Skills/
"""

        for cat in sorted(skills_by_category.keys()):
            readme_content += f"├── {cat}/\n"

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

    def _generate_readme(self, repo_path: Path, plan: RepoPlan) -> None:
        """Generate or update the main README file with skill tables.

        This now supports INCREMENTAL updates:
        - Loads existing skills from .index.json (previously processed)
        - Merges with new skills from current plan
        - Generates README with ALL skills (existing + new)

        This means if you have 100 skills and add 50 more, the README will show 150,
        not just the 50 new ones.

        Args:
            repo_path: Path to the repository
            plan: Repository plan containing folder_structure with NEW skills to add
        """
        # Step 1: Load existing skills from .index.json (previously processed)
        existing_index = self._load_skill_index(repo_path)
        logger.info(f"Found {len(existing_index)} existing skills in index")

        # Step 2: Build skills_by_category from ALL sources (existing + new)
        skills_by_category = {}

        # First, add existing skills from index
        for entry in existing_index.values():
            category = entry.category
            if category not in skills_by_category:
                skills_by_category[category] = []

            # Parse tags if stored as JSON string (handle backwards compatibility)
            tags = []
            if entry.tags:
                try:
                    tags = json.loads(entry.tags) if isinstance(entry.tags, str) else entry.tags
                except:
                    tags = []
            if not isinstance(tags, list):
                tags = []
            tags = tags[:3]  # Limit to 3 tags for table

            # Build source_url if not available (backwards compatibility)
            source_url = entry.source_url
            if not source_url and entry.source_path:
                # Construct URL from source_repo and source_path
                source_url = f"https://raw.githubusercontent.com/{entry.source_repo}/main/{entry.source_path}"

            # Use display_name if available, otherwise use name
            display_name = entry.display_name if entry.display_name else entry.name

            # Use local_path's directory name as the skill folder name
            skill_folder_name = entry.local_path.split('/')[-1] if '/' in entry.local_path else entry.name

            skills_by_category[category].append({
                'name': skill_folder_name,
                'display_name': display_name,
                'category': category,
                'source': entry.source_repo,
                'source_url': source_url,
                'tags': tags,
                'repo_stars': entry.repo_stars,
            })

        logger.info(f"Loaded {sum(len(v) for v in skills_by_category.values())} existing skills from index")

        # Then, add/update with new skills from current plan
        new_skills_count = 0
        updated_skills_count = 0

        for folder_name, skills in plan.folder_structure.items():
            if folder_name not in skills_by_category:
                skills_by_category[folder_name] = []

            for skill in skills:
                # Extract tags from metadata
                tags = skill.metadata.get('tags', [])
                if isinstance(tags, list):
                    tags = tags[:3]  # Limit to 3 tags for table

                skill_info = {
                    'name': self._sanitize_filename_for_dir(skill),
                    'display_name': skill.name,
                    'category': folder_name,
                    'source': skill.source_repo,
                    'source_url': skill.source_url,
                    'tags': tags,
                    'repo_stars': skill.repo_stars,
                }

                # Check if this skill already exists (by source_url)
                existing_skill_index = None
                for i, existing in enumerate(skills_by_category[folder_name]):
                    if existing.get('source_url') == skill.source_url:
                        existing_skill_index = i
                        break

                if existing_skill_index is not None:
                    # Update existing skill
                    skills_by_category[folder_name][existing_skill_index] = skill_info
                    updated_skills_count += 1
                else:
                    # Add new skill
                    skills_by_category[folder_name].append(skill_info)
                    new_skills_count += 1

        logger.info(f"Added {new_skills_count} new skills, updated {updated_skills_count} existing skills")

        # Step 3: Build and write README with ALL skills
        total_skills = sum(len(skills) for skills in skills_by_category.values())
        readme_content = self._build_readme_with_tables(skills_by_category)
        readme_path = repo_path / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")

        logger.info(f"Generated main README with {total_skills} total skills: {readme_path}")

    def _get_index_path(self, repo_path: Path) -> Path:
        """Get the path to the skill index file.

        Args:
            repo_path: Path to the repository

        Returns:
            Path to .index.json
        """
        return repo_path / ".index.json"

    def _load_skill_index(self, repo_path: Path) -> Dict[str, SkillIndexEntry]:
        """Load the skill index file.

        Args:
            repo_path: Path to the repository

        Returns:
            Dict mapping file_hash to SkillIndexEntry
        """
        index_path = self._get_index_path(repo_path)
        if not index_path.exists():
            return {}

        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            index = {}
            for entry_data in data.get("skills", []):
                entry = SkillIndexEntry(**entry_data)
                index[entry.file_hash] = entry
            logger.debug(f"Loaded skill index with {len(index)} entries")

            # Migrate old entries to include new fields
            index = self._migrate_index_entries(repo_path, index)

            return index
        except (json.JSONDecodeError, IOError, TypeError) as e:
            logger.warning(f"Could not load skill index: {e}")
            return {}

    def _migrate_index_entries(self, repo_path: Path, index: Dict[str, SkillIndexEntry]) -> Dict[str, SkillIndexEntry]:
        """Migrate old index entries to include new fields.

        Ensures backwards compatibility when new fields are added to SkillIndexEntry.

        Args:
            repo_path: Path to the repository
            index: Current index dictionary

        Returns:
            Migrated index dictionary
        """
        migrated = False
        for entry in index.values():
            # Migrate display_name
            if not entry.display_name:
                entry.display_name = entry.name
                migrated = True

            # Migrate source_url (construct from source_repo and source_path)
            if not entry.source_url:
                entry.source_url = f"https://raw.githubusercontent.com/{entry.source_repo}/main/{entry.source_path}"
                migrated = True

            # Migrate tags (set to empty list if missing)
            if entry.tags is None:
                entry.tags = "[]"
                migrated = True

        if migrated:
            logger.info("Migrated old index entries to include new fields")
            self._save_skill_index(repo_path, index)

        return index

    def rebuild_index_from_disk(self, repo_path: Path) -> None:
        """Rebuild the entire index from disk by scanning all skill directories.

        This is a recovery operation when the index becomes out of sync with disk.

        Args:
            repo_path: Path to the repository
        """
        logger.warning("Rebuilding index from disk - this may take a while...")

        index = {}
        scanned = 0

        for category_dir in repo_path.iterdir():
            if category_dir.name.startswith('.') or not category_dir.is_dir():
                continue

            for skill_dir in category_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                readme_path = skill_dir / "README.md"
                skill_md_path = skill_dir / "skill.md"

                if not readme_path.exists() or not skill_md_path.exists():
                    continue

                try:
                    # Extract metadata from README
                    info = self._extract_skill_info_from_readme(readme_path, skill_dir.name, category_dir.name)
                    if not info:
                        continue

                    # Read skill.md to compute hash
                    content = skill_md_path.read_text(encoding="utf-8")
                    import hashlib
                    file_hash = hashlib.sha256(content.encode()).hexdigest()

                    # Create index entry with all required fields
                    entry = SkillIndexEntry(
                        file_hash=file_hash,
                        source_path=info.get('source_path', skill_dir.name),
                        source_repo=info.get('source', 'unknown'),
                        local_path=f"{category_dir.name}/{skill_dir.name}",
                        category=category_dir.name,
                        name=skill_dir.name,
                        display_name=info.get('display_name', skill_dir.name),
                        indexed_at=datetime.utcnow().isoformat(),
                        source_url=info.get('source_url', f"https://github.com/{info.get('source', 'unknown')}"),
                        tags=json.dumps(info.get('tags', [])),
                        repo_stars=info.get('repo_stars'),
                    )

                    index[file_hash] = entry
                    scanned += 1

                except Exception as e:
                    logger.debug(f"Error scanning {skill_dir}: {e}")

        # Save rebuilt index
        self._save_skill_index(repo_path, index)
        logger.info(f"Rebuilt index with {scanned} entries")

    def _save_skill_index(self, repo_path: Path, index: Dict[str, SkillIndexEntry]) -> None:
        """Save the skill index file.

        Args:
            repo_path: Path to the repository
            index: Dict mapping file_hash to SkillIndexEntry
        """
        index_path = self._get_index_path(repo_path)
        data = {
            "version": "1.0",
            "updated_at": datetime.utcnow().isoformat(),
            "skills": [asdict(entry) for entry in index.values()],
        }
        index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug(f"Saved skill index with {len(index)} entries")

    def _update_skill_index(
        self,
        repo_path: Path,
        skill: Skill,
        category: str,
        local_dir: str
    ) -> None:
        """Update the skill index for a single skill.

        Args:
            repo_path: Path to the repository
            skill: Skill object
            category: Category folder name
            local_dir: Local directory name (relative to category)
        """
        index = self._load_skill_index(repo_path)

        # Get tags from metadata
        tags = skill.metadata.get('tags', [])
        if isinstance(tags, list):
            tags = json.dumps(tags)

        # Create or update entry for this skill
        entry = SkillIndexEntry(
            file_hash=skill.file_hash,
            source_path=skill.source_path,
            source_repo=skill.source_repo,
            local_path=f"{category}/{local_dir}",
            category=category,
            name=self._sanitize_filename_for_dir(skill),
            display_name=skill.name,
            indexed_at=datetime.utcnow().isoformat(),
            repo_stars=skill.repo_stars,
            repo_updated_at=skill.updated_at,
            source_url=skill.source_url,
            tags=tags,
        )

        index[skill.file_hash] = entry
        self._save_skill_index(repo_path, index)

    def _remove_from_index(self, repo_path: Path, file_hash: str) -> None:
        """Remove a skill from the index.

        Args:
            repo_path: Path to the repository
            file_hash: Hash of the skill to remove
        """
        index = self._load_skill_index(repo_path)
        if file_hash in index:
            del index[file_hash]
            self._save_skill_index(repo_path, index)
            logger.debug(f"Removed {file_hash} from index")

    def _find_existing_skill_location(self, repo_path: Path, skill: Skill) -> Optional[tuple[str, str]]:
        """Find if a skill already exists in the repository (by source_path).

        This enables proper updates: if the same source file has new content,
        we can update the existing directory instead of creating a new one.

        Args:
            repo_path: Path to the repository
            skill: Skill to check

        Returns:
            Tuple of (category, local_dir) if found, None otherwise
        """
        index = self._load_skill_index(repo_path)

        for entry in index.values():
            if entry.source_path == skill.source_path and entry.source_repo == skill.source_repo:
                # Found matching source path - return stored location
                parts = entry.local_path.split("/", 1)
                if len(parts) == 2:
                    return parts[0], parts[1]
        return None

    def _cleanup_old_skill_version(self, repo_path: Path, category: str, old_dir: str) -> None:
        """Clean up an old skill directory after update.

        Args:
            repo_path: Path to the repository
            category: Category folder name
            old_dir: Old directory name to remove
        """
        old_path = repo_path / category / old_dir
        if old_path.exists() and old_path.is_dir():
            shutil.rmtree(old_path)
            logger.debug(f"Removed old skill directory: {old_path}")

    def _commit_changes(self, repo: GitRepo, plan: RepoPlan) -> None:
        """Commit changes to the repository.

        Args:
            repo: Git repository
            plan: Repository plan
        """
        # Add all changes
        try:
            repo.git.add(A=True)
        except Exception as e:
            logger.warning(f"Could not add files: {e}")

        # Check if there are changes to commit
        # Ensure .index.json is tracked
        repo_path = Path(repo.working_dir)
        index_path = self._get_index_path(repo_path)
        if index_path.exists():
            try:
                repo.git.add(str(index_path.relative_to(repo_path)))
            except Exception:
                pass  # May already be tracked

        if repo.is_dirty() or repo.untracked_files:
            skill_count = len(plan.skills)
            folders = ", ".join(plan.folder_structure.keys())
            message = f"Add {skill_count} new skill(s)\n\nCategories: {folders}\n\nAutomated update by SkillFlow"

            repo.index.commit(message)
            logger.info(f"Committed {skill_count} skills")
        else:
            logger.info("No changes to commit")

    def _push_to_remote(self, repo: GitRepo, repo_name: str) -> None:
        """Push changes to GitHub.

        Args:
            repo: Git repository
            repo_name: Name of the repository
        """
        try:
            origin = repo.remote("origin")
            push_info = origin.push()

            for info in push_info:
                if info.flags & info.ERROR:
                    logger.error(f"Push error: {str(info)}")
                else:
                    logger.info(f"✓ Pushed to {repo_name}")
        except GitCommandError as e:
            logger.error(f"Git push error: {e}")


# Convenience function for Claude Code to call
def process_skills(
    skills_data: List[Dict[str, Any]],
    github_token: Optional[str] = None,
    org: str = "tools-only",
    repo_name: str = "X-Skills",
    push: bool = True,
    force_rebuild: bool = False
) -> str:
    """Process a list of skills and organize them into the X-Skills repository.

    This is the main entry point for Claude Code to call.

    Args:
        skills_data: List of skill dictionaries
        github_token: GitHub token (optional, reads from GITHUB_TOKEN env var)
        org: GitHub organization/username
        repo_name: Name of the skills repository
        push: Whether to push to GitHub
        force_rebuild: Whether to clear all content and rebuild from scratch

    Returns:
        Path to the local repository
    """
    # Convert dict data to Skill objects
    skills = [Skill(**data) for data in skills_data]

    # Create agent
    agent = RepoMaintainerAgent(github_token=github_token, base_org=org, repo_name=repo_name)

    # Analyze and plan
    plan = agent.analyze_and_plan(skills)

    # Execute plan
    repo_path = agent.execute_plan(plan, push=push, force_rebuild=force_rebuild)

    logger.info(f"✓ Processed {len(skills)} skills into {plan.repo_name}")

    return repo_path


def create_skill_from_file(file_path: str) -> Dict[str, Any]:
    """Create a skill dictionary from a file path.

    Args:
        file_path: Path to the skill markdown file

    Returns:
        Skill dictionary
    """
    path = Path(file_path)

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract metadata from YAML frontmatter if present
    metadata = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                metadata = yaml.safe_load(parts[1]) or {}
                content = parts[2]
            except:
                content = content

    return {
        "name": metadata.get("name", path.stem),
        "content": content,
        "source_repo": metadata.get("source_repo", "unknown"),
        "source_path": metadata.get("original_path", str(path)),
        "source_url": metadata.get("source", ""),
        "file_hash": metadata.get("file_hash", ""),
        "metadata": metadata
    }


if __name__ == "__main__":
    import sys

    # Example usage from command line
    if len(sys.argv) > 1:
        # Process files passed as arguments
        skills_list = [create_skill_from_file(f) for f in sys.argv[1:]]
        result = process_skills(skills_list)
        print(f"Processed skills into: {result}")
    else:
        print("Usage: python -m src.repo_maintainer <skill_file1.md> <skill_file2.md> ...")
