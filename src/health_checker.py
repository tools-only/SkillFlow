"""Health Checker module for validating skill health.

This module provides various health checks for skills including
link validation, format checking, staleness detection, and syntax validation.
"""

import logging
import re
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse
import hashlib

from .config import Config
from .tracker import Tracker, SkillInfo, HealthCheckResult


logger = logging.getLogger(__name__)


# ========== Data Classes ==========

@dataclass
class HealthCheckSummary:
    """Summary of health check results."""
    total_skills: int
    healthy: int
    warnings: int
    failed: int
    skipped: int
    check_details: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def healthy_percentage(self) -> float:
        """Calculate healthy percentage."""
        if self.total_skills == 0:
            return 100.0
        return (self.healthy / self.total_skills) * 100

    @property
    def failed_percentage(self) -> float:
        """Calculate failed percentage."""
        if self.total_skills == 0:
            return 0.0
        return (self.failed / self.total_skills) * 100


@dataclass
class LinkCheckResult:
    """Result of a link check."""
    url: str
    status_code: Optional[int] = None
    is_accessible: bool = False
    error: Optional[str] = None
    redirect_url: Optional[str] = None


@dataclass
class FormatCheckResult:
    """Result of a format check."""
    has_frontmatter: bool
    has_required_fields: bool
    missing_fields: List[str] = field(default_factory=list)
    yaml_errors: List[str] = field(default_factory=list)
    is_valid: bool = True


@dataclass
class StalenessCheckResult:
    """Result of a staleness check."""
    is_stale: bool
    days_since_update: Optional[int] = None
    repo_archived: bool = False
    repo_deleted: bool = False
    last_commit_date: Optional[str] = None


# ========== Link Checker ==========

class LinkChecker:
    """Check if source URLs are accessible."""

    def __init__(self, config: Config):
        """Initialize link checker.

        Args:
            config: Configuration object
        """
        self.config = config
        self.timeout = config.get("health_check.thresholds.request_timeout", 10)
        self.failure_codes = config.get("health_check.checks.link_check.failure_codes", [404, 410])
        self.warning_codes = config.get("health_check.checks.link_check.warning_codes", [403, 429, 500, 502, 503])

    def check_url(self, url: str) -> LinkCheckResult:
        """Check if a URL is accessible.

        Args:
            url: URL to check

        Returns:
            LinkCheckResult with check details
        """
        try:
            import requests

            response = requests.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                headers={"User-Agent": "SkillFlow-HealthCheck/1.0"}
            )

            redirect_url = response.url if response.url != url else None

            result = LinkCheckResult(
                url=url,
                status_code=response.status_code,
                is_accessible=response.status_code not in self.failure_codes,
                redirect_url=redirect_url
            )

            if response.status_code in self.failure_codes:
                result.error = f"HTTP {response.status_code}"
            elif response.status_code in self.warning_codes:
                result.error = f"HTTP {response.status_code} (warning)"

            return result

        except requests.exceptions.Timeout:
            return LinkCheckResult(
                url=url,
                is_accessible=False,
                error="Request timeout"
            )
        except requests.exceptions.RequestException as e:
            return LinkCheckResult(
                url=url,
                is_accessible=False,
                error=str(e)
            )
        except Exception as e:
            return LinkCheckResult(
                url=url,
                is_accessible=False,
                error=f"Unexpected error: {e}"
            )

    def check_github_repo_exists(self, repo_name: str) -> Tuple[bool, Optional[str]]:
        """Check if a GitHub repository exists.

        Args:
            repo_name: Repository name (owner/repo)

        Returns:
            Tuple of (exists, error_message)
        """
        try:
            import requests
            url = f"https://api.github.com/repos/{repo_name}"
            response = requests.get(url, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                if data.get("archived"):
                    return False, "Repository is archived"
                return True, None
            elif response.status_code == 404:
                return False, "Repository not found"
            else:
                return False, f"HTTP {response.status_code}"

        except Exception as e:
            return False, str(e)


# ========== Format Checker ==========

class FormatChecker:
    """Check skill file formats."""

    YAML_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def __init__(self, config: Config):
        """Initialize format checker.

        Args:
            config: Configuration object
        """
        self.config = config
        self.required_fields = config.get("health_check.checks.format_check.required_fields", ["name", "description"])
        self.recommended_fields = config.get("health_check.checks.format_check.recommended_fields", ["category", "tags"])
        self.max_file_size = config.get("health_check.checks.format_check.max_file_size", 1048576)

    def check_content(self, content: str) -> FormatCheckResult:
        """Check content format.

        Args:
            content: Skill file content

        Returns:
            FormatCheckResult
        """
        result = FormatCheckResult(
            has_frontmatter=False,
            has_required_fields=False,
            is_valid=True
        )

        # Check file size
        if len(content.encode()) > self.max_file_size:
            result.yaml_errors.append(f"File size exceeds maximum ({self.max_file_size} bytes)")
            result.is_valid = False

        # Check for YAML frontmatter
        match = self.YAML_PATTERN.match(content)
        if match:
            result.has_frontmatter = True

            # Parse YAML
            try:
                import yaml
                metadata = yaml.safe_load(match.group(1))

                if not isinstance(metadata, dict):
                    result.yaml_errors.append("YAML frontmatter is not a dictionary")
                    result.is_valid = False
                    return result

                # Check required fields
                missing = []
                for field in self.required_fields:
                    if field not in metadata or not metadata[field]:
                        missing.append(field)
                        result.is_valid = False

                result.missing_fields = missing
                result.has_required_fields = len(missing) == 0

            except yaml.YAMLError as e:
                result.yaml_errors.append(f"YAML parse error: {e}")
                result.is_valid = False

        else:
            result.yaml_errors.append("No YAML frontmatter found")
            result.is_valid = False

        return result


# ========== Staleness Checker ==========

class StalenessChecker:
    """Check for stale repositories."""

    def __init__(self, config: Config):
        """Initialize staleness checker.

        Args:
            config: Configuration object
        """
        self.config = config
        self.stale_threshold = config.health_stale_days
        self.critical_threshold = config.get("health_check.checks.staleness_check.critical_threshold_days", 365)

    def check_skill(self, skill: SkillInfo) -> StalenessCheckResult:
        """Check if a skill's source repository is stale.

        Args:
            skill: SkillInfo to check

        Returns:
            StalenessCheckResult
        """
        result = StalenessCheckResult(
            is_stale=False,
            repo_archived=False,
            repo_deleted=False
        )

        # Check if we have timestamp info
        if skill.source_updated_at:
            try:
                last_update = datetime.fromisoformat(skill.source_updated_at.replace('Z', '+00:00'))
                days_since = (datetime.now(last_update.tzinfo) - last_update).days
                result.days_since_update = days_since
                result.last_commit_date = skill.source_updated_at

                if days_since > self.stale_threshold:
                    result.is_stale = True

            except Exception as e:
                logger.warning(f"Could not parse timestamp for {skill.source_repo}: {e}")

        return result

    def check_repo_with_github(self, repo_name: str) -> StalenessCheckResult:
        """Check repository staleness using GitHub API.

        Args:
            repo_name: Repository name (owner/repo)

        Returns:
            StalenessCheckResult
        """
        result = StalenessCheckResult(
            is_stale=False,
            repo_archived=False,
            repo_deleted=False
        )

        try:
            import requests
            token = self.config.github_token
            headers = {}
            if token:
                headers["Authorization"] = f"token {token}"

            url = f"https://api.github.com/repos/{repo_name}"
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 404:
                result.repo_deleted = True
                result.is_stale = True
                return result

            if response.status_code != 200:
                return result

            data = response.json()

            # Check archived status
            if data.get("archived"):
                result.repo_archived = True
                result.is_stale = True

            # Check last update
            pushed_at = data.get("pushed_at")
            if pushed_at:
                try:
                    last_push = datetime.fromisoformat(pushed_at.replace('Z', '+00:00'))
                    days_since = (datetime.now(last_push.tzinfo) - last_push).days
                    result.days_since_update = days_since
                    result.last_commit_date = pushed_at

                    if days_since > self.stale_threshold:
                        result.is_stale = True

                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Could not check staleness for {repo_name}: {e}")

        return result


# ========== Syntax Checker ==========

class SyntaxChecker:
    """Check Markdown syntax."""

    def __init__(self, config: Config):
        """Initialize syntax checker.

        Args:
            config: Configuration object
        """
        self.config = config
        self.check_headings = config.get("health_check.checks.syntax_check.check_headings", True)
        self.check_code_blocks = config.get("health_check.checks.syntax_check.check_code_blocks", True)
        self.max_heading_level = config.get("health_check.checks.syntax_check.max_heading_level", 6)

    def check_content(self, content: str) -> List[str]:
        """Check Markdown syntax.

        Args:
            content: Content to check

        Returns:
            List of warning/error messages
        """
        errors = []

        if self.check_headings:
            # Check for heading levels
            for match in re.finditer(r"^(#{1,6})\s", content, re.MULTILINE):
                level = len(match.group(1))
                if level > self.max_heading_level:
                    errors.append(f"Invalid heading level: {level}")

        if self.check_code_blocks:
            # Check for unclosed code blocks
            open_ticks = content.count("```")
            if open_ticks % 2 != 0:
                errors.append("Unclosed code block detected")

        return errors


# ========== Main Health Checker ==========

class HealthChecker:
    """Main health checker that runs all health checks."""

    def __init__(self, config: Config, tracker: Tracker):
        """Initialize health checker.

        Args:
            config: Configuration object
            tracker: Tracker instance
        """
        self.config = config
        self.tracker = tracker

        # Initialize checkers
        self.link_checker = LinkChecker(config)
        self.format_checker = FormatChecker(config)
        self.staleness_checker = StalenessChecker(config)
        self.syntax_checker = SyntaxChecker(config)

        logger.info("HealthChecker initialized")

    def run_all_checks(self, skill: SkillInfo, check_types: List[str] = None) -> Dict[str, Any]:
        """Run all health checks on a skill.

        Args:
            skill: SkillInfo to check
            check_types: Optional list of check types to run

        Returns:
            Dictionary with check results
        """
        if check_types is None:
            check_types = ["link", "format", "staleness"]

        results = {
            "skill_hash": skill.file_hash,
            "skill_name": skill.skill_name,
            "source_repo": skill.source_repo,
            "source_url": skill.source_url,
            "checks": {},
            "overall_status": "passed",
        }

        all_passed = True

        # Link check
        if "link" in check_types:
            link_result = self.link_checker.check_url(skill.source_url)
            results["checks"]["link"] = {
                "passed": link_result.is_accessible,
                "status_code": link_result.status_code,
                "error": link_result.error,
            }

            if not link_result.is_accessible:
                all_passed = False

            # Store in database
            check_status = "passed" if link_result.is_accessible else "failed"
            self.tracker.add_health_check(
                skill_id=skill.file_hash,
                check_type="link",
                check_result=check_status,
                check_details=json.dumps({
                    "status_code": link_result.status_code,
                    "error": link_result.error,
                })
            )

        # Format check (requires reading local file)
        if "format" in check_types and skill.local_path:
            try:
                content = self._read_skill_content(skill)
                if content:
                    format_result = self.format_checker.check_content(content)
                    results["checks"]["format"] = {
                        "passed": format_result.is_valid,
                        "has_frontmatter": format_result.has_frontmatter,
                        "missing_fields": format_result.missing_fields,
                        "errors": format_result.yaml_errors,
                    }

                    if not format_result.is_valid:
                        all_passed = False

                    self.tracker.add_health_check(
                        skill_id=skill.file_hash,
                        check_type="format",
                        check_result="passed" if format_result.is_valid else "failed",
                        check_details=json.dumps({
                            "has_frontmatter": format_result.has_frontmatter,
                            "missing_fields": format_result.missing_fields,
                        })
                    )
            except Exception as e:
                logger.warning(f"Could not check format for {skill.file_hash}: {e}")

        # Staleness check
        if "staleness" in check_types:
            staleness_result = self.staleness_checker.check_skill(skill)
            results["checks"]["staleness"] = {
                "passed": not staleness_result.is_stale,
                "is_stale": staleness_result.is_stale,
                "days_since_update": staleness_result.days_since_update,
                "repo_archived": staleness_result.repo_archived,
                "repo_deleted": staleness_result.repo_deleted,
            }

            if staleness_result.is_stale:
                all_passed = False

            check_status = "passed"
            if staleness_result.repo_deleted:
                check_status = "failed"
            elif staleness_result.is_stale:
                check_status = "warning"

            self.tracker.add_health_check(
                skill_id=skill.file_hash,
                check_type="staleness",
                check_result=check_status,
                check_details=json.dumps({
                    "days_since_update": staleness_result.days_since_update,
                    "repo_archived": staleness_result.repo_archived,
                })
            )

        # Syntax check
        if "syntax" in check_types and skill.local_path:
            try:
                content = self._read_skill_content(skill)
                if content:
                    syntax_errors = self.syntax_checker.check_content(content)
                    results["checks"]["syntax"] = {
                        "passed": len(syntax_errors) == 0,
                        "errors": syntax_errors,
                    }

                    if syntax_errors:
                        all_passed = False

                    self.tracker.add_health_check(
                        skill_id=skill.file_hash,
                        check_type="syntax",
                        check_result="passed" if not syntax_errors else "warning",
                        check_details=json.dumps({"errors": syntax_errors})
                    )
            except Exception as e:
                logger.warning(f"Could not check syntax for {skill.file_hash}: {e}")

        results["overall_status"] = "passed" if all_passed else "failed"
        return results

    def run_full_check(self, limit: int = None) -> HealthCheckSummary:
        """Run health checks on all skills.

        Args:
            limit: Optional limit on number of skills to check

        Returns:
            HealthCheckSummary
        """
        logger.info("Running full health check")

        skills = self.tracker.get_all_processed()
        if limit:
            skills = skills[:limit]

        summary = HealthCheckSummary(
            total_skills=len(skills),
            healthy=0,
            warnings=0,
            failed=0,
            skipped=0,
        )

        check_details = {
            "link": {"passed": 0, "failed": 0, "warning": 0},
            "format": {"passed": 0, "failed": 0, "warning": 0},
            "staleness": {"passed": 0, "failed": 0, "warning": 0},
            "syntax": {"passed": 0, "failed": 0, "warning": 0},
        }

        for skill in skills:
            try:
                result = self.run_all_checks(skill)

                if result["overall_status"] == "passed":
                    summary.healthy += 1
                else:
                    summary.failed += 1

                # Track check type results
                for check_type, check_result in result["checks"].items():
                    status = check_result.get("passed", False)
                    if status:
                        check_details[check_type]["passed"] += 1
                    else:
                        check_details[check_type]["failed"] += 1

            except Exception as e:
                logger.error(f"Error checking skill {skill.file_hash}: {e}")
                summary.failed += 1

        summary.check_details = check_details
        logger.info(f"Full health check complete: {summary}")
        return summary

    def run_daily_check(self) -> HealthCheckSummary:
        """Run health check on recently added/updated skills.

        Returns:
            HealthCheckSummary
        """
        logger.info("Running daily health check")

        # Get skills checked in the last 24 hours or without health check
        cutoff = datetime.utcnow() - timedelta(hours=24)

        # For simplicity, check all skills (could be optimized)
        return self.run_full_check()

    def get_unhealthy_skills(self, status: str = "failed") -> List[Dict[str, Any]]:
        """Get unhealthy skills with details.

        Args:
            status: Health status to filter by

        Returns:
            List of skill details with health info
        """
        skills = self.tracker.get_unhealthy_skills(status)
        results = []

        for skill in skills:
            latest_check = self.tracker.get_latest_health_check(skill.file_hash)

            result = {
                "hash": skill.file_hash,
                "name": skill.skill_name,
                "source_repo": skill.source_repo,
                "source_url": skill.source_url,
                "health_status": skill.health_status,
                "last_check": skill.last_health_check,
            }

            if latest_check:
                result["latest_check"] = {
                    "type": latest_check.check_type,
                    "result": latest_check.check_result,
                    "details": latest_check.check_details,
                    "checked_at": latest_check.checked_at,
                }

            results.append(result)

        return results

    def generate_report(self) -> str:
        """Generate a health check report.

        Returns:
            Markdown formatted report
        """
        summary = self.run_full_check()
        unhealthy = self.get_unhealthy_skills("failed")

        report = f"""# SkillFlow Health Check Report

Generated: {datetime.utcnow().isoformat()}

## Summary

- **Total Skills:** {summary.total_skills}
- **Healthy:** {summary.healthy} ({summary.healthy_percentage:.1f}%)
- **Failed:** {summary.failed} ({summary.failed_percentage:.1f}%)
- **Warnings:** {summary.warnings}

## Check Results

| Check Type | Passed | Failed | Warnings |
|------------|--------|--------|----------|
"""

        for check_type, details in summary.check_details.items():
            report += f"| {check_type.capitalize()} | {details['passed']} | {details['failed']} | {details.get('warning', 0)} |\n"

        if unhealthy:
            report += f"\n## Unhealthy Skills ({len(unhealthy)})\n\n"
            for skill in unhealthy[:20]:  # Limit to 20
                report += f"- **{skill.get('name', skill['hash'][:16])}** ({skill['source_repo']})\n"
                if skill.get('latest_check'):
                    report += f"  - {skill['latest_check']['type']}: {skill['latest_check']['result']}\n"

            if len(unhealthy) > 20:
                report += f"\n... and {len(unhealthy) - 20} more\n"

        return report

    def _read_skill_content(self, skill: SkillInfo) -> Optional[str]:
        """Read skill content from local file.

        Args:
            skill: SkillInfo with local_path

        Returns:
            File content or None
        """
        if not skill.local_path:
            return None

        try:
            from pathlib import Path
            path = Path(skill.local_path)
            if path.exists():
                return path.read_text(encoding='utf-8')
        except Exception as e:
            logger.warning(f"Could not read skill content from {skill.local_path}: {e}")

        return None


# ========== Standalone Functions ==========

def run_health_check(config: Config, check_type: str = "full") -> Dict[str, Any]:
    """Run health checks (standalone function).

    Args:
        config: Configuration object
        check_type: Type of check to run ('full', 'daily', 'report')

    Returns:
        Check results or summary
    """
    tracker = Tracker(config)
    checker = HealthChecker(config, tracker)

    if check_type == "full":
        summary = checker.run_full_check()
        return {
            "summary": {
                "total": summary.total_skills,
                "healthy": summary.healthy,
                "failed": summary.failed,
                "warnings": summary.warnings,
            },
            "check_details": summary.check_details,
        }
    elif check_type == "daily":
        summary = checker.run_daily_check()
        return {
            "summary": {
                "total": summary.total_skills,
                "healthy": summary.healthy,
                "failed": summary.failed,
            },
        }
    elif check_type == "report":
        return {"report": checker.generate_report()}
    else:
        return {"error": f"Unknown check type: {check_type}"}
