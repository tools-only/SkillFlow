"""Search Term Optimizer - Manual CLI for optimizing search terms.

This module provides manual CLI commands for:
- Analyzing current search term effectiveness
- Suggesting new search terms based on existing skills
- Updating the search_terms.yaml configuration

All commands are manually triggered - no automatic optimization.
"""

import argparse
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import yaml

from .config import Config
from .tracker import Tracker


logger = logging.getLogger(__name__)


@dataclass
class TermMetrics:
    """Metrics for a search term."""
    term: str
    use_count: int = 0
    last_used: str = ""
    success_rate: float = 0.0
    avg_repos_found: float = 0.0
    avg_repo_stars: float = 0.0


class SearchTermOptimizer:
    """Manual search term optimizer.

    This class provides methods to analyze current search terms,
    suggest new ones based on existing skills, and update the config.
    """

    def __init__(self, config: Config):
        """Initialize the optimizer.

        Args:
            config: Configuration object
        """
        self.config = config
        self.tracker = Tracker(config)

    def analyze_current_terms(self) -> Dict[str, TermMetrics]:
        """Analyze current search terms.

        Since we don't have historical metrics, this returns
        basic info about current terms.

        Returns:
            Dict mapping term to TermMetrics
        """
        metrics = {}
        current_time = datetime.utcnow().isoformat()

        for term in self.config.search_terms:
            metrics[term] = TermMetrics(
                term=term,
                use_count=0,  # Not tracked in manual mode
                last_used=current_time,
                success_rate=0.0,
                avg_repos_found=0.0,
                avg_repo_stars=0.0,
            )

        return metrics

    def _extract_tags_from_skills(self) -> Counter:
        """Extract all tags from processed skills.

        Returns:
            Counter of tag frequencies
        """
        skills = self.tracker.get_all_processed()
        tag_counter = Counter()

        for skill in skills:
            # Tags aren't directly stored in SkillInfo
            # We'd need to read from skill files or index
            pass

        return tag_counter

    def _extract_keywords_from_content(self, content: str, top_n: int = 20) -> List[str]:
        """Extract high-frequency keywords from skill content.

        Args:
            content: Skill content
            top_n: Number of top keywords to return

        Returns:
            List of keywords
        """
        # Common words to filter out
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we',
            'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
            'skill', 'claude', 'ai', 'agent', 'tool', 'use', 'your', 'user',
        }

        # Extract words (lowercase, alphanumeric)
        words = re.findall(r'\b[a-z][a-z0-9-]*\b', content.lower())

        # Filter stop words and short words
        words = [w for w in words if w not in stop_words and len(w) >= 3]

        return Counter(words).most_common(top_n)

    def _get_github_topics_for_repos(self) -> Dict[str, List[str]]:
        """Get GitHub topics for indexed repositories.

        Note: This would require GitHub API calls. For manual mode,
        we return empty dict as topics would need to be fetched separately.

        Returns:
            Dict mapping repo to list of topics
        """
        return {}

    def suggest_new_terms(self, existing_skills_count: int = 0) -> List[str]:
        """Suggest new search terms based on analysis.

        Args:
            existing_skills_count: Number of existing skills (for context)

        Returns:
            List of suggested search terms
        """
        suggestions = []

        # Base suggestions from common AI/skill categories
        base_suggestions = [
            # AI/ML categories
            "machine-learning",
            "deep-learning",
            "nlp",
            "computer-vision",
            "ai-assistant",
            "llm",
            "prompt-engineering",

            # Development categories
            "code-generation",
            "refactoring",
            "debugging",
            "testing",
            "api",
            "github-actions",
            "devops",

            # Data categories
            "data-analysis",
            "visualization",
            "etl",
            "csv",
            "json",

            # Productivity
            "automation",
            "workflow",
            "productivity",
            "task-management",

            # Content categories
            "writing",
            "content-generation",
            "documentation",

            # Research
            "research",
            "academic",
            "citation",
        ]

        # Filter out existing terms
        existing_terms = set(self.config.search_terms)
        new_suggestions = [t for t in base_suggestions if t.lower() not in existing_terms]

        return new_suggestions

    def generate_report(self) -> str:
        """Generate optimization report.

        Returns:
            Report string
        """
        metrics = self.analyze_current_terms()
        suggestions = self.suggest_new_terms()

        lines = [
            "=" * 60,
            "Search Term Optimization Report",
            "=" * 60,
            "",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            f"Current search terms: {len(metrics)}",
            "",
            "Current Terms:",
            "-" * 40,
        ]

        for term, metric in sorted(metrics.items()):
            lines.append(f"  - {term}")

        lines.extend([
            "",
            "Suggested New Terms:",
            "-" * 40,
        ])

        for suggestion in suggestions:
            lines.append(f"  - {suggestion}")

        lines.extend([
            "",
            "Recommendations:",
            "-" * 40,
            "1. Review suggested terms and add relevant ones to config/search_terms.yaml",
            "2. Remove terms that consistently return no results",
            "3. Consider seasonal or trending topics in your domain",
            "",
            "To update search terms, run:",
            "  python -m src.search_term_optimizer --update",
            "",
        ])

        return "\n".join(lines)

    def update_search_terms_config(self, new_terms: List[str]) -> bool:
        """Update the search_terms.yaml configuration.

        Args:
            new_terms: List of new search terms to add

        Returns:
            True if successful, False otherwise
        """
        config_path = Path("config/search_terms.yaml")
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            return False

        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f)

            current_terms = set(data.get("search_terms", []))

            # Add new terms
            updated_terms = sorted(current_terms | set(new_terms))

            data["search_terms"] = updated_terms

            with open(config_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Updated search_terms.yaml with {len(new_terms)} new terms")
            return True

        except (IOError, yaml.YAMLError) as e:
            logger.error(f"Failed to update config: {e}")
            return False


def main():
    """Main entry point for CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Search Term Optimizer - Manual CLI"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze current search terms"
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Generate new search term suggestions"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update search_terms.yaml with suggested terms (requires confirmation)"
    )
    parser.add_argument(
        "--terms",
        nargs="+",
        help="Specific terms to add when using --update"
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt"
    )

    args = parser.parse_args()

    config = Config()
    optimizer = SearchTermOptimizer(config)

    if args.analyze:
        metrics = optimizer.analyze_current_terms()
        print(f"\nCurrent search terms ({len(metrics)}):")
        for term, metric in sorted(metrics.items()):
            print(f"  - {term}")

    elif args.suggest:
        suggestions = optimizer.suggest_new_terms()
        print(f"\nSuggested new search terms ({len(suggestions)}):")
        for term in suggestions:
            print(f"  - {term}")

    elif args.update:
        if args.terms:
            new_terms = args.terms
        else:
            new_terms = optimizer.suggest_new_terms()

        if not new_terms:
            print("No new terms to add.")
            return

        print(f"\nTerms to add ({len(new_terms)}):")
        for term in new_terms:
            print(f"  - {term}")

        if not args.yes:
            confirm = input("\nUpdate search_terms.yaml? [y/N]: ")
            if confirm.lower() != 'y':
                print("Aborted.")
                return

        if optimizer.update_search_terms_config(new_terms):
            print("✓ Updated search_terms.yaml")
        else:
            print("✗ Failed to update config")

    else:
        # Default: show full report
        print(optimizer.generate_report())


if __name__ == "__main__":
    main()
