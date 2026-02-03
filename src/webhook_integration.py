"""Webhook Integration - Connects webhook events to processors.

This module provides integration between the webhook server and the
IssueMaintainerAgent and PRHandler for real-time event processing.
"""

import logging
import threading
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .config import Config
from .tracker import Tracker
from .webhook_handler import WebhookEventHandler, WebhookContext
from .issue_maintainer import IssueMaintainerAgent
from .pr_handler import PRHandler


logger = logging.getLogger(__name__)


@dataclass
class ProcessingStats:
    """Statistics for event processing."""
    issues_processed: int = 0
    prs_processed: int = 0
    errors: int = 0
    last_processed_at: str = ""


class WebhookIntegration:
    """Integrates webhook events with issue and PR processors.

    This class:
    1. Registers category processors with WebhookEventHandler
    2. Processes issues through IssueMaintainerAgent
    3. Processes PRs through PRHandler
    4. Tracks processing statistics
    """

    def __init__(
        self,
        config: Config,
        tracker: Tracker,
        webhook_handler: WebhookEventHandler,
        repo_name: str = None,
    ):
        """Initialize webhook integration.

        Args:
            config: Configuration object
            tracker: Tracker instance
            webhook_handler: WebhookEventHandler to integrate with
            repo_name: Repository name (owner/repo) for GitHub API
        """
        self.config = config
        self.tracker = tracker
        self.webhook_handler = webhook_handler
        self.repo_name = repo_name or config.get("issues.repo_name", "")

        # Initialize processors
        self.issue_agent: Optional[IssueMaintainerAgent] = None
        self.pr_handler: Optional[PRHandler] = None

        # Statistics
        self.stats = ProcessingStats()
        self._lock = threading.Lock()

        # Processing flag
        self._processing_enabled = True

        logger.info("WebhookIntegration initialized")

    def setup_processors(self) -> None:
        """Setup and register category processors."""
        # Initialize IssueMaintainerAgent
        if self.config.get("issues.enabled", True):
            try:
                self.issue_agent = IssueMaintainerAgent(
                    config=self.config,
                    repo_name=self.repo_name,
                )
                logger.info("IssueMaintainerAgent initialized")
            except Exception as e:
                logger.error(f"Failed to initialize IssueMaintainerAgent: {e}")

        # Initialize PRHandler
        if self.config.get("pull_requests.enabled", True):
            try:
                self.pr_handler = PRHandler(
                    config=self.config,
                    tracker=self.tracker,
                    repo_name=self.repo_name,
                )
                logger.info("PRHandler initialized")
            except Exception as e:
                logger.error(f"Failed to initialize PRHandler: {e}")

        # Register category processors
        self._register_processors()

    def _register_processors(self) -> None:
        """Register category processors with webhook handler."""

        def process_repo_request(context: WebhookContext, category: str) -> Dict[str, Any]:
            """Process repo-request events."""
            return self._process_issue_event(context, category)

        def process_skill_submission(context: WebhookContext, category: str) -> Dict[str, Any]:
            """Process skill-submission (PR) events."""
            return self._process_pr_event(context, category)

        def process_bug(context: WebhookContext, category: str) -> Dict[str, Any]:
            """Process bug report events."""
            return self._process_issue_event(context, category)

        def process_feature(context: WebhookContext, category: str) -> Dict[str, Any]:
            """Process feature request events."""
            return self._process_issue_event(context, category)

        def process_other(context: WebhookContext, category: str) -> Dict[str, Any]:
            """Process uncategorized events."""
            logger.info(f"Processing uncategorized event: {context.event_type}")
            return {"success": True, "status": "ignored", "category": category}

        # Register processors
        self.webhook_handler.set_category_processor("repo-request", process_repo_request)
        self.webhook_handler.set_category_processor("skill-submission", process_skill_submission)
        self.webhook_handler.set_category_processor("bug", process_bug)
        self.webhook_handler.set_category_processor("feature", process_feature)
        self.webhook_handler.set_category_processor("other", process_other)

        logger.info("Category processors registered")

    def _process_issue_event(self, context: WebhookContext, category: str) -> Dict[str, Any]:
        """Process an issue event through IssueMaintainerAgent.

        Args:
            context: Webhook context
            category: Event category

        Returns:
            Processing result
        """
        if not self.issue_agent:
            return {"success": False, "error": "IssueMaintainerAgent not initialized"}

        payload = context.payload
        action = payload.get("action", "")
        issue = payload.get("issue", {})
        issue_number = issue.get("number", 0)

        logger.info(f"Processing issue #{issue_number} ({category}) - action: {action}")

        # Only process opened or edited issues
        if action not in ("opened", "edited", "reopened"):
            return {"success": True, "status": "ignored", "reason": f"Action '{action}' not processed"}

        try:
            # Get or create IssueInfo
            from .tracker import IssueInfo

            issue_info = self.tracker.get_issue(issue_number)
            if not issue_info:
                # Create from webhook payload
                issue_info = IssueInfo(
                    issue_number=issue_number,
                    issue_title=issue.get("title", ""),
                    issue_body=issue.get("body"),
                    issue_state=issue.get("state", "open"),
                    issue_author=issue.get("user", {}).get("login", "unknown"),
                    created_at=issue.get("created_at", ""),
                    updated_at=issue.get("updated_at", ""),
                    processing_status="pending",
                    labels=str([l["name"] for l in issue.get("labels", [])]),
                )
                self.tracker.add_issue(issue_info)

            # Process through agent
            plan = self.issue_agent.analyze_and_plan(issue_info)

            with self._lock:
                self.stats.issues_processed += 1
                self.stats.last_processed_at = issue.get("updated_at", "")

            if plan:
                # Execute the plan
                result = self.issue_agent.execute_plan(plan)
                return {
                    "success": result.success,
                    "status": "executed" if result.success else "failed",
                    "plan_id": plan.plan_id,
                    "category": category,
                }
            else:
                return {
                    "success": True,
                    "status": "analyzed",
                    "category": category,
                    "message": "No plan generated (filtered or no requirements)",
                }

        except Exception as e:
            logger.error(f"Error processing issue #{issue_number}: {e}")
            with self._lock:
                self.stats.errors += 1
            return {"success": False, "error": str(e), "category": category}

    def _process_pr_event(self, context: WebhookContext, category: str) -> Dict[str, Any]:
        """Process a PR event through PRHandler.

        Args:
            context: Webhook context
            category: Event category

        Returns:
            Processing result
        """
        if not self.pr_handler:
            return {"success": False, "error": "PRHandler not initialized"}

        payload = context.payload
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number", 0)

        logger.info(f"Processing PR #{pr_number} ({category}) - action: {action}")

        # Only process opened or edited PRs
        if action not in ("opened", "edited", "reopened", "synchronize"):
            return {"success": True, "status": "ignored", "reason": f"Action '{action}' not processed"}

        try:
            # Get or create PRInfo
            from .tracker import PRInfo

            pr_info = self.tracker.get_pr(pr_number)
            if not pr_info:
                # Create from webhook payload
                pr_info = PRInfo(
                    pr_number=pr_number,
                    pr_title=pr.get("title", ""),
                    pr_author=pr.get("user", {}).get("login", "unknown"),
                    pr_state=pr.get("state", "open"),
                    head_ref=pr.get("head", {}).get("ref", ""),
                    base_ref=pr.get("base", {}).get("ref", ""),
                    created_at=pr.get("created_at", ""),
                    updated_at=pr.get("updated_at", ""),
                    processing_status="pending",
                )
                self.tracker.add_pr(pr_info)

            # Process through handler
            result = self.pr_handler.process_pr(pr_info)

            with self._lock:
                self.stats.prs_processed += 1
                self.stats.last_processed_at = pr.get("updated_at", "")

            return {
                "success": result.status in ("validated", "approved", "merged"),
                "status": result.status,
                "merged": result.merged,
                "category": category,
            }

        except Exception as e:
            logger.error(f"Error processing PR #{pr_number}: {e}")
            with self._lock:
                self.stats.errors += 1
            return {"success": False, "error": str(e), "category": category}

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            return {
                "issues_processed": self.stats.issues_processed,
                "prs_processed": self.stats.prs_processed,
                "errors": self.stats.errors,
                "last_processed_at": self.stats.last_processed_at,
            }

    def reset_stats(self) -> None:
        """Reset processing statistics."""
        with self._lock:
            self.stats = ProcessingStats()


def setup_webhook_integration(
    config: Config,
    tracker: Tracker,
    webhook_handler: WebhookEventHandler,
    repo_name: str = None,
) -> WebhookIntegration:
    """Setup webhook integration (convenience function).

    Args:
        config: Configuration object
        tracker: Tracker instance
        webhook_handler: WebhookEventHandler to integrate with
        repo_name: Repository name (owner/repo) for GitHub API

    Returns:
        Configured WebhookIntegration instance
    """
    integration = WebhookIntegration(
        config=config,
        tracker=tracker,
        webhook_handler=webhook_handler,
        repo_name=repo_name,
    )
    integration.setup_processors()
    return integration
