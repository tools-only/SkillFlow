"""AI-based skill analysis using local rule-based categorization."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import Config


logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Metadata extracted from a skill file."""

    name: str
    description: str
    category: str
    subcategory: str
    tags: list[str]
    primary_purpose: str


@dataclass
class CategoryInfo:
    """Category and subcategory for a skill."""

    category: str
    subcategory: str


class SkillAnalyzer:
    """Analyze skill files using local rule-based analysis."""

    # Main categories for skills with their patterns
    CATEGORY_PATTERNS = {
        "daily-assistant": {
            "keywords": ["calendar", "schedule", "reminder", "todo", "task", "daily", "routine", "planner"],
            "subcategories": {
                "scheduling": ["schedule", "calendar", "appointment", "meeting"],
                "tasks": ["todo", "task", "checklist", "reminder"],
                "notes": ["note", "memo", "journal", "diary"],
            }
        },
        "commercial": {
            "keywords": ["ecommerce", "shop", "store", "product", "checkout", "cart", "customer", "invoice"],
            "subcategories": {
                "ecommerce": ["shop", "store", "product", "checkout", "cart"],
                "business": ["business", "invoice", "receipt", "payment"],
            }
        },
        "investment": {
            "keywords": ["stock", "trading", "finance", "investment", "portfolio", "crypto", "market"],
            "subcategories": {
                "trading": ["trade", "stock", "market"],
                "crypto": ["crypto", "bitcoin", "blockchain"],
                "analysis": ["analysis", "portfolio", "finance"],
            }
        },
        "development": {
            "keywords": ["code", "programming", "developer", "api", "git", "debug", "refactor", "testing"],
            "subcategories": {
                "coding": ["code", "programming", "developer", "function"],
                "devops": ["deploy", "docker", "ci/cd", "server"],
                "testing": ["test", "mock", "stub", "fixture"],
                "tools": ["cli", "tool", "utility", "helper"],
            }
        },
        "research": {
            "keywords": ["research", "paper", "academic", "citation", "literature", "study", "data"],
            "subcategories": {
                "academic": ["paper", "academic", "citation", "reference"],
                "data-gathering": ["scrape", "crawl", "fetch", "collect"],
            }
        },
        "content-creation": {
            "keywords": ["write", "writing", "content", "article", "blog", "post", "draft", "edit"],
            "subcategories": {
                "writing": ["write", "writing", "article", "blog"],
                "editing": ["edit", "proofread", "rewrite"],
                "media": ["image", "video", "audio", "media"],
            }
        },
        "data-analysis": {
            "keywords": ["data", "analyze", "statistics", "chart", "graph", "visualization", "csv", "json"],
            "subcategories": {
                "visualization": ["chart", "graph", "plot", "visual"],
                "processing": ["parse", "convert", "transform", "clean"],
            }
        },
        "automation": {
            "keywords": ["automate", "automation", "workflow", "batch", "script", "cron"],
            "subcategories": {
                "workflow": ["workflow", "pipeline", "automate"],
                "scripting": ["script", "batch", "macro"],
            }
        },
        "communication": {
            "keywords": ["email", "message", "chat", "notification", "slack", "discord", "telegram"],
            "subcategories": {
                "email": ["email", "mail", "newsletter"],
                "messaging": ["message", "chat", "slack", "discord"],
            }
        },
        "productivity": {
            "keywords": ["productivity", "efficient", "optimize", "speed", "boost", "focus"],
            "subcategories": {
                "time-management": ["time", "pomodoro", "focus", "timer"],
                "optimization": ["optimize", "efficient", "boost"],
            }
        },
    }

    MAIN_CATEGORIES = list(CATEGORY_PATTERNS.keys()) + ["other"]

    def __init__(self, config: Config):
        """Initialize skill analyzer.

        Args:
            config: Configuration object
        """
        self.config = config
        logger.info("Using local rule-based skill analysis (no API required)")

    def analyze_skill(self, content: str, source_repo: str) -> Optional[SkillMetadata]:
        """Analyze a skill file and extract metadata.

        Args:
            content: Skill file content
            source_repo: Source repository name

        Returns:
            SkillMetadata if successful, None otherwise
        """
        try:
            # Extract metadata from content
            name = self._extract_name(content, source_repo)
            description = self._extract_description(content)
            category, subcategory = self._categorize_skill(content)
            tags = self._extract_tags(content, category)
            primary_purpose = self._extract_purpose(content, description)

            metadata = SkillMetadata(
                name=name,
                description=description,
                category=category,
                subcategory=subcategory,
                tags=tags,
                primary_purpose=primary_purpose,
            )

            logger.info(
                f"Analyzed skill '{name}': {category}/{subcategory}"
            )
            return metadata

        except Exception as e:
            logger.error(f"Error analyzing skill: {e}")
            return None

    def _extract_name(self, content: str, source_repo: str) -> str:
        """Extract skill name from content.

        Args:
            content: Skill file content
            source_repo: Source repository name

        Returns:
            Extracted or generated name
        """
        # Try to find YAML frontmatter name
        yaml_match = re.search(r'name:\s*["\']?([^"\'\n]+)["\']?', content, re.IGNORECASE)
        if yaml_match:
            return yaml_match.group(1).strip()

        # Try to find first heading
        heading_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if heading_match:
            return heading_match.group(1).strip()

        # Use repo name as fallback
        return source_repo.split("/")[-1].replace("-", " ").replace("_", " ").title()

    def _extract_description(self, content: str) -> str:
        """Extract description from content.

        Args:
            content: Skill file content

        Returns:
            Extracted or generated description
        """
        # Try YAML frontmatter
        yaml_match = re.search(
            r'description:\s*["\']([^"\']+)["\']',
            content,
            re.IGNORECASE | re.DOTALL
        )
        if yaml_match:
            return yaml_match.group(1).strip()

        # Look for first paragraph
        paragraphs = re.split(r'\n\n+', content)
        for para in paragraphs:
            # Skip YAML and headings
            if para.strip().startswith('---') or para.strip().startswith('#'):
                continue
            # Get first meaningful paragraph
            text = re.sub(r'[#*\-`]', '', para).strip()
            if len(text) > 20 and len(text) < 300:
                return text

        return "AI skill for automation and assistance"

    def _categorize_skill(self, content: str) -> tuple[str, str]:
        """Categorize skill based on content analysis.

        Args:
            content: Skill file content

        Returns:
            Tuple of (category, subcategory)
        """
        content_lower = content.lower()

        # Score each category
        best_category = "other"
        best_subcategory = "general"
        best_score = 0

        for category, patterns in self.CATEGORY_PATTERNS.items():
            # Score main category
            category_score = sum(
                1 for keyword in patterns["keywords"]
                if keyword in content_lower
            )

            # Score subcategories
            subcategory_score = 0
            best_sub_for_category = "general"

            for subcat, sub_keywords in patterns["subcategories"].items():
                score = sum(
                    1 for keyword in sub_keywords
                    if keyword in content_lower
                )
                if score > subcategory_score:
                    subcategory_score = score
                    best_sub_for_category = subcat

            total_score = category_score + (subcategory_score * 2)

            if total_score > best_score:
                best_score = total_score
                best_category = category
                best_subcategory = best_sub_for_category

        return best_category, best_subcategory

    def _extract_tags(self, content: str, category: str) -> list[str]:
        """Extract tags from content.

        Args:
            content: Skill file content
            category: Detected category

        Returns:
            List of tags
        """
        tags = []

        # Try YAML tags
        yaml_tags = re.search(r'tags:\s*\[(.+?)\]', content, re.DOTALL)
        if yaml_tags:
            tag_content = yaml_tags.group(1)
            tags = [t.strip().strip('"\'') for t in tag_content.split(',') if t.strip()]

        # If no tags found, generate from category
        if not tags:
            tags = [category.replace("-", " ")]

        return tags[:5]  # Limit to 5 tags

    def _extract_purpose(self, content: str, description: str) -> str:
        """Extract primary purpose from content.

        Args:
            content: Skill file content
            description: Extracted description

        Returns:
            Primary purpose statement
        """
        # Try YAML frontmatter
        yaml_match = re.search(
            r'purpose:\s*["\']([^"\']+)["\']',
            content,
            re.IGNORECASE
        )
        if yaml_match:
            return yaml_match.group(1).strip()

        # Use description as purpose
        return description

    def categorize_skill(self, metadata: SkillMetadata) -> CategoryInfo:
        """Get category info from metadata.

        Args:
            metadata: Skill metadata

        Returns:
            CategoryInfo object
        """
        # Normalize category
        category = metadata.category.lower().replace(" ", "-").replace("_", "-")
        if category not in self.MAIN_CATEGORIES:
            category = "other"

        # Normalize subcategory
        subcategory = metadata.subcategory.lower().replace(" ", "-").replace("_", "-")
        if not subcategory or subcategory == "":
            subcategory = "general"

        return CategoryInfo(category=category, subcategory=subcategory)

    def analyze_batch(
        self, skills: list[tuple[str, str]]
    ) -> list[Optional[SkillMetadata]]:
        """Analyze multiple skills in batch.

        Args:
            skills: List of (content, source_repo) tuples

        Returns:
            List of SkillMetadata objects
        """
        results: list[Optional[SkillMetadata]] = []

        for content, source_repo in skills:
            metadata = self.analyze_skill(content, source_repo)
            results.append(metadata)

        return results
