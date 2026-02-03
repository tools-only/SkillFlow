"""Issue Analyzer module for analyzing GitHub Issues.

This module provides security checking, content extraction, and
author validation for GitHub Issues in the SkillFlow system.
"""

import logging
import re
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


# ========== Data Classes ==========

@dataclass
class FilterResult:
    """Result of security filtering."""
    is_malicious: bool
    severity: str  # 'low', 'medium', 'high', 'critical'
    reason: str
    patterns_matched: List[str] = field(default_factory=list)


@dataclass
class AuthorInfo:
    """Information about an issue author."""
    username: str
    account_age_days: Optional[int] = None
    contributions: Optional[int] = None
    is_suspicious: bool = False
    suspicion_reasons: List[str] = field(default_factory=list)


@dataclass
class ExtractedRequirement:
    """A requirement extracted from an issue."""
    requirement_type: str  # 'repo-request', 'feature-request', 'config-update', 'bug-report'
    data: Dict[str, Any]
    confidence: float  # 0.0 to 1.0
    source_text: str


@dataclass
class ParsedIssue:
    """Result of parsing an issue."""
    issue_type: str
    repositories: List[str]
    features: List[str]
    configs: Dict[str, Any]
    raw_data: Dict[str, Any]


# ========== Security Checker ==========

class SecurityChecker:
    """Check for malicious content in issues."""

    # Malicious patterns to detect
    MALICIOUS_PATTERNS = [
        (r"rm\s+-rf\s+/", "command_injection", "critical"),
        (r"rm\s+-rf\s+\*", "command_injection", "critical"),
        (r"rm\s+-rf\s+\.git", "repo_destruction", "critical"),
        (r"drop\s+table", "sql_injection", "high"),
        (r"delete\s+from\s+\w+\s+where", "sql_injection", "high"),
        (r"eval\s*\(", "code_execution", "high"),
        (r"exec\s*\(", "code_execution", "high"),
        (r"__import__\s*\(", "python_import", "high"),
        (r"subprocess\.", "subprocess", "medium"),
        (r"os\.system", "system_command", "medium"),
        (r"shell_exec", "shell_command", "medium"),
        (r"passthru\(", "php_execution", "high"),
        (r"<\?php", "php_injection", "medium"),
        (r"format\s+disk", "disk_destruction", "critical"),
        (r"format\s+c:", "disk_destruction", "critical"),
    ]

    # Blocked keywords
    BLOCKED_KEYWORDS = [
        "delete all",
        "remove all",
        "format disk",
        "wipe database",
        "destroy repo",
        "nuke",
        "crypto mining",
        "bitcoin miner",
        "malware",
        "backdoor",
        "trojan",
        "ransomware",
        "exploit kit",
        "botnet",
    ]

    # Suspicious patterns
    SUSPICIOUS_PATTERNS = [
        (r"(?i)crypto|bitcoin|mining|xmr|monero", "crypto_mining", "low"),
        (r"(?i)access_token|api_key|secret", "credential_theft", "medium"),
        (r"(?i)phish|credential|password", "phishing", "medium"),
        (r"(?i)0x[0-9a-f]{16,}", "shellcode_pattern", "high"),
    ]

    def __init__(self, config_path: str = None):
        """Initialize security checker.

        Args:
            config_path: Optional path to security rules config file
        """
        self.malicious_patterns = self.MALICIOUS_PATTERNS[:]
        self.blocked_keywords = self.BLOCKED_KEYWORDS[:]
        self.suspicious_patterns = self.SUSPICIOUS_PATTERNS[:]

        if config_path:
            self._load_config(config_path)

    def _load_config(self, config_path: str) -> None:
        """Load security rules from config file."""
        try:
            import yaml
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            if 'malicious_patterns' in config:
                self.malicious_patterns.extend([
                    (p['pattern'], p['type'], p['severity'])
                    for p in config['malicious_patterns']
                ])

            if 'blocked_keywords' in config:
                self.blocked_keywords.extend(config['blocked_keywords'])

            logger.info(f"Loaded security rules from {config_path}")
        except Exception as e:
            logger.warning(f"Could not load security config: {e}")

    def check(self, text: str) -> FilterResult:
        """Check text for malicious content.

        Args:
            text: Text to check

        Returns:
            FilterResult with analysis
        """
        matched_patterns = []
        max_severity = "low"

        # Check malicious patterns
        for pattern, ptype, severity in self.malicious_patterns:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                matched_patterns.append(f"{ptype}: {pattern}")
                if self._severity_rank(severity) > self._severity_rank(max_severity):
                    max_severity = severity

        # Check blocked keywords
        text_lower = text.lower()
        for keyword in self.blocked_keywords:
            if keyword.lower() in text_lower:
                matched_patterns.append(f"blocked_keyword: {keyword}")
                if self._severity_rank("high") > self._severity_rank(max_severity):
                    max_severity = "high"

        # Check suspicious patterns
        for pattern, ptype, severity in self.suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                matched_patterns.append(f"suspicious: {ptype}")
                if self._severity_rank(severity) > self._severity_rank(max_severity):
                    max_severity = severity

        is_malicious = len(matched_patterns) > 0

        return FilterResult(
            is_malicious=is_malicious,
            severity=max_severity,
            reason=f"Found {len(matched_patterns)} suspicious patterns" if is_malicious else "No issues found",
            patterns_matched=matched_patterns
        )

    def _severity_rank(self, severity: str) -> int:
        """Get numeric rank for severity comparison."""
        ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return ranks.get(severity, 0)


# ========== Issue Parser ==========

class IssueParser:
    """Parse issue content to extract structured information."""

    # GitHub repository URL patterns
    REPO_PATTERNS = [
        r"github\.com/([\w-]+/[\w-]+)",
        r"(?:https?://)?(?:www\.)?github\.com/([\w-]+/[\w-]+)",
        r"`([\w-]+/[\w-]+)`",
        r"\*\*([\w-]+/[\w-]+)\*\*",
    ]

    # Issue type indicators
    TYPE_INDICATORS = {
        "repo-request": ["add repo", "add repository", "repository request", "new repo", "include repo"],
        "feature-request": ["feature", "enhancement", "improvement", "add feature", "new feature"],
        "bug-report": ["bug", "issue", "error", "not working", "broken", "fix"],
        "config-update": ["config", "configuration", "setting", "update config", "change config"],
    }

    def __init__(self):
        """Initialize issue parser."""
        self.repo_pattern = re.compile("|".join(self.REPO_PATTERNS), re.IGNORECASE)

    def parse(self, title: str, body: str, labels: List[str] = None) -> ParsedIssue:
        """Parse an issue to extract structured information.

        Args:
            title: Issue title
            body: Issue body
            labels: Issue labels

        Returns:
            ParsedIssue with extracted data
        """
        full_text = f"{title}\n\n{body or ''}"
        labels = labels or []

        # Determine issue type
        issue_type = self._detect_issue_type(title, body, labels)

        # Extract repositories
        repositories = self._extract_repositories(full_text)

        # Extract feature descriptions
        features = self._extract_features(full_text)

        # Extract config updates
        configs = self._extract_configs(full_text)

        return ParsedIssue(
            issue_type=issue_type,
            repositories=repositories,
            features=features,
            configs=configs,
            raw_data={
                "title": title,
                "body": body,
                "labels": labels,
                "full_text": full_text,
            }
        )

    def _detect_issue_type(self, title: str, body: str, labels: List[str]) -> str:
        """Detect the type of issue."""
        text = f"{title} {body}".lower()

        # Check labels first
        label_map = {
            "repo-request": "repo-request",
            "repository": "repo-request",
            "enhancement": "feature-request",
            "feature": "feature-request",
            "bug": "bug-report",
            "config": "config-update",
        }

        for label in labels:
            label_lower = label.lower()
            if label_lower in label_map:
                return label_map[label_lower]

        # Check text content
        for issue_type, indicators in self.TYPE_INDICATORS.items():
            for indicator in indicators:
                if indicator in text:
                    return issue_type

        return "unknown"

    def _extract_repositories(self, text: str) -> List[str]:
        """Extract GitHub repository URLs/names from text."""
        repos = set()

        for match in self.repo_pattern.finditer(text):
            repo = match.group(1)
            if repo and "/" in repo:
                # Clean up the repo name
                repo = repo.strip().rstrip("/")
                repos.add(repo)

        return sorted(list(repos))

    def _extract_features(self, text: str) -> List[str]:
        """Extract feature descriptions from text."""
        features = []

        # Look for bullet points or numbered lists
        lines = text.split("\n")
        in_list = False

        for line in lines:
            stripped = line.strip()

            # Check for list markers
            if re.match(r"^[\s]*(?:[-*+]|\d+\.)\s+", stripped):
                in_list = True
                feature = re.sub(r"^[\s]*(?:[-*+]|\d+\.)\s+", "", stripped)
                if len(feature) > 5 and len(feature) < 500:
                    features.append(feature)
            elif in_list and not stripped:
                in_list = False

        return features

    def _extract_configs(self, text: str) -> Dict[str, Any]:
        """Extract configuration updates from text."""
        configs = {}

        # Look for YAML or JSON blocks
        yaml_pattern = r"```(?:ya?ml|yaml)\n(.*?)```"
        json_pattern = r"```(?:json)?\n(.*?)```"

        for match in re.finditer(yaml_pattern, text, re.DOTALL):
            try:
                import yaml
                yaml_content = match.group(1)
                parsed = yaml.safe_load(yaml_content)
                if isinstance(parsed, dict):
                    configs.update(parsed)
            except Exception:
                pass

        for match in re.finditer(json_pattern, text, re.DOTALL):
            try:
                json_content = match.group(1)
                parsed = json.loads(json_content)
                if isinstance(parsed, dict):
                    configs.update(parsed)
            except Exception:
                pass

        return configs


# ========== Author Validator ==========

class AuthorValidator:
    """Validate issue author reputation."""

    def __init__(self, min_age_days: int = 7, min_contributions: int = 1):
        """Initialize author validator.

        Args:
            min_age_days: Minimum account age in days
            min_contributions: Minimum number of contributions
        """
        self.min_age_days = min_age_days
        self.min_contributions = min_contributions

    async def validate(self, github, username: str) -> AuthorInfo:
        """Validate an author's reputation.

        Args:
            github: GitHub API client
            username: GitHub username

        Returns:
            AuthorInfo with validation results
        """
        suspicion_reasons = []

        try:
            user = github.get_user(username)

            # Get account age
            created_at = user.created_at
            if created_at:
                account_age = (datetime.now(created_at.tzinfo) - created_at).days
            else:
                account_age = None

            # Get public contribution count
            # Note: This is an approximation using public repos
            contributions = 0
            try:
                repos = list(user.get_repos()[:100])  # Limit to 100 repos
                contributions = len(repos)
            except Exception:
                contributions = None

            # Check for suspicious patterns
            is_suspicious = False

            if account_age is not None and account_age < self.min_age_days:
                is_suspicious = True
                suspicion_reasons.append(f"Account age ({account_age} days) below minimum ({self.min_age_days})")

            if contributions is not None and contributions < self.min_contributions:
                is_suspicious = True
                suspicion_reasons.append(f"Low contribution count ({contributions})")

            # Check for default avatar (often indicates fake account)
            try:
                if user.avatar_url and "identicon" in user.avatar_url:
                    is_suspicious = True
                    suspicion_reasons.append("Using default identicon avatar")
            except Exception:
                pass

            return AuthorInfo(
                username=username,
                account_age_days=account_age,
                contributions=contributions,
                is_suspicious=is_suspicious,
                suspicion_reasons=suspicion_reasons
            )

        except Exception as e:
            logger.warning(f"Could not validate author {username}: {e}")
            return AuthorInfo(
                username=username,
                is_suspicious=True,
                suspicion_reasons=["Could not fetch author information"]
            )


# ========== Requirement Extractor ==========

class RequirementExtractor:
    """Extract structured requirements from parsed issues."""

    def __init__(self):
        """Initialize requirement extractor."""
        pass

    def extract(self, parsed_issue: ParsedIssue) -> List[ExtractedRequirement]:
        """Extract requirements from a parsed issue.

        Args:
            parsed_issue: Parsed issue data

        Returns:
            List of ExtractedRequirement objects
        """
        requirements = []

        # Extract repo requests
        if parsed_issue.issue_type == "repo-request" and parsed_issue.repositories:
            for repo in parsed_issue.repositories:
                requirements.append(ExtractedRequirement(
                    requirement_type="repo-request",
                    data={"repository": repo},
                    confidence=0.9,
                    source_text=f"Add repository: {repo}"
                ))

        # Extract feature requests
        if parsed_issue.issue_type == "feature-request" and parsed_issue.features:
            for feature in parsed_issue.features:
                requirements.append(ExtractedRequirement(
                    requirement_type="feature-request",
                    data={"feature": feature},
                    confidence=0.7,
                    source_text=feature
                ))

        # Extract config updates
        if parsed_issue.configs:
            requirements.append(ExtractedRequirement(
                requirement_type="config-update",
                data=parsed_issue.configs,
                confidence=0.8,
                source_text=json.dumps(parsed_issue.configs)
            ))

        # Extract search terms
        search_terms = self._extract_search_terms(parsed_issue.raw_data["full_text"])
        if search_terms:
            requirements.append(ExtractedRequirement(
                requirement_type="search-terms",
                data={"terms": search_terms},
                confidence=0.8,
                source_text=", ".join(search_terms)
            ))

        return requirements

    def _extract_search_terms(self, text: str) -> List[str]:
        """Extract search terms from text."""
        terms = []

        # Look for patterns like "search term: X" or "add term: X"
        patterns = [
            r"search term[s]?:\s*([^\n]+)",
            r"add term[s]?:\s*([^\n]+)",
            r"keyword[s]?:\s*([^\n]+)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                term_text = match.group(1).strip()
                # Split by commas and clean up
                for term in re.split(r"[,;]", term_text):
                    term = term.strip().strip('"\'')
                    if 2 <= len(term) <= 100:
                        terms.append(term)

        return terms


# ========== Main Analyzer Interface ==========

class IssueAnalyzer:
    """Main issue analyzer that combines all analysis components."""

    def __init__(self, security_config_path: str = None,
                 min_author_age_days: int = 7,
                 min_author_contributions: int = 1):
        """Initialize issue analyzer.

        Args:
            security_config_path: Path to security rules config
            min_author_age_days: Minimum author account age
            min_author_contributions: Minimum author contributions
        """
        self.security_checker = SecurityChecker(security_config_path)
        self.issue_parser = IssueParser()
        self.author_validator = AuthorValidator(min_author_age_days, min_author_contributions)
        self.requirement_extractor = RequirementExtractor()

    def analyze(self, title: str, body: str, author: str,
                labels: List[str] = None, github_client=None) -> Dict[str, Any]:
        """Perform complete analysis of an issue.

        Args:
            title: Issue title
            body: Issue body
            author: Issue author username
            labels: Issue labels
            github_client: Optional GitHub API client for author validation

        Returns:
            Dictionary with analysis results
        """
        result = {
            "safe": False,
            "issue_type": "unknown",
            "requirements": [],
            "filter_reason": None,
            "author_info": None,
            "parsed_data": None,
        }

        full_text = f"{title}\n\n{body or ''}"

        # Step 1: Security check
        security_result = self.security_checker.check(full_text)
        if security_result.is_malicious:
            result["safe"] = False
            result["filter_reason"] = f"Security check failed: {security_result.reason}"
            result["security_result"] = {
                "severity": security_result.severity,
                "patterns": security_result.patterns_matched
            }
            return result

        # Step 2: Parse issue
        parsed = self.issue_parser.parse(title, body, labels)
        result["parsed_data"] = {
            "issue_type": parsed.issue_type,
            "repositories": parsed.repositories,
            "features": parsed.features,
            "configs": parsed.configs,
        }
        result["issue_type"] = parsed.issue_type

        # Step 3: Author validation (if client provided)
        if github_client:
            import asyncio
            try:
                # Try to run async, fall back to sync
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                author_info = loop.run_until_complete(
                    self.author_validator.validate(github_client, author)
                )
                result["author_info"] = {
                    "username": author_info.username,
                    "account_age_days": author_info.account_age_days,
                    "contributions": author_info.contributions,
                    "is_suspicious": author_info.is_suspicious,
                    "suspicion_reasons": author_info.suspicion_reasons,
                }

                # Filter if author is suspicious
                if author_info.is_suspicious:
                    result["safe"] = False
                    result["filter_reason"] = f"Author validation failed: {', '.join(author_info.suspicion_reasons)}"
                    return result

            except Exception as e:
                logger.warning(f"Author validation failed for {author}: {e}")

        # Step 4: Extract requirements
        requirements = self.requirement_extractor.extract(parsed)
        result["requirements"] = [
            {
                "type": r.requirement_type,
                "data": r.data,
                "confidence": r.confidence,
                "source": r.source_text,
            }
            for r in requirements
        ]

        result["safe"] = True
        return result
