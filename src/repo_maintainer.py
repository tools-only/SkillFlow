"""Repo Maintainer Agent - Manages and organizes skills into a single GitHub repository.

This agent manages the X-Skills repository with category-based folder organization.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from git import Repo as GitRepo, GitCommandError
from github import Github


logger = logging.getLogger(__name__)


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

    # Category mappings for folder organization
    CATEGORY_FOLDERS = {
        "development": ["development", "coding", "programming", "developer", "debug", "test", "api", "git"],
        "daily-assistant": ["daily-assistant", "scheduling", "task", "todo", "reminder", "calendar"],
        "content-creation": ["content-creation", "writing", "blog", "article", "edit", "draft"],
        "data-analysis": ["data-analysis", "chart", "graph", "statistics", "visualization", "csv", "json"],
        "automation": ["automation", "workflow", "script", "batch", "cron"],
        "research": ["research", "academic", "paper", "citation", "literature", "study"],
        "communication": ["communication", "email", "message", "chat", "slack", "discord"],
        "productivity": ["productivity", "efficient", "optimize", "focus", "timer", "pomodoro"],
        "commercial": ["commercial", "ecommerce", "shop", "store", "business", "invoice"],
        "investment": ["investment", "trading", "stock", "crypto", "finance", "portfolio"],
    }

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
        """Organize skills into category folders.

        Args:
            skills: List of skills to organize

        Returns:
            Dict mapping category folder names to skill lists
        """
        folders: Dict[str, List[Skill]] = {}

        for skill in skills:
            category = self._determine_category(skill)
            folder_name = self._sanitize_folder_name(category)

            if folder_name not in folders:
                folders[folder_name] = []
            folders[folder_name].append(skill)

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

    def execute_plan(self, plan: RepoPlan, push: bool = True) -> str:
        """Execute a repository plan.

        Args:
            plan: Repository plan to execute
            push: Whether to push to GitHub

        Returns:
            Path to the local repository
        """
        repo_path = self.work_dir / plan.repo_name

        # Clone or create repo
        if plan.create_new:
            logger.info(f"Cloning existing repo: {plan.repo_name}")
            repo = self._clone_repo(repo_path, plan.repo_name)
        else:
            logger.info(f"Using existing repo: {plan.repo_name}")
            repo = self._clone_repo(repo_path, plan.repo_name)

        # Organize skills into folders
        for folder_name, skills in plan.folder_structure.items():
            folder_path = repo_path / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)

            for skill in skills:
                skill_path = folder_path / f"{self._sanitize_filename(skill.name)}.md"
                self._write_skill_file(skill_path, skill)

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

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a name for use as a filename.

        Args:
            name: Name to sanitize

        Returns:
            Sanitized filename
        """
        name = name.strip()
        name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        name = name.replace(":", "_").replace("*", "_").replace("?", "_")
        name = name.replace('"', "_").replace("<", "_").replace(">", "_")
        name = name.replace("|", "_")
        if len(name) > 100:
            name = name[:97] + "..."
        return name or "unnamed_skill"

    def _write_skill_file(self, file_path: Path, skill: Skill) -> None:
        """Write a skill file with metadata header.

        Args:
            file_path: Path to write the file
            skill: Skill to write
        """
        # Check if file already exists (skip duplicates)
        if file_path.exists():
            return

        header = f"""---
name: {skill.name}
source: {skill.source_url}
original_path: {skill.source_path}
source_repo: {skill.source_repo}
category: {skill.metadata.get('category', '')}
subcategory: {skill.metadata.get('subcategory', '')}
tags: {skill.metadata.get('tags', [])}
collected_at: {datetime.utcnow().isoformat()}
file_hash: {skill.file_hash}
---

"""

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(header + skill.content)

        logger.debug(f"Wrote skill: {file_path}")

    def _generate_readme(self, repo_path: Path, plan: RepoPlan) -> None:
        """Generate or update the README file.

        Args:
            repo_path: Path to the repository
            plan: Repository plan
        """
        readme_path = repo_path / "README.md"

        # Count skills by folder
        folder_counts = {
            folder: len(skills)
            for folder, skills in plan.folder_structure.items()
        }
        total_skills = sum(folder_counts.values())

        # Build category list for README
        category_lines = []
        for folder, count in sorted(folder_counts.items()):
            folder_display = folder.replace("-", " ").title()
            category_lines.append(f"- **{folder_display}**: {count} skill{'s' if count != 1 else ''}")

        readme_content = f"""# X-Skills

A curated collection of **{total_skills} AI-powered skills** organized into {len(folder_counts)} categories.

## Overview

This repository contains automatically aggregated skills from various open-source projects. Each skill is designed to work with AI assistants like Claude Code to automate specific tasks.

## Categories

{chr(10).join(category_lines)}

## Repository Structure

```
X-Skills/
"""

        for folder in sorted(folder_counts.keys()):
            readme_content += f"├── {folder}/\n"

        readme_content += f"""```

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
2. Copy the skill content to your project
3. Use with Claude Code or similar AI assistants

## Contributing

This repository is automatically maintained by [SkillFlow](https://github.com/tools-only/SkillFlow). Skills are aggregated from open-source repositories.

---

*Last updated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}*
*Automatically maintained by SkillFlow*
"""

        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)

        logger.info(f"Generated README: {readme_path}")

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
    push: bool = True
) -> str:
    """Process a list of skills and organize them into the X-Skills repository.

    This is the main entry point for Claude Code to call.

    Args:
        skills_data: List of skill dictionaries
        github_token: GitHub token (optional, reads from GITHUB_TOKEN env var)
        org: GitHub organization/username
        repo_name: Name of the skills repository
        push: Whether to push to GitHub

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
    repo_path = agent.execute_plan(plan, push=push)

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
