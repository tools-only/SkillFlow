"""Update Planner module for generating and executing update plans.

This module handles the creation, validation, and execution of
structured update plans based on requirements extracted from Issues.
"""

import logging
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from enum import Enum


logger = logging.getLogger(__name__)


# ========== Data Classes ==========

class PlanType(Enum):
    """Types of update plans."""
    ADD_REPOS = "add_repos"
    REMOVE_REPOS = "remove_repos"
    UPDATE_TERMS = "update_terms"
    UPDATE_CONFIG = "update_config"
    SYNC_REPO = "sync_repo"
    BATCH_UPDATE = "batch_update"


class ExecutionStatus(Enum):
    """Plan execution status."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RepoUpdatePlan:
    """Repository update plan.

    This represents a structured plan for updating the SkillFlow
    repository based on requirements from GitHub Issues.
    """
    plan_id: str
    plan_type: str  # PlanType value
    source_issue: int  # GitHub issue number

    # Data fields
    repos_to_add: List[str] = field(default_factory=list)
    repos_to_remove: List[str] = field(default_factory=list)
    search_terms_to_add: List[str] = field(default_factory=list)
    search_terms_to_remove: List[str] = field(default_factory=list)
    config_updates: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    priority: int = 5  # 1-10, 10 highest
    notes: str = ""
    execution_status: str = "pending"
    execution_result: Optional[str] = None
    executed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert plan to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepoUpdatePlan":
        """Create plan from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "RepoUpdatePlan":
        """Create plan from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class ExecutionResult:
    """Result of plan execution."""
    success: bool
    plan_id: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    executed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return asdict(self)


# ========== Update Planner ==========

class UpdatePlanner:
    """Generate update plans from requirements."""

    def __init__(self, config=None):
        """Initialize update planner.

        Args:
            config: Optional Config object for accessing system settings
        """
        self.config = config

    def generate_plan(self, source_issue: int, requirements: List[Dict],
                      issue_data: Dict = None) -> RepoUpdatePlan:
        """Generate an update plan from extracted requirements.

        Args:
            source_issue: Source issue number
            requirements: List of extracted requirements
            issue_data: Optional additional issue data for context

        Returns:
            RepoUpdatePlan object
        """
        plan = RepoUpdatePlan(
            plan_id=str(uuid.uuid4())[:8],
            plan_type="batch_update",
            source_issue=source_issue,
            created_at=datetime.utcnow().isoformat(),
        )

        # Group requirements by type
        repos_to_add = []
        repos_to_remove = []
        terms_to_add = []
        terms_to_remove = []
        config_updates = {}

        for req in requirements:
            req_type = req.get("type", "")
            req_data = req.get("data", {})

            if req_type == "repo-request":
                repo = req_data.get("repository", "")
                if repo:
                    repos_to_add.append(repo)

            elif req_type == "remove-repo":
                repo = req_data.get("repository", "")
                if repo:
                    repos_to_remove.append(repo)

            elif req_type == "search-terms":
                terms = req_data.get("terms", [])
                if isinstance(terms, list):
                    terms_to_add.extend(terms)
                elif isinstance(terms, str):
                    terms_to_add.append(terms)

            elif req_type == "config-update":
                config_updates.update(req_data)

        # Determine plan type based on content
        if repos_to_add and not terms_to_add and not config_updates:
            plan.plan_type = PlanType.ADD_REPOS.value
        elif repos_to_remove and not repos_to_add and not terms_to_add:
            plan.plan_type = PlanType.REMOVE_REPOS.value
        elif terms_to_add and not repos_to_add:
            plan.plan_type = PlanType.UPDATE_TERMS.value
        elif config_updates and not repos_to_add and not terms_to_add:
            plan.plan_type = PlanType.UPDATE_CONFIG.value
        else:
            plan.plan_type = PlanType.BATCH_UPDATE.value

        # Populate plan data
        plan.repos_to_add = self._deduplicate(repos_to_add)
        plan.repos_to_remove = self._deduplicate(repos_to_remove)
        plan.search_terms_to_add = self._deduplicate(terms_to_add)
        plan.search_terms_to_remove = self._deduplicate(terms_to_remove)
        plan.config_updates = config_updates

        # Set priority based on issue data
        plan.priority = self._estimate_priority(issue_data or {}, requirements)

        # Generate notes
        plan.notes = self._generate_notes(plan, requirements)

        logger.info(f"Generated plan {plan.plan_id} of type {plan.plan_type} from issue #{source_issue}")
        return plan

    def validate_plan(self, plan: RepoUpdatePlan) -> tuple[bool, List[str]]:
        """Validate a plan for correctness and safety.

        Args:
            plan: Plan to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check plan ID
        if not plan.plan_id:
            errors.append("Plan ID is required")

        # Check source issue
        if plan.source_issue <= 0:
            errors.append("Source issue number must be positive")

        # Check plan type
        valid_types = [t.value for t in PlanType]
        if plan.plan_type not in valid_types:
            errors.append(f"Invalid plan type: {plan.plan_type}")

        # Check that plan has some content
        has_content = (
            plan.repos_to_add or
            plan.repos_to_remove or
            plan.search_terms_to_add or
            plan.search_terms_to_remove or
            plan.config_updates
        )
        if not has_content:
            errors.append("Plan must contain at least one update action")

        # Validate repository names
        for repo in plan.repos_to_add + plan.repos_to_remove:
            if not self._is_valid_repo_name(repo):
                errors.append(f"Invalid repository name: {repo}")

        # Validate search terms
        for term in plan.search_terms_to_add + plan.search_terms_to_remove:
            if not isinstance(term, str) or len(term) < 2:
                errors.append(f"Invalid search term: {term}")

        # Check priority range
        if not 1 <= plan.priority <= 10:
            errors.append("Priority must be between 1 and 10")

        return (len(errors) == 0, errors)

    def estimate_priority(self, issue_data: Dict, requirements: List[Dict]) -> int:
        """Calculate plan priority (legacy method, use _estimate_priority).

        Args:
            issue_data: Issue metadata
            requirements: List of requirements

        Returns:
            Priority value 1-10
        """
        return self._estimate_priority(issue_data, requirements)

    def _estimate_priority(self, issue_data: Dict, requirements: List[Dict]) -> int:
        """Calculate priority based on issue attributes.

        Args:
            issue_data: Issue metadata
            requirements: List of requirements

        Returns:
            Priority value 1-10
        """
        priority = 5  # Default

        # Boost for feature requests
        if issue_data.get("labels"):
            labels = [l.lower() for l in issue_data["labels"]]
            if "enhancement" in labels or "feature" in labels:
                priority += 1
            if "bug" in labels:
                priority += 2
            if "priority" in labels or "important" in labels:
                priority += 2

        # Boost based on number of repositories
        repo_count = sum(1 for r in requirements if r.get("type") == "repo-request")
        if repo_count > 5:
            priority += 1
        if repo_count > 10:
            priority += 1

        # Boost based on issue reactions
        reactions = issue_data.get("reactions", {})
        total_reactions = (
            reactions.get("+1", 0) +
            reactions.get("heart", 0) +
            reactions.get("hooray", 0)
        )
        if total_reactions > 5:
            priority += 1
        if total_reactions > 10:
            priority += 1

        # Clamp to valid range
        return max(1, min(10, priority))

    def merge_plans(self, plans: List[RepoUpdatePlan]) -> RepoUpdatePlan:
        """Merge multiple plans into a single batch update plan.

        Args:
            plans: List of plans to merge

        Returns:
            Merged plan
        """
        if not plans:
            raise ValueError("Cannot merge empty plan list")

        if len(plans) == 1:
            return plans[0]

        # Use the highest priority and earliest created_at
        merged = RepoUpdatePlan(
            plan_id=str(uuid.uuid4())[:8],
            plan_type=PlanType.BATCH_UPDATE.value,
            source_issue=min(p.source_issue for p in plans),  # Earliest issue
            created_at=min(p.created_at for p in plans),
            priority=max(p.priority for p in plans),
            notes=f"Merged from {len(plans)} plans",
        )

        # Combine all data
        for plan in plans:
            merged.repos_to_add.extend(plan.repos_to_add)
            merged.repos_to_remove.extend(plan.repos_to_remove)
            merged.search_terms_to_add.extend(plan.search_terms_to_add)
            merged.search_terms_to_remove.extend(plan.search_terms_to_remove)
            merged.config_updates.update(plan.config_updates)

        # Deduplicate
        merged.repos_to_add = self._deduplicate(merged.repos_to_add)
        merged.repos_to_remove = self._deduplicate(merged.repos_to_remove)
        merged.search_terms_to_add = self._deduplicate(merged.search_terms_to_add)
        merged.search_terms_to_remove = self._deduplicate(merged.search_terms_to_remove)

        logger.info(f"Merged {len(plans)} plans into {merged.plan_id}")
        return merged

    def _deduplicate(self, items: List[str]) -> List[str]:
        """Remove duplicates while preserving order."""
        seen = set()
        result = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    def _is_valid_repo_name(self, repo: str) -> bool:
        """Check if a repository name is valid."""
        if not isinstance(repo, str):
            return False

        # Should be in format "owner/repo"
        parts = repo.split("/")
        if len(parts) != 2:
            return False

        owner, name = parts
        if not owner or not name:
            return False

        # Basic validation
        if len(owner) > 39 or len(name) > 100:
            return False

        # Check for valid characters
        import re
        repo_pattern = r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$"
        return bool(re.match(repo_pattern, repo))

    def _generate_notes(self, plan: RepoUpdatePlan, requirements: List[Dict]) -> str:
        """Generate human-readable notes for the plan."""
        parts = []

        if plan.repos_to_add:
            parts.append(f"Add {len(plan.repos_to_add)} repo(s)")

        if plan.repos_to_remove:
            parts.append(f"Remove {len(plan.repos_to_remove)} repo(s)")

        if plan.search_terms_to_add:
            parts.append(f"Add {len(plan.search_terms_to_add)} search term(s)")

        if plan.config_updates:
            parts.append(f"Update {len(plan.config_updates)} config value(s)")

        if not parts:
            return "No changes (empty plan)"

        return "; ".join(parts)


# ========== Plan Executor ==========

class PlanExecutor:
    """Execute update plans via the repo_maintainer."""

    def __init__(self, repo_maintainer=None, tracker=None, config=None):
        """Initialize plan executor.

        Args:
            repo_maintainer: RepoMaintainerAgent instance
            tracker: Tracker instance for database updates
            config: Config instance
        """
        self.repo_maintainer = repo_maintainer
        self.tracker = tracker
        self.config = config

    def execute_plan(self, plan: RepoUpdatePlan) -> ExecutionResult:
        """Execute an update plan.

        Args:
            plan: Plan to execute

        Returns:
            ExecutionResult with outcome
        """
        logger.info(f"Executing plan {plan.plan_id} (type: {plan.plan_type})")

        plan.execution_status = ExecutionStatus.EXECUTING.value

        try:
            details = {}

            # Execute based on plan type
            if plan.plan_type == PlanType.ADD_REPOS.value or (
                plan.plan_type == PlanType.BATCH_UPDATE.value and plan.repos_to_add
            ):
                result = self._execute_add_repos(plan, details)
                if not result:
                    raise Exception("Failed to add repositories")

            if plan.plan_type == PlanType.REMOVE_REPOS.value or (
                plan.plan_type == PlanType.BATCH_UPDATE.value and plan.repos_to_remove
            ):
                result = self._execute_remove_repos(plan, details)
                if not result:
                    raise Exception("Failed to remove repositories")

            if plan.plan_type == PlanType.UPDATE_TERMS.value or (
                plan.plan_type == PlanType.BATCH_UPDATE.value and plan.search_terms_to_add
            ):
                result = self._execute_update_terms(plan, details)
                if not result:
                    raise Exception("Failed to update search terms")

            if plan.plan_type == PlanType.UPDATE_CONFIG.value or (
                plan.plan_type == PlanType.BATCH_UPDATE.value and plan.config_updates
            ):
                result = self._execute_update_config(plan, details)
                if not result:
                    raise Exception("Failed to update configuration")

            # Update plan status
            plan.execution_status = ExecutionStatus.COMPLETED.value
            plan.executed_at = datetime.utcnow().isoformat()
            plan.execution_result = json.dumps(details)

            # Update tracker if available
            if self.tracker:
                self.tracker.update_plan_status(
                    plan.source_issue,
                    ExecutionStatus.COMPLETED.value,
                    execution_result=plan.execution_result
                )

            logger.info(f"Plan {plan.plan_id} executed successfully")

            return ExecutionResult(
                success=True,
                plan_id=plan.plan_id,
                message=f"Plan executed successfully: {plan.notes}",
                details=details,
            )

        except Exception as e:
            logger.error(f"Plan {plan.plan_id} execution failed: {e}")
            plan.execution_status = ExecutionStatus.FAILED.value
            plan.executed_at = datetime.utcnow().isoformat()
            plan.execution_result = json.dumps({"error": str(e)})

            if self.tracker:
                self.tracker.update_plan_status(
                    plan.source_issue,
                    ExecutionStatus.FAILED.value,
                    execution_result=str(e)
                )

            return ExecutionResult(
                success=False,
                plan_id=plan.plan_id,
                message=f"Plan execution failed: {str(e)}",
                error=str(e),
            )

    def _execute_add_repos(self, plan: RepoUpdatePlan, details: Dict) -> bool:
        """Execute add repositories action.

        Args:
            plan: Update plan
            details: Details dict to update with results

        Returns:
            True if successful
        """
        # Add repos to excluded list to prevent auto-processing
        # They will be processed in the next pipeline run
        if self.config:
            excluded = self.config.excluded_repos
            for repo in plan.repos_to_add:
                if repo not in excluded:
                    excluded.append(repo)

            # Update config file
            self._update_excluded_repos(excluded)

        details["added_repos"] = plan.repos_to_add
        return True

    def _execute_remove_repos(self, plan: RepoUpdatePlan, details: Dict) -> bool:
        """Execute remove repositories action.

        Args:
            plan: Update plan
            details: Details dict to update with results

        Returns:
            True if successful
        """
        if self.config:
            excluded = self.config.excluded_repos
            for repo in plan.repos_to_remove:
                if repo in excluded:
                    excluded.remove(repo)

            # Update config file
            self._update_excluded_repos(excluded)

        details["removed_repos"] = plan.repos_to_remove
        return True

    def _execute_update_terms(self, plan: RepoUpdatePlan, details: Dict) -> bool:
        """Execute update search terms action.

        Args:
            plan: Update plan
            details: Details dict to update with results

        Returns:
            True if successful
        """
        if self.config:
            search_terms = self.config.search_terms
            for term in plan.search_terms_to_add:
                if term not in search_terms:
                    search_terms.append(term)

            # Update config file
            self._update_search_terms(search_terms)

        details["added_terms"] = plan.search_terms_to_add
        return True

    def _execute_update_config(self, plan: RepoUpdatePlan, details: Dict) -> bool:
        """Execute update configuration action.

        Args:
            plan: Update plan
            details: Details dict to update with results

        Returns:
            True if successful
        """
        # This would update the config.yaml file
        # For now, just track what would be updated
        details["config_updates"] = plan.config_updates
        logger.info(f"Config updates requested: {plan.config_updates}")
        return True

    def _update_excluded_repos(self, repos: List[str]) -> None:
        """Update the excluded repos in config file."""
        import yaml
        from pathlib import Path

        config_path = Path("config/search_terms.yaml")
        if not config_path.exists():
            return

        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)

            data["excluded_repos"] = repos

            with open(config_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)

            logger.info(f"Updated excluded_repos in config")
        except Exception as e:
            logger.error(f"Failed to update excluded_repos: {e}")

    def _update_search_terms(self, terms: List[str]) -> None:
        """Update the search terms in config file."""
        import yaml
        from pathlib import Path

        config_path = Path("config/search_terms.yaml")
        if not config_path.exists():
            return

        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)

            data["terms"] = terms

            with open(config_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)

            logger.info(f"Updated search terms in config")
        except Exception as e:
            logger.error(f"Failed to update search terms: {e}")
