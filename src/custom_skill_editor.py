"""Custom Skill Editor - Create and manage custom skills.

Provides functionality to create custom skills from templates,
edit skills, and add skills to custom patches.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import Config


logger = logging.getLogger(__name__)


# Skill templates
SKILL_TEMPLATES = {
    "basic": """# {name}

You are a specialized AI assistant for {purpose}.

## Capabilities

- {capability_1}
- {capability_2}
- {capability_3}

## Instructions

1. Always be helpful and accurate
2. Ask clarifying questions when needed
3. Provide detailed, actionable responses

## Context

This skill was created for custom use with Claude Code.
Created: {date}
""",
    "research": """# {name}

You are a specialized research assistant for {purpose}.

## Research Methodology

1. **Source Selection**: Prioritize peer-reviewed, authoritative sources
2. **Critical Evaluation**: Assess source credibility and bias
3. **Synthesis**: Combine information from multiple sources
4. **Citation**: Provide proper citations for all claims

## Search Strategy

- Use specific, targeted search queries
- Evaluate source credibility before using information
- Cross-reference important claims
- Note limitations and uncertainties

## Output Format

Provide research findings in a structured format:
1. Summary of key findings
2. Detailed analysis with citations
3. Limitations and areas for further research
4. Recommendations based on evidence

## Context

Created: {date}
Category: Research
""",
    "development": """# {name}

You are a specialized development assistant for {purpose}.

## Development Approach

1. **Understanding**: Clarify requirements before coding
2. **Planning**: Break down complex tasks into steps
3. **Implementation**: Write clean, maintainable code
4. **Testing**: Verify functionality and edge cases
5. **Documentation**: Document code and decisions

## Code Quality Standards

- Follow language-specific best practices
- Write self-documenting code with clear names
- Add comments for complex logic
- Handle errors appropriately
- Consider performance and security

## Problem-Solving Process

1. Understand the problem
2. Identify potential solutions
3. Choose the best approach
4. Implement incrementally
5. Test and iterate

## Context

Created: {date}
Category: Development
""",
    "content-creation": """# {name}

You are a specialized content creation assistant for {purpose}.

## Content Principles

1. **Clarity**: Write clearly and concisely
2. **Engagement**: Create compelling, relevant content
3. **Accuracy**: Ensure factual correctness
4. **Voice**: Maintain consistent tone and style

## Content Structure

1. **Hook**: Grab attention with compelling opening
2. **Body**: Deliver value with clear organization
3. **Call to Action**: Guide next steps

## Writing Guidelines

- Know your audience
- Use active voice
- Be specific and concrete
- Edit ruthlessly
- Optimize for readability

## Context

Created: {date}
Category: Content Creation
""",
}


class CustomSkillEditor:
    """Create and manage custom skills.

    Provides functionality for:
    - Creating skills from templates
    - Editing existing skills
    - Managing custom patches
    """

    def __init__(self, config: Optional[Config] = None):
        """Initialize the Custom Skill Editor.

        Args:
            config: Optional configuration object
        """
        self.config = config or Config()
        self.custom_skills_dir = Path(self.config.get(
            "custom_skills.directory",
            "custom-skills"
        ))
        self.custom_patches_file = self.custom_skills_dir / "custom-patches.json"

        # Ensure directories exist
        self.custom_skills_dir.mkdir(parents=True, exist_ok=True)

        # Load custom patches
        self._custom_patches: Dict[str, Any] = {}
        self._load_custom_patches()

    def _load_custom_patches(self) -> None:
        """Load custom patches from file."""
        if self.custom_patches_file.exists():
            try:
                with open(self.custom_patches_file, "r") as f:
                    self._custom_patches = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error loading custom patches: {e}")

    def _save_custom_patches(self) -> None:
        """Save custom patches to file."""
        try:
            with open(self.custom_patches_file, "w") as f:
                json.dump(self._custom_patches, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving custom patches: {e}")

    def get_available_templates(self) -> List[str]:
        """Get list of available skill templates.

        Returns:
            List of template names
        """
        return list(SKILL_TEMPLATES.keys())

    def create_from_template(
        self,
        template_type: str,
        name: str,
        description: Optional[str] = None
    ) -> str:
        """Create a skill from a template.

        Args:
            template_type: Type of template (basic, research, development, etc.)
            name: Name for the skill
            description: Optional description/purpose

        Returns:
            Created skill content
        """
        if template_type not in SKILL_TEMPLATES:
            template_type = "basic"

        template = SKILL_TEMPLATES[template_type]

        # Generate purpose from name/description
        purpose = description or f"{name} tasks"

        # Generate capabilities
        capability_1 = f"Assist with {purpose}"
        capability_2 = "Provide expert guidance and support"
        capability_3 = "Ensure high-quality outcomes"

        # Fill template
        content = template.format(
            name=name,
            purpose=purpose,
            capability_1=capability_1,
            capability_2=capability_2,
            capability_3=capability_3,
            date=datetime.now().strftime("%Y-%m-%d")
        )

        return content

    def create_basic_skill(
        self,
        name: str,
        category: str,
        description: Optional[str] = None
    ) -> str:
        """Create a basic skill.

        Args:
            name: Skill name
            category: Skill category
            description: Optional description

        Returns:
            Created skill content
        """
        template_type = "basic"

        # Map category to template
        category_template_map = {
            "research": "research",
            "development": "development",
            "content-creation": "content-creation",
            "content creation": "content-creation",
        }

        if category.lower() in category_template_map:
            template_type = category_template_map[category.lower()]

        return self.create_from_template(template_type, name, description)

    def add_skill_to_patch(
        self,
        skill_path: str,
        patch_id: str
    ) -> bool:
        """Add a skill to a custom patch.

        Args:
            skill_path: Path to the skill in X-Skills
            patch_id: ID of the custom patch

        Returns:
            True if successful
        """
        # Validate skill exists
        from src.skill_browser import SkillBrowser

        browser = SkillBrowser()
        skill_info = browser.get_skill_info(skill_path)

        if not skill_info:
            logger.error(f"Skill not found: {skill_path}")
            return False

        # Initialize patch if not exists
        if patch_id not in self._custom_patches:
            self._custom_patches[patch_id] = {
                "name": patch_id.replace("-", " ").title(),
                "description": f"Custom patch: {patch_id}",
                "skills": [],
                "created_at": datetime.now().isoformat(),
            }

        # Add skill if not already present
        if skill_path not in self._custom_patches[patch_id]["skills"]:
            self._custom_patches[patch_id]["skills"].append(skill_path)
            self._save_custom_patches()
            logger.info(f"Added {skill_path} to patch '{patch_id}'")
            return True

        logger.info(f"Skill {skill_path} already in patch '{patch_id}'")
        return True

    def create_custom_patch(
        self,
        patch_id: str,
        name: str,
        description: str,
        skill_paths: List[str]
    ) -> bool:
        """Create a new custom patch.

        Args:
            patch_id: Unique patch identifier
            name: Display name
            description: Patch description
            skill_paths: List of skill paths to include

        Returns:
            True if successful
        """
        if patch_id in self._custom_patches:
            logger.warning(f"Patch '{patch_id}' already exists")
            return False

        self._custom_patches[patch_id] = {
            "name": name,
            "description": description,
            "skills": skill_paths,
            "created_at": datetime.now().isoformat(),
        }

        self._save_custom_patches()
        logger.info(f"Created custom patch '{patch_id}' with {len(skill_paths)} skills")
        return True

    def list_custom_patches(self) -> Dict[str, Any]:
        """List all custom patches.

        Returns:
            Dictionary of custom patches
        """
        return self._custom_patches.copy()

    def get_patch_skills(self, patch_id: str) -> Optional[List[str]]:
        """Get skills in a custom patch.

        Args:
            patch_id: Patch identifier

        Returns:
            List of skill paths or None if patch not found
        """
        if patch_id not in self._custom_patches:
            return None

        return self._custom_patches[patch_id]["skills"]

    def export_patch(
        self,
        patch_id: str,
        output_dir: Optional[Path] = None
    ) -> bool:
        """Export a custom patch for installation.

        Args:
            patch_id: Patch identifier
            output_dir: Output directory (defaults to custom-skills/patches)

        Returns:
            True if successful
        """
        if patch_id not in self._custom_patches:
            logger.error(f"Patch not found: {patch_id}")
            return False

        if output_dir is None:
            output_dir = self.custom_skills_dir / "patches"

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create patch.json
        patch_data = self._custom_patches[patch_id]
        patch_json = {
            "spec": {
                "id": patch_id,
                "name": patch_data["name"],
                "description": patch_data["description"],
                "use_case": patch_data["description"],
                "categories": ["custom"],
                "subcategories": [],
                "tags": [],
                "exclude": [],
                "min_stars": None,
                "max_skills": len(patch_data["skills"]),
                "required_skills": patch_data["skills"],
                "optional_skills": [],
                "dependencies": [],
                "version": "1.0.0",
            },
            "skills": [],
            "total_count": len(patch_data["skills"]),
            "generated_at": datetime.now().isoformat(),
        }

        # Add skill references
        from src.skill_browser import SkillBrowser
        browser = SkillBrowser()

        for skill_path in patch_data["skills"]:
            skill_info = browser.get_skill_info(skill_path)
            if skill_info:
                patch_json["skills"].append({
                    "local_path": skill_path,
                    "display_name": skill_info.get("display_name", skill_path),
                    "category": skill_info.get("category", "custom"),
                    "subcategory": "",
                    "tags": skill_info.get("tags", []),
                    "required": True,
                    "reason": "Custom selection",
                })

        # Write patch.json
        patch_file = output_dir / patch_id / "patch.json"
        patch_file.parent.mkdir(parents=True, exist_ok=True)

        with open(patch_file, "w") as f:
            json.dump(patch_json, f, indent=2)

        logger.info(f"Exported patch '{patch_id}' to {patch_file}")
        return True


__all__ = ["CustomSkillEditor"]
