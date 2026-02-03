"""Webhook Handler module for processing GitHub webhook events.

This module handles incoming webhook events from GitHub and
queues them for processing.
"""

import logging
import json
import hmac
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from enum import Enum

from .config import Config
from .tracker import Tracker, WebhookEvent


logger = logging.getLogger(__name__)


# ========== Data Classes ==========

class WebhookEventType(Enum):
    """Types of webhook events."""
    PUSH = "push"
    RELEASE = "release"
    REPOSITORY = "repository"
    PING = "ping"
    ISSUES = "issues"
    PULL_REQUEST = "pull_request"
    ISSUE_COMMENT = "issue_comment"
    PULL_REQUEST_REVIEW = "pull_request_review"

class EventCategory(Enum):
    """Categories of events for routing to processors."""
    REPO_REQUEST = "repo-request"
    SKILL_SUBMISSION = "skill-submission"
    BUG = "bug"
    FEATURE = "feature"
    OTHER = "other"


@dataclass
class WebhookContext:
    """Context for webhook processing."""
    event_type: str
    repo_name: str
    payload: Dict[str, Any]
    received_at: str
    signature: Optional[str] = None
    delivery_id: Optional[str] = None


# ========== Webhook Handler ==========

class WebhookEventHandler:
    """Handle GitHub webhook events."""

    def __init__(self, config: Config, tracker: Tracker):
        """Initialize webhook handler.

        Args:
            config: Configuration object
            tracker: Tracker instance for event tracking
        """
        self.config = config
        self.tracker = tracker
        self.webhook_secret = config.webhook_secret

        # Event handlers
        self._handlers = {
            WebhookEventType.PUSH.value: self._handle_push_event,
            WebhookEventType.RELEASE.value: self._handle_release_event,
            WebhookEventType.REPOSITORY.value: self._handle_repository_event,
            WebhookEventType.PING.value: self._handle_ping_event,
            WebhookEventType.ISSUES.value: self._handle_issues_event,
            WebhookEventType.PULL_REQUEST.value: self._handle_pull_request_event,
            WebhookEventType.ISSUE_COMMENT.value: self._handle_issue_comment_event,
            WebhookEventType.PULL_REQUEST_REVIEW.value: self._handle_pull_request_review_event,
        }

        # Category processors (can be injected)
        self._category_processors = {}

        # Sync callback (optional)
        self.sync_callback: Optional[Callable] = None

        logger.info("WebhookEventHandler initialized")

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature.

        Args:
            payload: Raw request payload
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            logger.warning("No webhook secret configured, skipping signature verification")
            return True

        if not signature:
            return False

        # signature format: "sha256=<hash>"
        if not signature.startswith("sha256="):
            return False

        signature_hash = signature[7:]  # Remove "sha256=" prefix

        # Compute expected signature
        expected_hash = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature_hash, expected_hash)

    def categorize_event(self, payload: dict, event_type: str) -> str:
        """Categorize GitHub event by type and labels.

        Args:
            payload: GitHub webhook payload
            event_type: Event type from X-GitHub-Event header

        Returns:
            Event category: 'repo-request', 'skill-submission', 'bug', 'feature', 'other'
        """
        if event_type == 'pull_request':
            return EventCategory.SKILL_SUBMISSION.value

        if event_type == 'pull_request_review':
            return EventCategory.SKILL_SUBMISSION.value

        if event_type == 'issues':
            labels = [l['name'] for l in payload.get('issue', {}).get('labels', [])]
            if 'repo-request' in labels:
                return EventCategory.REPO_REQUEST.value
            elif 'bug' in labels:
                return EventCategory.BUG.value
            elif 'enhancement' in labels or 'feature-request' in labels:
                return EventCategory.FEATURE.value

        if event_type == 'issue_comment':
            # Get the issue's labels to determine category
            issue_labels = [l['name'] for l in payload.get('issue', {}).get('labels', [])]
            if 'repo-request' in issue_labels:
                return EventCategory.REPO_REQUEST.value
            elif 'bug' in issue_labels:
                return EventCategory.BUG.value
            elif 'enhancement' in issue_labels or 'feature-request' in issue_labels:
                return EventCategory.FEATURE.value

        return EventCategory.OTHER.value

    def set_category_processor(self, category: str, processor: Callable) -> None:
        """Set a processor for a specific event category.

        Args:
            category: Event category (repo-request, skill-submission, bug, feature, other)
            processor: Callable that takes (context, category) and processes the event
        """
        self._category_processors[category] = processor
        logger.info(f"Category processor registered for: {category}")

    def parse_event(self, headers: Dict[str, str], payload: bytes) -> Optional[WebhookContext]:
        """Parse webhook event from request.

        Args:
            headers: Request headers
            payload: Raw request body

        Returns:
            WebhookContext or None if invalid
        """
        # Get event type
        event_type = headers.get("X-GitHub-Event", "")
        if not event_type:
            logger.error("Missing X-GitHub-Event header")
            return None

        # Get delivery ID
        delivery_id = headers.get("X-GitHub-Delivery")

        # Get signature
        signature = headers.get("X-Hub-Signature-256")

        # Verify signature
        if signature and not self.verify_signature(payload, signature):
            logger.error(f"Invalid signature for delivery {delivery_id}")
            return None

        # Parse payload
        try:
            data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
            return None

        # Get repository name
        repo_name = None
        if "repository" in data:
            repo_name = data["repository"].get("full_name")

        if not repo_name:
            logger.error("No repository name in payload")
            return None

        return WebhookContext(
            event_type=event_type,
            repo_name=repo_name,
            payload=data,
            received_at=datetime.utcnow().isoformat(),
            signature=signature,
            delivery_id=delivery_id,
        )

    def handle_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle a webhook event.

        Args:
            context: Webhook event context

        Returns:
            Handler result
        """
        logger.info(f"Handling {context.event_type} event from {context.repo_name}")

        # Store event in database
        event_id = self.tracker.add_webhook_event(
            event_type=context.event_type,
            repo_name=context.repo_name,
            event_payload=json.dumps(context.payload),
            received_at=context.received_at
        )

        # Categorize the event
        category = self.categorize_event(context.payload, context.event_type)
        logger.info(f"Event categorized as: {category}")

        # Check if there's a category processor
        if category in self._category_processors:
            try:
                processor = self._category_processors[category]
                result = processor(context, category)

                if result.get("success"):
                    self.tracker.update_webhook_event(event_id, "completed")
                else:
                    self.tracker.update_webhook_event(
                        event_id,
                        "failed",
                        error_message=result.get("error", "Unknown error")
                    )

                return result

            except Exception as e:
                logger.error(f"Error in category processor for {category}: {e}")
                self.tracker.update_webhook_event(
                    event_id,
                    "failed",
                    error_message=str(e)
                )
                return {"status": "error", "error": str(e)}

        # Get handler for this event type
        handler = self._handlers.get(context.event_type)
        if not handler:
            logger.warning(f"No handler for event type: {context.event_type}")
            self.tracker.update_webhook_event(event_id, "completed")
            return {"status": "ignored", "reason": f"No handler for {context.event_type}"}

        # Process event
        try:
            result = handler(context)

            if result.get("success"):
                self.tracker.update_webhook_event(event_id, "completed")
            else:
                self.tracker.update_webhook_event(
                    event_id,
                    "failed",
                    error_message=result.get("error", "Unknown error")
                )

            return result

        except Exception as e:
            logger.error(f"Error handling {context.event_type} event: {e}")
            self.tracker.update_webhook_event(
                event_id,
                "failed",
                error_message=str(e)
            )
            return {"status": "error", "error": str(e)}

    def _handle_push_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle push event.

        Args:
            context: Webhook context

        Returns:
            Handler result
        """
        payload = context.payload
        ref = payload.get("ref", "")
        repo_name = context.repo_name

        # Extract branch name
        branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref

        # Get commit info
        head_commit = payload.get("head_commit", {})
        commit_id = head_commit.get("id", "")
        committer = head_commit.get("committer", {}).get("username", "")

        logger.info(f"Push to {repo_name}/{branch} by {committer}: {commit_id[:8]}")

        # Check if this is a tracked repository
        # Trigger sync if it is
        if self.sync_callback:
            try:
                self.sync_callback(repo_name, branch, commit_id)
            except Exception as e:
                logger.error(f"Error in sync callback: {e}")

        return {
            "success": True,
            "status": "processed",
            "repo": repo_name,
            "branch": branch,
            "commit": commit_id[:8],
        }

    def _handle_release_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle release event.

        Args:
            context: Webhook context

        Returns:
            Handler result
        """
        payload = context.payload
        action = payload.get("action", "")
        repo_name = context.repo_name

        release = payload.get("release", {})
        tag_name = release.get("tag_name", "")
        release_name = release.get("name", "")
        author = release.get("author", {}).get("login", "")

        logger.info(f"Release {action} in {repo_name}: {tag_name} by {author}")

        # Releases indicate the repository is active
        # Could trigger a sync or update activity status

        return {
            "success": True,
            "status": "processed",
            "repo": repo_name,
            "action": action,
            "tag": tag_name,
            "release": release_name,
        }

    def _handle_repository_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle repository event.

        Args:
            context: Webhook context

        Returns:
            Handler result
        """
        payload = context.payload
        action = payload.get("action", "")
        repo_name = context.repo_name

        logger.info(f"Repository {action}: {repo_name}")

        # Handle repository transfers, deletions, etc.
        if action == "deleted":
            logger.warning(f"Repository deleted: {repo_name}")
            # Could mark all skills from this repo as unavailable
        elif action == "transferred":
            # Repository was transferred to a new owner
            new_repo = payload.get("repository", {}).get("full_name")
            logger.info(f"Repository transferred to: {new_repo}")
            # Could update source_repo for all skills

        return {
            "success": True,
            "status": "processed",
            "repo": repo_name,
            "action": action,
        }

    def _handle_ping_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle ping event.

        Args:
            context: Webhook context

        Returns:
            Handler result
        """
        logger.info(f"Ping from {context.repo_name}")
        return {"success": True, "status": "pong"}

    def _handle_issues_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle issues event (repo requests, bugs, features).

        Args:
            context: Webhook context

        Returns:
            Handler result
        """
        payload = context.payload
        action = payload.get("action", "")
        repo_name = context.repo_name

        issue = payload.get("issue", {})
        issue_number = issue.get("number", 0)
        issue_title = issue.get("title", "")
        issue_author = issue.get("user", {}).get("login", "unknown")
        labels = [l["name"] for l in issue.get("labels", [])]

        logger.info(f"Issue {action} #{issue_number} in {repo_name}: {issue_title}")
        logger.info(f"  Author: {issue_author}, Labels: {labels}")

        # Store/track the issue in database for async processing
        # The actual processing will be done by IssueMaintainerAgent
        try:
            from .tracker import IssueInfo

            issue_info = IssueInfo(
                issue_number=issue_number,
                issue_title=issue_title,
                issue_body=issue.get("body"),
                issue_state=issue.get("state", "open"),
                issue_author=issue_author,
                created_at=issue.get("created_at", datetime.utcnow().isoformat()),
                updated_at=issue.get("updated_at", datetime.utcnow().isoformat()),
                processing_status="pending",
                labels=json.dumps(labels),
            )

            self.tracker.add_issue(issue_info)
            logger.info(f"Issue #{issue_number} tracked in database")

        except Exception as e:
            logger.error(f"Error tracking issue #{issue_number}: {e}")

        return {
            "success": True,
            "status": "processed",
            "repo": repo_name,
            "action": action,
            "issue_number": issue_number,
            "category": self.categorize_event(payload, "issues"),
        }

    def _handle_pull_request_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle pull request event (skill submissions).

        Args:
            context: Webhook context

        Returns:
            Handler result
        """
        payload = context.payload
        action = payload.get("action", "")
        repo_name = context.repo_name

        pr = payload.get("pull_request", {})
        pr_number = pr.get("number", 0)
        pr_title = pr.get("title", "")
        pr_author = pr.get("user", {}).get("login", "unknown")
        pr_state = pr.get("state", "open")
        head_ref = pr.get("head", {}).get("ref", "")
        base_ref = pr.get("base", {}).get("ref", "")

        logger.info(f"PR {action} #{pr_number} in {repo_name}: {pr_title}")
        logger.info(f"  Author: {pr_author}, State: {pr_state}, {head_ref} -> {base_ref}")

        # Store/track the PR in database for async processing
        # The actual processing will be done by PRHandler
        try:
            from .tracker import PRInfo

            pr_info = PRInfo(
                pr_number=pr_number,
                pr_title=pr_title,
                pr_author=pr_author,
                pr_state=pr_state,
                head_ref=head_ref,
                base_ref=base_ref,
                created_at=pr.get("created_at", datetime.utcnow().isoformat()),
                updated_at=pr.get("updated_at", datetime.utcnow().isoformat()),
                processing_status="pending",
            )

            self.tracker.add_pr(pr_info)
            logger.info(f"PR #{pr_number} tracked in database")

        except Exception as e:
            logger.error(f"Error tracking PR #{pr_number}: {e}")

        return {
            "success": True,
            "status": "processed",
            "repo": repo_name,
            "action": action,
            "pr_number": pr_number,
            "category": self.categorize_event(payload, "pull_request"),
        }

    def _handle_issue_comment_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle issue comment event.

        Args:
            context: Webhook context

        Returns:
            Handler result
        """
        payload = context.payload
        action = payload.get("action", "")
        repo_name = context.repo_name

        issue = payload.get("issue", {})
        issue_number = issue.get("number", 0)
        comment = payload.get("comment", {})
        comment_author = comment.get("user", {}).get("login", "unknown")

        logger.info(f"Issue comment {action} on #{issue_number} by {comment_author}")

        # Check if issue should be re-processed
        # This can trigger re-analysis when someone comments on a pending issue

        return {
            "success": True,
            "status": "processed",
            "repo": repo_name,
            "action": action,
            "issue_number": issue_number,
        }

    def _handle_pull_request_review_event(self, context: WebhookContext) -> Dict[str, Any]:
        """Handle pull request review event.

        Args:
            context: Webhook context

        Returns:
            Handler result
        """
        payload = context.payload
        action = payload.get("action", "")
        repo_name = context.repo_name

        pr = payload.get("pull_request", {})
        pr_number = pr.get("number", 0)
        review = payload.get("review", {})
        review_state = review.get("state", "")
        review_author = review.get("user", {}).get("login", "unknown")

        logger.info(f"PR review {action} on #{pr_number} by {review_author}: {review_state}")

        # Check if PR should be merged after approval
        if review_state == "approved":
            logger.info(f"PR #{pr_number} approved, eligible for auto-merge")

        return {
            "success": True,
            "status": "processed",
            "repo": repo_name,
            "action": action,
            "pr_number": pr_number,
            "review_state": review_state,
        }

    def set_sync_callback(self, callback: Callable) -> None:
        """Set callback function for sync triggers.

        Args:
            callback: Function to call when sync is needed
                     (repo_name, branch, commit_id) -> None
        """
        self.sync_callback = callback


# ========== Event Queue ==========

class EventQueue:
    """Queue for processing webhook events asynchronously."""

    def __init__(self, config: Config, tracker: Tracker):
        """Initialize event queue.

        Args:
            config: Configuration object
            tracker: Tracker instance
        """
        self.config = config
        self.tracker = tracker
        self.handler = WebhookEventHandler(config, tracker)

        self.max_size = config.get("webhook.queue.max_size", 1000)
        self.workers = config.get("webhook.queue.workers", 2)

        logger.info(f"EventQueue initialized (max_size={self.max_size}, workers={self.workers})")

    def add_event(self, headers: Dict[str, str], payload: bytes) -> Dict[str, Any]:
        """Add event to queue.

        Args:
            headers: Request headers
            payload: Raw request body

        Returns:
            Result dictionary
        """
        context = self.handler.parse_event(headers, payload)
        if not context:
            return {"status": "error", "error": "Invalid webhook event"}

        # Process immediately (simpler implementation)
        result = self.handler.handle_event(context)
        return result

    def process_pending_events(self) -> Dict[str, Any]:
        """Process pending events from database.

        Returns:
            Processing results
        """
        logger.info("Processing pending webhook events")

        pending = self.tracker.get_pending_events()

        results = {
            "processed": 0,
            "completed": 0,
            "failed": 0,
            "errors": 0,
        }

        for event in pending:
            try:
                # Reconstruct context
                context = WebhookContext(
                    event_type=event.event_type,
                    repo_name=event.repo_name,
                    payload=json.loads(event.event_payload) if event.event_payload else {},
                    received_at=event.received_at,
                )

                result = self.handler.handle_event(context)
                results["processed"] += 1

                if result.get("status") == "completed" or result.get("success"):
                    results["completed"] += 1
                else:
                    results["failed"] += 1

            except Exception as e:
                logger.error(f"Error processing event {event.event_id}: {e}")
                results["errors"] += 1

        logger.info(f"Event processing complete: {results}")
        return results

    def retry_failed_events(self) -> Dict[str, Any]:
        """Retry failed events.

        Returns:
            Retry results
        """
        logger.info("Retrying failed webhook events")

        # Get failed events with retry count below threshold
        failed_events = self.tracker.get_pending_events()

        results = {
            "retried": 0,
            "succeeded": 0,
            "still_failed": 0,
        }

        for event in failed_events:
            if event.processing_status == "failed" and event.retry_count < 3:
                try:
                    # Reconstruct context
                    context = WebhookContext(
                        event_type=event.event_type,
                        repo_name=event.repo_name,
                        payload=json.loads(event.event_payload) if event.event_payload else {},
                        received_at=event.received_at,
                    )

                    result = self.handler.handle_event(context)
                    results["retried"] += 1

                    if result.get("success"):
                        results["succeeded"] += 1
                    else:
                        results["still_failed"] += 1
                        # Update with retry increment
                        self.tracker.update_webhook_event(
                            event.event_id,
                            "failed",
                            error_message=result.get("error"),
                            increment_retry=True
                        )

                except Exception as e:
                    logger.error(f"Error retrying event {event.event_id}: {e}")
                    self.tracker.update_webhook_event(
                        event.event_id,
                        "failed",
                        error_message=str(e),
                        increment_retry=True
                    )

        logger.info(f"Retry complete: {results}")
        return results
