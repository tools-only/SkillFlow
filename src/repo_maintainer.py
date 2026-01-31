"""Repo Maintainer Agent - Manages and organizes skills into separate GitHub repos.

This agent can be called from Claude Code to:
1. Analyze new skills and categorize them
2. Create "X Skills" repos as needed (e.g., "Development Skills")
3. Organize skills into folders
4. Generate/update README introductions
5. Push to appropriate repositories
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
    """Plan for managing a skills repository."""
    repo_name: str
    category: str
    description: str
    skills: List[Skill]
    create_new: bool
    folder_structure: Dict[str, List[Skill]]


class RepoMaintainerAgent:
    """Agent that manages and organizes skills into GitHub repositories.

    This agent can reason about:
    - Whether to create a new repository or use an existing one
    - How to organize skills into folders
    - What to write in README introductions
    """

    # Known skill repositories
    KNOWN_REPOS = {
        "Development Skills": ["development", "coding", "programming", "developer", "debug", "test"],
        "Daily Assistant Skills": ["daily-assistant", "scheduling", "task", "todo", "reminder", "calendar"],
        "Content Creation Skills": ["content-creation", "writing", "blog", "article", "edit"],
        "Data Analysis Skills": ["data-analysis", "chart", "graph", "statistics", "visualization"],
        "Automation Skills": ["automation", "workflow", "script", "batch", "cron"],
        "Research Skills": ["research", "academic", "paper", "citation", "literature"],
        "Communication Skills": ["communication", "email", "message", "chat", "slack"],
        "Productivity Skills": ["productivity", "efficient", "optimize", "focus", "timer"],
        "Commercial Skills": ["commercial", "ecommerce", "shop", "store", "business"],
        "Investment Skills": ["investment", "trading", "stock", "crypto", "finance"],
    }

    def __init__(self, github_token: Optional[str] = None, base_org: str = "tools-only"):
        """Initialize the Repo Maintainer Agent.

        Args:
            github_token: GitHub token for API operations
            base_org: GitHub organization or username for repos
        """
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.base_org = base_org
        self.github = Github(self.github_token) if self.github_token else None
        self.work_dir = Path.cwd() / "skillflow_repos"
        self.work_dir.mkdir(exist_ok=True)

    def analyze_and_plan(self, skills: List[Skill]) -> List[RepoPlan]:
        """Analyze skills and create plans for repository management.

        Args:
            skills: List of skills to organize

        Returns:
            List of repository plans
        """
        plans: Dict[str, RepoPlan] = {}

        for skill in skills:
            # Determine which repo this skill belongs to
            repo_name, category = self._determine_repo(skill)

            if repo_name not in plans:
                # Check if repo already exists
                create_new = not self._repo_exists(repo_name)
                plans[repo_name] = RepoPlan(
                    repo_name=repo_name,
                    category=category,
                    description=self._generate_repo_description(category),
                    skills=[],
                    create_new=create_new,
                    folder_structure={}
                )

            plans[repo_name].skills.append(skill)

        # Organize skills into folders within each repo
        for plan in plans.values():
            plan.folder_structure = self._organize_into_folders(plan.skills, plan.category)

        return list(plans.values())

    def _determine_repo(self, skill: Skill) -> tuple[str, str]:
        """Determine which repository a skill belongs to.

        Args:
            skill: Skill to categorize

        Returns:
            Tuple of (repo_name, base_category)
        """
        content_lower = skill.content.lower()
        skill_name_lower = skill.name.lower()

        # Check metadata first
        category = skill.metadata.get("category", "")
        if category:
            for repo_name, keywords in self.KNOWN_REPOS.items():
                cat_lower = category.lower().replace("-", " ")
                if any(kw in cat_lower for kw in keywords):
                    return repo_name, category

        # Search content for keywords
        best_repo = "Other Skills"
        best_score = 0

        for repo_name, keywords in self.KNOWN_REPOS.items():
            score = sum(1 for kw in keywords if kw in content_lower or kw in skill_name_lower)
            if score > best_score:
                best_score = score
                best_repo = repo_name

        return best_repo, category or "other"

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

    def _generate_repo_description(self, category: str) -> str:
        """Generate a description for a repository.

        Args:
            category: Category name

        Returns:
            Repository description
        """
        descriptions = {
            "development": "Collection of AI-powered development skills for coding, debugging, and software engineering.",
            "daily-assistant": "Daily assistant skills for scheduling, task management, and personal organization.",
            "content-creation": "Skills for content creation, writing, and media production assistance.",
            "data-analysis": "Data analysis, visualization, and statistics skills.",
            "automation": "Automation and workflow scripting skills.",
            "research": "Research skills for academic work and data gathering.",
            "communication": "Communication skills for email, messaging, and collaboration.",
            "productivity": "Productivity enhancement skills and tools.",
            "commercial": "Commercial and business-related skills.",
            "investment": "Investment and financial analysis skills.",
            "other": "Miscellaneous AI skills that don't fit into other categories.",
        }

        cat_key = category.lower().replace("-", "").replace("_", "")
        for key, desc in descriptions.items():
            if key in cat_key:
                return desc

        return f"Collection of {category} related AI skills."

    def _organize_into_folders(self, skills: List[Skill], category: str) -> Dict[str, List[Skill]]:
        """Organize skills into subcategory folders.

        Args:
            skills: List of skills in this repo
            category: Base category

        Returns:
            Dict mapping folder name to list of skills
        """
        folders: Dict[str, List[Skill]] = {}

        for skill in skills:
            # Get subcategory from metadata
            subcategory = skill.metadata.get("subcategory", "general")
            folder_name = self._sanitize_folder_name(subcategory)

            if folder_name not in folders:
                folders[folder_name] = []
            folders[folder_name].append(skill)

        return folders

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
        return name or "general"

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
            logger.info(f"Creating new repo: {plan.repo_name}")
            repo = self._create_repo(repo_path, plan.repo_name, plan.description)
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
        if push and self.github_token:
            self._push_to_remote(repo, plan.repo_name)

        return str(repo_path)

    def _create_repo(self, repo_path: Path, repo_name: str, description: str) -> GitRepo:
        """Create a new repository locally and on GitHub.

        Args:
            repo_path: Local path for the repo
            repo_name: Name of the repository
            description: Repository description

        Returns:
            GitRepo object
        """
        # Create local repo
        repo_path.mkdir(parents=True, exist_ok=True)
        repo = GitRepo.init(repo_path)

        # Create on GitHub
        if self.github:
            try:
                user = self.github.get_user()
                gh_repo = user.create_repo(
                    repo_name,
                    description=description,
                    private=False,
                    auto_init=False
                )
                # Add remote
                repo.create_remote("origin", gh_repo.clone_url)
                logger.info(f"Created GitHub repo: {gh_repo.html_url}")
            except Exception as e:
                logger.warning(f"Could not create GitHub repo: {e}")

        return repo

    def _clone_repo(self, repo_path: Path, repo_name: str) -> GitRepo:
        """Clone an existing repository.

        Args:
            repo_path: Local path for the repo
            repo_name: Name of the repository

        Returns:
            GitRepo object
        """
        clone_url = f"git@github.com:{self.base_org}/{repo_name}.git"

        if repo_path.exists():
            # Already cloned, just open it
            return GitRepo(repo_path)

        repo = GitRepo.clone_from(clone_url, repo_path)
        logger.info(f"Cloned {clone_url}")
        return repo

    def _write_skill_file(self, file_path: Path, skill: Skill) -> None:
        """Write a skill file with metadata header.

        Args:
            file_path: Path to write the file
            skill: Skill to write
        """
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

        readme_content = f"""# {plan.repo_name}

{plan.description}

## Overview

This repository contains **{total_skills} AI-powered skills** organized into {len(folder_counts)} categories.

## Categories

"""

        for folder, count in sorted(folder_counts.items()):
            folder_display = folder.replace("-", " ").title()
            readme_content += f"- **{folder_display}**: {count} skill{'s' if count != 1 else ''}\n"

        readme_content += f"""

## About This Collection

These skills were automatically aggregated from various open-source repositories.
Each skill file includes metadata about its source and purpose.

## Skill Structure

```
{plan.repo_name}/
"""

        for folder in sorted(folder_counts.keys()):
            readme_content += f"├── {folder}/\n"

        readme_content += f"""```

## Usage

These skills can be used with AI assistants like Claude Code to automate
various tasks related to {plan.category}.

---

*Last updated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}*
*Aggregated by [SkillFlow](https://github.com/tools-only/SkillFlow)*
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
        repo.git.add(A=True)

        # Check if there are changes to commit
        if repo.is_dirty() or repo.untracked_files:
            skill_count = len(plan.skills)
            message = f"Add/Update {skill_count} skill(s)\n\nCategories: {', '.join(plan.folder_structure.keys())}\n\nAutomated update by SkillFlow Repo Maintainer"

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
                    logger.error(f"Push error: {info.name}")
                else:
                    logger.info(f"Pushed to {repo_name}: {info.name}")
        except GitCommandError as e:
            logger.error(f"Git push error: {e}")

    def get_all_repos(self) -> List[str]:
        """Get list of all managed repositories.

        Returns:
            List of repository names
        """
        if not self.github:
            return [d.name for d in self.work_dir.iterdir() if d.is_dir()]

        repos = []
        try:
            user = self.github.get_user()
            for repo in user.get_repos():
                if repo.name.endswith("Skills") or repo.name in self.KNOWN_REPOS:
                    repos.append(repo.name)
        except Exception as e:
            logger.error(f"Error listing repos: {e}")

        return repos


# Convenience function for Claude Code to call
def process_skills(
    skills_data: List[Dict[str, Any]],
    github_token: Optional[str] = None,
    org: str = "tools-only",
    push: bool = True
) -> Dict[str, str]:
    """Process a list of skills and organize them into repositories.

    This is the main entry point for Claude Code to call.

    Args:
        skills_data: List of skill dictionaries with keys:
            - name: str
            - content: str
            - source_repo: str
            - source_path: str
            - source_url: str
            - file_hash: str
            - metadata: dict
        github_token: GitHub token (optional, reads from GITHUB_TOKEN env var)
        org: GitHub organization/username
        push: Whether to push to GitHub

    Returns:
        Dict mapping repo names to local paths
    """
    # Convert dict data to Skill objects
    skills = [Skill(**data) for data in skills_data]

    # Create agent
    agent = RepoMaintainerAgent(github_token=github_token, base_org=org)

    # Analyze and plan
    plans = agent.analyze_and_plan(skills)

    # Execute plans
    results = {}
    for plan in plans:
        logger.info(f"Processing: {plan.repo_name}")
        repo_path = agent.execute_plan(plan, push=push)
        results[plan.repo_name] = repo_path

        if push:
            logger.info(f"✓ {plan.repo_name}: {len(plan.skills)} skills")

    return results


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
        results = process_skills(skills_list)
        print(json.dumps(results, indent=2))
    else:
        print("Usage: python -m src.repo_maintainer <skill_file1.md> <skill_file2.md> ...")
