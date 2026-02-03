"""Issue Maintainer Agent - Intelligent GitHub Issue processing.

This agent acts as a "maintainer/customer service" that analyzes
GitHub Issues, filters malicious content, and generates structured
update plans for the repo_maintainer to execute.
"""

import logging
import json
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from github import Github
from github.Issue import Issue as GithubIssue

from .config import Config
from .tracker import Tracker, IssueInfo
from .issue_analyzer import IssueAnalyzer
from .update_planner import UpdatePlanner, PlanExecutor, RepoUpdatePlan, ExecutionResult


logger = logging.getLogger(__name__)


# ========== Configuration ==========

DEFAULT_ISSUE_LABELS = {
    "repo-request": "Repository Request",
    "feature-request": "Feature Request",
    "bug-report": "Bug Report",
    "config-update": "Config Update",
    "auto-processed": "Auto Processed",
    "malicious": "Malicious Content",
    "invalid": "Invalid",
}


# ========== Issue Maintainer Agent ==========

class IssueMaintainerAgent:
    """Agent that maintains and processes GitHub Issues.

    This agent:
    1. Fetches new Issues from the repository
    2. Analyzes each Issue for malicious content
    3. Extracts structured requirements
    4. Generates update plans
    5. Delegates execution to repo_maintainer
    6. Comments on Issues with results
    """

    def __init__(self, config: Config, github_token: str = None,
                 repo_name: str = None, repo_maintainer=None):
        """Initialize Issue Maintainer Agent.

        Args:
            config: Configuration object
            github_token: GitHub API token (defaults to config.github_token)
            repo_name: Repository name in format "owner/repo"
            repo_maintainer: Optional RepoMaintainerAgent for plan execution
        """
        self.config = config
        self.github_token = github_token or config.github_token
        self.repo_name = repo_name
        self.repo_maintainer = repo_maintainer

        # Initialize tracker
        self.tracker = Tracker(config)

        # Initialize GitHub client
        if self.github_token:
            self.github = Github(self.github_token)
        else:
            self.github = None
            logger.warning("No GitHub token provided, Issue processing will be limited")

        # Initialize analyzer
        security_config = config.get("issues.security_rules_file", "config/security_rules.yaml")
        self.analyzer = IssueAnalyzer(
            security_config_path=security_config,
            min_author_age_days=config.get("issues.reputation.min_author_age_days", 7),
            min_author_contributions=config.get("issues.reputation.min_contributions", 1),
        )

        # Initialize planner
        self.planner = UpdatePlanner(config)

        # Initialize executor
        self.executor = PlanExecutor(
            repo_maintainer=repo_maintainer,
            tracker=self.tracker,
            config=config,
        )

        # Processing settings
        self.auto_process_labels = config.get("issues.auto_process_labels", ["repo-request"])
        self.comment_on_processed = config.get("issues.comment_on_processed", True)
        self.reputation_check = config.get("issues.reputation_check", True)

        logger.info("IssueMaintainerAgent initialized")

    def fetch_new_issues(self) -> List[IssueInfo]:
        """Fetch new issues from the repository.

        Returns:
            List of IssueInfo objects for unprocessed issues
        """
        if not self.github or not self.repo_name:
            logger.warning("GitHub client or repo_name not configured")
            return []

        try:
            repo = self.github.get_repo(self.repo_name)

            # Get open issues
            issues = repo.get_issues(state="open")

            new_issues = []

            for issue in issues:
                # Skip pull requests
                if issue.pull_request:
                    continue

                # Check if already tracked
                existing = self.tracker.get_issue(issue.number)
                if existing:
                    continue

                # Check if should be auto-processed (by label)
                labels = [label.name for label in issue.labels]
                should_process = self._should_auto_process(issue, labels)

                # Create IssueInfo
                issue_info = IssueInfo(
                    issue_number=issue.number,
                    issue_title=issue.title,
                    issue_body=issue.body,
                    issue_state=issue.state,
                    issue_author=issue.user.login if issue.user else "unknown",
                    created_at=issue.created_at.isoformat() if issue.created_at else datetime.utcnow().isoformat(),
                    updated_at=issue.updated_at.isoformat() if issue.updated_at else datetime.utcnow().isoformat(),
                    processing_status="pending" if should_process else "queued",
                    labels=json.dumps(labels),
                )

                # Track in database
                self.tracker.add_issue(issue_info)
                new_issues.append(issue_info)

                logger.info(f"Found new issue #{issue.number}: {issue.title}")

            return new_issues

        except Exception as e:
            logger.error(f"Error fetching issues: {e}")
            return []

    def analyze_and_plan(self, issue_info: IssueInfo) -> Optional[RepoUpdatePlan]:
        """Analyze an issue and generate an update plan.

        Args:
            issue_info: Issue to analyze

        Returns:
            RepoUpdatePlan if valid and requirements found, None otherwise
        """
        logger.info(f"Analyzing issue #{issue_info.issue_number}")

        # Update status
        self.tracker.update_issue_status(
            issue_info.issue_number,
            "analyzing",
            processed_at=datetime.utcnow().isoformat()
        )

        try:
            # Parse labels
            labels = []
            if issue_info.labels:
                try:
                    labels = json.loads(issue_info.labels)
                except json.JSONDecodeError:
                    pass

            # Analyze the issue
            analysis = self.analyzer.analyze(
                title=issue_info.issue_title,
                body=issue_info.issue_body or "",
                author=issue_info.issue_author,
                labels=labels,
                github_client=self.github if self.reputation_check else None,
            )

            # Store analysis result
            self.tracker.update_issue_status(
                issue_info.issue_number,
                "analyzed",
                analysis_result=json.dumps(analysis)
            )

            # Check if issue was filtered
            if not analysis.get("safe"):
                reason = analysis.get("filter_reason", "Unknown reason")
                logger.info(f"Issue #{issue_info.issue_number} filtered: {reason}")

                self.tracker.update_issue_status(
                    issue_info.issue_number,
                    "rejected",
                    filter_reason=reason
                )

                # Post rejection comment on GitHub
                self._post_rejection_comment(issue_info.issue_number, reason, analysis)

                # Add malicious label if security issue
                if analysis.get("security_result"):
                    self._add_issue_label(issue_info.issue_number, "malicious")

                return None

            # Extract requirements
            requirements = analysis.get("requirements", [])
            if not requirements:
                logger.info(f"No requirements found in issue #{issue_info.issue_number}")
                self.tracker.update_issue_status(
                    issue_info.issue_number,
                    "filtered",
                    filter_reason="No valid requirements found"
                )
                # Post no requirements comment
                self._post_no_requirements_comment(issue_info.issue_number)
                return None

            # Generate update plan
            plan = self.planner.generate_plan(
                source_issue=issue_info.issue_number,
                requirements=requirements,
                issue_data={
                    "labels": labels,
                    "author": issue_info.issue_author,
                }
            )

            # Validate plan
            is_valid, errors = self.planner.validate_plan(plan)
            if not is_valid:
                logger.warning(f"Generated plan for issue #{issue_info.issue_number} is invalid: {errors}")
                self.tracker.update_issue_status(
                    issue_info.issue_number,
                    "rejected",
                    filter_reason=f"Invalid plan: {', '.join(errors)}"
                )
                # Post validation error comment
                self._post_validation_error_comment(issue_info.issue_number, errors)
                return None

            # Store plan in database
            self.tracker.add_update_plan(
                plan_type=plan.plan_type,
                source_issue=issue_info.issue_number,
                plan_data=plan.to_json(),
                execution_status="pending",
                created_at=plan.created_at,
            )

            # Update issue with plan reference
            self.tracker.update_issue_status(
                issue_info.issue_number,
                "planned",
                update_plan=plan.to_json()
            )

            # Post plan comment on GitHub
            self._post_plan_comment(issue_info.issue_number, plan, requirements, analysis)

            logger.info(f"Generated plan {plan.plan_id} for issue #{issue_info.issue_number}")
            return plan

        except Exception as e:
            logger.error(f"Error analyzing issue #{issue_info.issue_number}: {e}")
            self.tracker.update_issue_status(
                issue_info.issue_number,
                "rejected",
                error_message=str(e)
            )
            # Post error comment
            self._post_error_comment(issue_info.issue_number, str(e))
            return None

    def execute_plan(self, plan: RepoUpdatePlan) -> ExecutionResult:
        """Execute an update plan.

        Args:
            plan: Plan to execute

        Returns:
            ExecutionResult
        """
        logger.info(f"Executing plan {plan.plan_id}")

        result = self.executor.execute_plan(plan)

        # Comment on issue if configured
        if self.comment_on_processed and result.success:
            self._post_execution_comment(plan.source_issue, result)

        return result

    def process_pending_issues(self, max_issues: int = 10) -> Dict[str, Any]:
        """Process all pending issues.

        Args:
            max_issues: Maximum number of issues to process

        Returns:
            Dictionary with processing results
        """
        logger.info("Processing pending issues")

        results = {
            "fetched": 0,
            "analyzed": 0,
            "planned": 0,
            "executed": 0,
            "filtered": 0,
            "errors": 0,
            "details": [],
        }

        # Fetch new issues
        new_issues = self.fetch_new_issues()[:max_issues]
        results["fetched"] = len(new_issues)

        # Get pending issues from database
        pending_issues = self.tracker.get_pending_issues("pending")

        # Combine and limit
        all_pending = new_issues + [i for i in pending_issues if i not in new_issues]
        all_pending = all_pending[:max_issues]

        for issue_info in all_pending:
            try:
                # Analyze and plan
                plan = self.analyze_and_plan(issue_info)

                if plan:
                    results["planned"] += 1

                    # Execute the plan
                    execution_result = self.execute_plan(plan)

                    if execution_result.success:
                        results["executed"] += 1
                        self.tracker.update_issue_status(
                            issue_info.issue_number,
                            "completed"
                        )
                    else:
                        results["errors"] += 1
                        self.tracker.update_issue_status(
                            issue_info.issue_number,
                            "failed",
                            error_message=execution_result.error
                        )
                else:
                    results["filtered"] += 1

                results["analyzed"] += 1

                results["details"].append({
                    "issue_number": issue_info.issue_number,
                    "title": issue_info.issue_title,
                    "status": "completed" if plan else "filtered",
                })

            except Exception as e:
                logger.error(f"Error processing issue #{issue_info.issue_number}: {e}")
                results["errors"] += 1

        logger.info(f"Processing complete: {results}")
        return results

    def _should_auto_process(self, issue: GithubIssue, labels: List[str]) -> bool:
        """Check if an issue should be auto-processed.

        Args:
            issue: GitHub Issue object
            labels: Issue label names

        Returns:
            True if should auto-process
        """
        # Check labels
        for label in labels:
            if label.lower() in [l.lower() for l in self.auto_process_labels]:
                return True

        # Check title keywords
        title_lower = issue.title.lower()
        for keyword in self.auto_process_labels:
            if keyword.lower() in title_lower:
                return True

        return False

    def _add_issue_label(self, issue_number: int, label_name: str) -> bool:
        """Add a label to an issue.

        Args:
            issue_number: Issue number
            label_name: Label to add

        Returns:
            True if successful
        """
        if not self.github or not self.repo_name:
            return False

        try:
            repo = self.github.get_repo(self.repo_name)
            issue = repo.get_issue(issue_number)

            # Check if label exists, create if not
            try:
                repo.get_label(label_name)
            except Exception:
                # Create label
                repo.create_label(
                    name=label_name,
                    color=DEFAULT_ISSUE_LABELS.get(label_name, "000000"),
                    description=DEFAULT_ISSUE_LABELS.get(label_name, label_name)
                )

            issue.add_to_labels(label_name)
            logger.info(f"Added label '{label_name}' to issue #{issue_number}")
            return True

        except Exception as e:
            logger.error(f"Error adding label to issue #{issue_number}: {e}")
            return False

    def _post_execution_comment(self, issue_number: int, result: ExecutionResult) -> bool:
        """Post a comment on an issue with execution results.

        Args:
            issue_number: Issue number
            result: Execution result

        Returns:
            True if successful
        """
        if not self.github or not self.repo_name:
            return False

        try:
            repo = self.github.get_repo(self.repo_name)
            issue = repo.get_issue(issue_number)

            # Create comment
            if result.success:
                comment = f"""## ✅ Update Plan Executed

This issue has been processed and the update plan has been executed successfully.

**Plan ID:** `{result.plan_id}`
**Executed at:** {result.executed_at}

**Summary:**
{result.message}

**Details:**
```json
{json.dumps(result.details, indent=2)}
```

This issue can now be closed. 🎉
"""
            else:
                comment = f"""## ❌ Update Plan Failed

The update plan for this issue could not be executed.

**Plan ID:** `{result.plan_id}`
**Executed at:** {result.executed_at}

**Error:**
```
{result.error or 'Unknown error'}
```

Please review the issue and make any necessary corrections.
"""

            issue.create_comment(comment)
            logger.info(f"Posted execution comment on issue #{issue_number}")
            return True

        except Exception as e:
            logger.error(f"Error posting comment on issue #{issue_number}: {e}")
            return False

    def _post_plan_comment(self, issue_number: int, plan: RepoUpdatePlan,
                           requirements: List[Dict], analysis: Dict) -> bool:
        """Post a comment on an issue with the generated update plan.

        Args:
            issue_number: Issue number
            plan: Generated update plan
            requirements: Extracted requirements
            analysis: Analysis results

        Returns:
            True if successful
        """
        if not self.github or not self.repo_name:
            logger.warning("GitHub client or repo_name not configured, skipping plan comment")
            return False

        try:
            repo = self.github.get_repo(self.repo_name)
            issue = repo.get_issue(issue_number)

            # Get issue author for personalization
            author = issue.user.login if issue.user else "there"

            # Build comment
            comment = f"""## 📋 Update Plan Generated

Hi @{author}! 👋

I've analyzed your issue and generated an update plan. Here's what I found:

---

### ✅ Analysis Result

Your issue passed all security and validation checks:
- ✓ No malicious content detected
- ✓ Valid issue type: `{analysis.get('issue_type', 'unknown')}`
- ✓ {len(requirements)} requirement(s) extracted

---

### 📦 Update Plan Details

**Plan ID:** `{plan.plan_id}`
**Plan Type:** `{plan.plan_type.replace('_', ' ').title()}`
**Priority:** {plan.priority}/10

"""

            # Add plan-specific details
            if plan.repos_to_add:
                comment += f"""
**Repositories to Add ({len(plan.repos_to_add)}):**
"""
                for repo in plan.repos_to_add[:5]:  # Show max 5
                    comment += f"- `{repo}`\n"
                if len(plan.repos_to_add) > 5:
                    comment += f"- ... and {len(plan.repos_to_add) - 5} more\n"

            if plan.search_terms_to_add:
                comment += f"""
**Search Terms to Add ({len(plan.search_terms_to_add)}):**
"""
                for term in plan.search_terms_to_add[:5]:
                    comment += f"- `{term}`\n"
                if len(plan.search_terms_to_add) > 5:
                    comment += f"- ... and {len(plan.search_terms_to_add) - 5} more\n"

            if plan.config_updates:
                comment += f"""
**Configuration Updates:**
```yaml
{json.dumps(plan.config_updates, indent=2)}
```
"""

            comment += f"""
---

### 📝 Summary

{plan.notes or 'No additional notes'}

---

### ⏭️ Next Steps

This plan is now queued for execution. The system will:

1. Add the requested repositories to the search list
2. Update configuration files as needed
3. Trigger a pipeline run to fetch new skills
4. Organize skills into the X-Skills repository

You'll receive another comment when execution is complete.

**Estimated processing time:** 5-15 minutes

---

💡 **Tip:** To check the status at any time, use the `/status` command or check the issue labels.

---

🤖 *This comment was automatically generated by SkillFlow Issue Maintainer Agent*
"""

            issue.create_comment(comment)

            # Add "planned" label
            self._add_issue_label(issue_number, "planned")

            logger.info(f"Posted plan comment on issue #{issue_number}")
            return True

        except Exception as e:
            logger.error(f"Error posting plan comment on issue #{issue_number}: {e}")
            return False

    def _post_rejection_comment(self, issue_number: int, reason: str, analysis: Dict) -> bool:
        """Post a rejection comment on an issue.

        Args:
            issue_number: Issue number
            reason: Rejection reason
            analysis: Analysis results

        Returns:
            True if successful
        """
        if not self.github or not self.repo_name:
            return False

        try:
            repo = self.github.get_repo(self.repo_name)
            issue = repo.get_issue(issue_number)
            author = issue.user.login if issue.user else "there"

            # Check if security issue
            is_security = analysis.get("security_result") is not None

            if is_security:
                comment = f"""## 🚨 Security Issue Detected

Hi @{author},

I cannot process this issue because it contains content that triggers security filters.

**Reason:** {reason}

**Security Details:**
- **Severity:** {analysis.get('security_result', {}).get('severity', 'unknown')}
- **Patterns Matched:** {len(analysis.get('security_result', {}).get('patterns', []))}

This is a precautionary measure to ensure the safety and integrity of the system.

If you believe this is a false positive, please:
1. Review your issue content
2. Remove or rephrase the flagged content
3. Open a new issue or comment below for manual review

---

🔒 *This issue was automatically filtered by SkillFlow Security Checker*
"""
            else:
                comment = f"""## ❌ Issue Cannot Be Processed

Hi @{author},

I'm unable to process this issue for the following reason:

**Reason:** {reason}

**What You Can Do:**

Please review your issue and ensure it:

1. ✅ Clearly specifies what repository to add (use format: `owner/repo-name`)
2. ✅ Explains why the repository is valuable
3. ✅ Uses the `repo-request` label if requesting a repository addition
4. ✅ Contains no malicious or suspicious content

Once you've made corrections, please comment and I'll re-analyze the issue.

---

🤖 *This comment was automatically generated by SkillFlow Issue Maintainer Agent*
"""

            issue.create_comment(comment)
            logger.info(f"Posted rejection comment on issue #{issue_number}")
            return True

        except Exception as e:
            logger.error(f"Error posting rejection comment on issue #{issue_number}: {e}")
            return False

    def _post_no_requirements_comment(self, issue_number: int) -> bool:
        """Post a comment when no requirements are found.

        Args:
            issue_number: Issue number

        Returns:
            True if successful
        """
        if not self.github or not self.repo_name:
            return False

        try:
            repo = self.github.get_repo(self.repo_name)
            issue = repo.get_issue(issue_number)
            author = issue.user.login if issue.user else "there"

            comment = f"""## ❓ No Actionable Requirements Found

Hi @{author},

I've analyzed your issue but couldn't extract any actionable requirements.

**What This Means:**

Your issue doesn't contain clear information about:
- A specific repository to add (format: `owner/repo-name`)
- Search terms to include
- Configuration changes to make

**How to Fix:**

Please update your issue with:

1. **For repository requests:**
   ```
   Please add: https://github.com/owner/repo-name

   Why it's valuable: [brief description]
   ```

2. **For search term suggestions:**
   ```
   Please add these search terms:
   - term1
   - term2
   - term3
   ```

Once updated, comment below and I'll re-analyze!

---

🤖 *Generated by SkillFlow Issue Maintainer Agent*
"""

            issue.create_comment(comment)
            logger.info(f"Posted no-requirements comment on issue #{issue_number}")
            return True

        except Exception as e:
            logger.error(f"Error posting no-requirements comment on issue #{issue_number}: {e}")
            return False

    def _post_validation_error_comment(self, issue_number: int, errors: List[str]) -> bool:
        """Post a comment about validation errors.

        Args:
            issue_number: Issue number
            errors: List of validation errors

        Returns:
            True if successful
        """
        if not self.github or not self.repo_name:
            return False

        try:
            repo = self.github.get_repo(self.repo_name)
            issue = repo.get_issue(issue_number)
            author = issue.user.login if issue.user else "there"

            comment = f"""## ⚠️ Validation Error

Hi @{author},

I generated an update plan for your issue, but it failed validation:

**Errors:**
"""
            for error in errors:
                comment += f"- ❌ {error}\n"

            comment += """
**Common Issues:**

- Invalid repository format (use `owner/repo-name`)
- Repository name too long or contains invalid characters
- Empty or malformed search terms

**Please Review:**

Check your issue and ensure all repository names and search terms are correctly formatted, then comment below for re-analysis.

---

🤖 *Generated by SkillFlow Issue Maintainer Agent*
"""

            issue.create_comment(comment)
            logger.info(f"Posted validation error comment on issue #{issue_number}")
            return True

        except Exception as e:
            logger.error(f"Error posting validation error comment on issue #{issue_number}: {e}")
            return False

    def _post_error_comment(self, issue_number: int, error_message: str) -> bool:
        """Post a comment about processing errors.

        Args:
            issue_number: Issue number
            error_message: Error message

        Returns:
            True if successful
        """
        if not self.github or not self.repo_name:
            return False

        try:
            repo = self.github.get_repo(self.repo_name)
            issue = repo.get_issue(issue_number)

            comment = f"""## 💥 Processing Error

An unexpected error occurred while processing this issue.

**Error:**
```
{error_message}
```

The maintainers have been notified. Please try again later or create a new issue if the problem persists.

---

🤖 *Generated by SkillFlow Issue Maintainer Agent*
"""

            issue.create_comment(comment)
            logger.info(f"Posted error comment on issue #{issue_number}")
            return True

        except Exception as e:
            logger.error(f"Error posting error comment on issue #{issue_number}: {e}")
            return False

    def get_issue_status(self, issue_number: int) -> Optional[Dict[str, Any]]:
        """Get the current status of an issue.

        Args:
            issue_number: Issue number

        Returns:
            Dictionary with issue status or None
        """
        issue_info = self.tracker.get_issue(issue_number)
        if not issue_info:
            return None

        return {
            "number": issue_info.issue_number,
            "title": issue_info.issue_title,
            "state": issue_info.issue_state,
            "author": issue_info.issue_author,
            "processing_status": issue_info.processing_status,
            "created_at": issue_info.created_at,
            "updated_at": issue_info.updated_at,
            "processed_at": issue_info.processed_at,
            "has_plan": issue_info.update_plan is not None,
            "filtered": issue_info.filter_reason is not None,
        }


# ========== Standalone Functions ==========

def process_issues(config: Config, repo_maintainer=None,
                   max_issues: int = 10) -> Dict[str, Any]:
    """Process GitHub Issues (standalone function).

    Args:
        config: Configuration object
        repo_maintainer: Optional repo_maintainer for plan execution
        max_issues: Maximum issues to process

    Returns:
        Processing results dictionary
    """
    agent = IssueMaintainerAgent(
        config=config,
        repo_name=config.get("issues.repo_name"),
        repo_maintainer=repo_maintainer,
    )

    return agent.process_pending_issues(max_issues=max_issues)
