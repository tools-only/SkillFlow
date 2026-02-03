"""Pull Request Handler module for processing community skill submissions.

This module handles PR validation, duplicate detection, and
automatic merging of skill submissions.
"""

import logging
import hashlib
import re
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from github import Github
from github.PullRequest import PullRequest as GithubPR
from github.File import File as GithubFile

from .config import Config
from .tracker import Tracker, PRInfo


logger = logging.getLogger(__name__)


# ========== Data Classes ==========

@dataclass
class PRSkillFile:
    """A skill file from a PR."""
    path: str
    content: str
    metadata: Dict[str, Any]
    hash: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of PR validation."""
    is_valid: bool
    can_auto_merge: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    skill_files: List[PRSkillFile] = field(default_factory=list)
    duplicate_count: int = 0


@dataclass
class PRProcessingResult:
    """Result of PR processing."""
    pr_number: int
    status: str  # 'validated', 'approved', 'rejected', 'merged'
    validation_result: Optional[ValidationResult] = None
    merged: bool = False
    comment_posted: bool = False
    error_message: Optional[str] = None


# ========== PR Validator ==========

class PRValidator:
    """Validate Pull Requests for skill submissions."""

    def __init__(self, config: Config, tracker: Tracker):
        """Initialize PR validator.

        Args:
            config: Configuration object
            tracker: Tracker for checking duplicates
        """
        self.config = config
        self.tracker = tracker
        self.required_files = config.pr_required_files

        # YAML frontmatter pattern
        self.frontmatter_pattern = re.compile(
            r"^---\s*\n(.*?)\n---\s*\n(.*)",
            re.DOTALL
        )

    def validate_pr(self, pr: GithubPR, files: List[GithubFile]) -> ValidationResult:
        """Validate a PR for skill submission.

        Args:
            pr: GitHub Pull Request object
            files: List of files in the PR

        Returns:
            ValidationResult with validation details
        """
        result = ValidationResult(
            is_valid=True,
            can_auto_merge=False,
        )

        # Check PR state
        if pr.state != "open":
            result.errors.append(f"PR is not open (state: {pr.state})")
            result.is_valid = False
            return result

        # Extract skill files
        skill_files = self._extract_skill_files(files)
        result.skill_files = skill_files

        # Check for required files
        self._validate_required_files(skill_files, result)

        # Validate file structures
        for skill_file in skill_files:
            self._validate_skill_file(skill_file, result)

        # Check for duplicates
        duplicate_count = self._check_duplicates(skill_files, result)
        result.duplicate_count = duplicate_count

        # Check if auto-merge is possible
        result.can_auto_merge = (
            result.is_valid and
            result.duplicate_count == 0 and
            len(result.errors) == 0 and
            self._has_auto_merge_label(pr)
        )

        return result

    def _extract_skill_files(self, files: List[GithubFile]) -> List[PRSkillFile]:
        """Extract and parse skill files from PR files.

        Args:
            files: List of GitHub file objects

        Returns:
            List of PRSkillFile objects
        """
        skill_files = []
        skill_dirs = set()

        # Find skill directories (should contain skill.md)
        for file in files:
            if file.filename.endswith("skill.md"):
                parts = file.filename.split("/")
                if len(parts) >= 2:
                    skill_dirs.add("/".join(parts[:-1]))

        # Extract all files from skill directories
        for skill_dir in skill_dirs:
            skill_md = None
            readme_md = None

            for file in files:
                if file.filename.startswith(skill_dir):
                    if file.filename.endswith("skill.md"):
                        skill_md = file
                    elif file.filename.endswith("README.md"):
                        readme_md = file

            if skill_md and readme_md:
                # Fetch content
                try:
                    skill_content = self._get_file_content(skill_md)
                    readme_content = self._get_file_content(readme_md)

                    # Parse metadata from README or skill.md
                    metadata = self._parse_metadata(readme_content, skill_content)

                    # Compute hash
                    combined = skill_content + readme_content
                    file_hash = hashlib.sha256(combined.encode()).hexdigest()

                    skill_file = PRSkillFile(
                        path=skill_dir,
                        content=skill_content,
                        metadata=metadata,
                        hash=file_hash,
                        is_valid=True,
                    )
                    skill_files.append(skill_file)

                except Exception as e:
                    logger.error(f"Error extracting skill files from {skill_dir}: {e}")

        return skill_files

    def _validate_required_files(self, skill_files: List[PRSkillFile],
                                  result: ValidationResult) -> None:
        """Validate that required files are present."""
        if not skill_files:
            result.errors.append(
                f"No valid skill submissions found. "
                f"Required structure: category-name/skill-name_hash/ with skill.md and README.md"
            )
            result.is_valid = False

    def _validate_skill_file(self, skill_file: PRSkillFile,
                             result: ValidationResult) -> None:
        """Validate a single skill file."""
        # Check content is not empty
        if not skill_file.content or len(skill_file.content) < 50:
            skill_file.is_valid = False
            skill_file.errors.append("Skill content is too short or empty")
            result.is_valid = False

        # Check metadata
        if not skill_file.metadata:
            result.warnings.append("No metadata found in README.md or skill.md")
        else:
            # Check required metadata fields
            required_fields = ["name", "description"]
            for field in required_fields:
                if field not in skill_file.metadata or not skill_file.metadata[field]:
                    skill_file.errors.append(f"Missing required metadata field: {field}")
                    result.is_valid = False

        # Check for YAML frontmatter syntax errors
        if "---" in skill_file.content:
            try:
                self._parse_frontmatter(skill_file.content)
            except Exception as e:
                skill_file.errors.append(f"YAML frontmatter parse error: {e}")
                result.is_valid = False

    def _check_duplicates(self, skill_files: List[PRSkillFile],
                          result: ValidationResult) -> int:
        """Check for duplicate skill files."""
        duplicate_count = 0

        for skill_file in skill_files:
            if self.tracker.is_already_processed(skill_file.hash):
                duplicate_count += 1
                result.errors.append(
                    f"Duplicate skill found: {skill_file.path} "
                    f"(hash: {skill_file.hash[:16]}...)"
                )

        if duplicate_count > 0:
            result.is_valid = False

        return duplicate_count

    def _has_auto_merge_label(self, pr: GithubPR) -> bool:
        """Check if PR has auto-merge label."""
        auto_merge_label = self.config.pr_auto_merge_label
        labels = [label.name for label in pr.labels]
        return auto_merge_label in labels

    def _get_file_content(self, file: GithubFile) -> str:
        """Get file content from GitHub file object."""
        # Decode base64 content
        import base64
        return base64.b64decode(file.content).decode('utf-8')

    def _parse_metadata(self, readme_content: str, skill_content: str) -> Dict[str, Any]:
        """Parse metadata from README or skill.md YAML frontmatter."""
        # Try README first
        for content in [readme_content, skill_content]:
            match = self.frontmatter_pattern.match(content)
            if match:
                try:
                    import yaml
                    metadata = yaml.safe_load(match.group(1))
                    if isinstance(metadata, dict):
                        return metadata
                except Exception:
                    pass

        return {}

    def _parse_frontmatter(self, content: str) -> Dict[str, Any]:
        """Parse YAML frontmatter from content."""
        match = self.frontmatter_pattern.match(content)
        if match:
            import yaml
            return yaml.safe_load(match.group(1)) or {}
        return {}


# ========== PR Handler ==========

class PRHandler:
    """Handle Pull Request processing."""

    def __init__(self, config: Config, tracker: Tracker, github_token: str = None,
                 repo_name: str = None):
        """Initialize PR handler.

        Args:
            config: Configuration object
            tracker: Tracker instance
            github_token: GitHub API token
            repo_name: Repository name (owner/repo)
        """
        self.config = config
        self.tracker = tracker
        self.github_token = github_token or config.github_token
        self.repo_name = repo_name

        # Initialize GitHub client
        if self.github_token:
            self.github = Github(self.github_token)
        else:
            self.github = None

        # Initialize validator
        self.validator = PRValidator(config, tracker)

        logger.info("PRHandler initialized")

    def fetch_new_prs(self) -> List[PRInfo]:
        """Fetch new pull requests from the repository.

        Returns:
            List of PRInfo objects for unprocessed PRs
        """
        if not self.github or not self.repo_name:
            logger.warning("GitHub client or repo_name not configured")
            return []

        try:
            repo = self.github.get_repo(self.repo_name)

            # Get open PRs
            prs = repo.get_pulls(state="open")

            new_prs = []

            for pr in prs:
                # Check if already tracked
                existing = self.tracker.get_pr(pr.number)
                if existing:
                    continue

                # Create PRInfo
                pr_info = PRInfo(
                    pr_number=pr.number,
                    pr_title=pr.title,
                    pr_author=pr.user.login if pr.user else "unknown",
                    pr_state=pr.state,
                    head_ref=pr.head.ref,
                    base_ref=pr.base.ref,
                    created_at=pr.created_at.isoformat() if pr.created_at else datetime.utcnow().isoformat(),
                    updated_at=pr.updated_at.isoformat() if pr.updated_at else datetime.utcnow().isoformat(),
                    processing_status="pending",
                )

                # Track in database
                self.tracker.add_pr(pr_info)
                new_prs.append(pr_info)

                logger.info(f"Found new PR #{pr.number}: {pr.title}")

            return new_prs

        except Exception as e:
            logger.error(f"Error fetching PRs: {e}")
            return []

    def process_pr(self, pr_info: PRInfo) -> PRProcessingResult:
        """Process a single PR.

        Args:
            pr_info: PR to process

        Returns:
            PRProcessingResult
        """
        if not self.github or not self.repo_name:
            return PRProcessingResult(
                pr_number=pr_info.pr_number,
                status="rejected",
                error_message="GitHub client not configured"
            )

        logger.info(f"Processing PR #{pr_info.pr_number}")

        try:
            repo = self.github.get_repo(self.repo_name)
            pr = repo.get_pull(pr_info.pr_number)

            # Get PR files
            files = list(pr.get_files())

            # Validate PR
            validation = self.validator.validate_pr(pr, files)

            # Update PR status in tracker
            self.tracker.update_pr_status(
                pr_info.pr_number,
                "validated" if validation.is_valid else "rejected",
                validation_results=json.dumps({
                    "is_valid": validation.is_valid,
                    "can_auto_merge": validation.can_auto_merge,
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                    "skill_count": len(validation.skill_files),
                    "duplicate_count": validation.duplicate_count,
                }),
                skill_files_added=json.dumps([
                    {"path": f.path, "hash": f.hash}
                    for f in validation.skill_files
                ])
            )

            # Post validation comment
            self._post_validation_comment(pr, validation)

            # Auto-merge if possible
            merged = False
            if validation.can_auto_merge and self.config.pr_validation_required:
                merged = self._auto_merge(pr, validation)

            # Determine final status
            if merged:
                status = "merged"
            elif validation.is_valid:
                status = "approved"
            else:
                status = "rejected"

            result = PRProcessingResult(
                pr_number=pr_info.pr_number,
                status=status,
                validation_result=validation,
                merged=merged,
                comment_posted=True,
            )

            # Update final status
            self.tracker.update_pr_status(
                pr_info.pr_number,
                status
            )

            return result

        except Exception as e:
            logger.error(f"Error processing PR #{pr_info.pr_number}: {e}")
            self.tracker.update_pr_status(
                pr_info.pr_number,
                "rejected",
                error_message=str(e)
            )

            return PRProcessingResult(
                pr_number=pr_info.pr_number,
                status="rejected",
                error_message=str(e)
            )

    def process_pending_prs(self, max_prs: int = 10) -> Dict[str, Any]:
        """Process all pending PRs.

        Args:
            max_prs: Maximum number of PRs to process

        Returns:
            Dictionary with processing results
        """
        logger.info("Processing pending PRs")

        results = {
            "fetched": 0,
            "processed": 0,
            "approved": 0,
            "rejected": 0,
            "merged": 0,
            "errors": 0,
            "details": [],
        }

        # Fetch new PRs
        new_prs = self.fetch_new_prs()[:max_prs]
        results["fetched"] = len(new_prs)

        # Get pending PRs from database
        pending_prs = self.tracker.get_pending_prs("pending")

        # Combine and limit
        all_pending = new_prs + [p for p in pending_prs if p not in new_prs]
        all_pending = all_pending[:max_prs]

        for pr_info in all_pending:
            try:
                result = self.process_pr(pr_info)

                results["processed"] += 1
                results[f"{result.status}"] = results.get(result.status, 0) + 1

                results["details"].append({
                    "pr_number": pr_info.pr_number,
                    "title": pr_info.pr_title,
                    "status": result.status,
                    "merged": result.merged,
                })

            except Exception as e:
                logger.error(f"Error processing PR #{pr_info.pr_number}: {e}")
                results["errors"] += 1

        logger.info(f"PR processing complete: {results}")
        return results

    def _post_validation_comment(self, pr: GithubPR, validation: ValidationResult) -> bool:
        """Post validation comment on PR.

        Args:
            pr: GitHub PR object
            validation: Validation result

        Returns:
            True if comment posted successfully
        """
        try:
            # Build comment
            if validation.is_valid:
                if validation.can_auto_merge:
                    comment = f"""## ✅ PR Validated - Auto-Merging

This PR has been validated and meets all requirements for auto-merge.

**Validation Results:**
- ✅ All required files present
- ✅ No duplicate skills found
- ✅ Auto-merge label detected
- ✅ All validation checks passed

**Skills in this PR:** {len(validation.skill_files)}

The PR will be merged automatically. 🚀
"""
                else:
                    comment = f"""## ✅ PR Validated

This PR has been validated and is ready for review.

**Validation Results:**
- ✅ All required files present
- ✅ No duplicate skills found
- ✅ All validation checks passed

**Skills in this PR:** {len(validation.skill_files)}

"""
                    if validation.warnings:
                        comment += "\n**Warnings:**\n"
                        for warning in validation.warnings:
                            comment += f"- ⚠️ {warning}\n"

                    comment += "\nTo enable auto-merge, add the `auto-merge` label."
            else:
                comment = "## ❌ PR Validation Failed\n\n"
                comment += "This PR has validation errors that must be fixed:\n\n"

                for error in validation.errors:
                    comment += f"- ❌ {error}\n"

                if validation.warnings:
                    comment += "\n**Warnings:**\n"
                    for warning in validation.warnings:
                        comment += f"- ⚠️ {warning}\n"

            pr.create_comment(comment)
            logger.info(f"Posted validation comment on PR #{pr.number}")
            return True

        except Exception as e:
            logger.error(f"Error posting comment on PR #{pr.number}: {e}")
            return False

    def _auto_merge(self, pr: GithubPR, validation: ValidationResult) -> bool:
        """Auto-merge a PR.

        Args:
            pr: GitHub PR object
            validation: Validation result

        Returns:
            True if merged successfully
        """
        try:
            # Merge PR
            pr.merge(
                commit_title=f"Auto-merge PR #{pr.number}: {pr.title}",
                commit_message="Automatically merged by SkillFlow PR Handler",
                merge_method="merge"
            )

            logger.info(f"Auto-merged PR #{pr.number}")
            return True

        except Exception as e:
            logger.error(f"Error auto-merging PR #{pr.number}: {e}")

            # Post error comment
            try:
                pr.create_comment(
                    f"## ⚠️ Auto-Merge Failed\n\n"
                    f"Validation passed but auto-merge failed:\n"
                    f"```\n{e}\n```\n\n"
                    f"Please merge manually."
                )
            except Exception:
                pass

            return False


# ========== Standalone Functions ==========

def check_prs(config: Config, max_prs: int = 10) -> Dict[str, Any]:
    """Check Pull Requests (standalone function).

    Args:
        config: Configuration object
        max_prs: Maximum PRs to process

    Returns:
        Processing results dictionary
    """
    tracker = Tracker(config)
    handler = PRHandler(
        config=config,
        tracker=tracker,
        repo_name=config.get("pull_requests.repo_name", ""),
    )

    return handler.process_pending_prs(max_prs=max_prs)
