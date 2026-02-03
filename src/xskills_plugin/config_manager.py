"""
Configuration Manager for X-Skills Plugin

Manages YAML configuration files for skill selection and settings.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml


@dataclass
class XSkillsConfig:
    """Configuration data structure for X-Skills plugin."""

    version: str = "1.0"
    xskills_path: str = "./skillflow_repos/X-Skills"
    link_target: str = ".claude/skills/xskills"
    enabled: "EnabledConfig" = field(default_factory=lambda: EnabledConfig())
    settings: "SettingsConfig" = field(default_factory=lambda: SettingsConfig())


@dataclass
class EnabledConfig:
    """Configuration for which skills are enabled."""

    by_name: List[str] = field(default_factory=list)
    by_category: Dict[str, Optional[Dict[str, Any]]] = field(default_factory=dict)
    by_tag: List[str] = field(default_factory=list)

    def get_excluded_skills(self, category: str) -> List[str]:
        """Get excluded skills for a category."""
        cat_config = self.by_category.get(category)
        if cat_config and isinstance(cat_config, dict):
            return cat_config.get("exclude", [])
        return []


@dataclass
class SettingsConfig:
    """Global settings for the plugin."""

    auto_update: bool = True
    link_strategy: str = "symlink"  # symlink | copy


class ConfigManager:
    """
    Manages reading and writing X-Skills configuration files.

    Configuration is stored in YAML format with support for:
    - Individual skill selection by name
    - Category-based selection with exclusions
    - Tag-based selection
    """

    DEFAULT_CONFIG_PATH = "config/xskills_config.yaml"

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the configuration manager.

        Args:
            config_path: Path to the configuration file.
                        If None, uses default path.
        """
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / self.DEFAULT_CONFIG_PATH

        self.config_path = Path(config_path)
        self.config: Optional[XSkillsConfig] = None
        self._loaded = False

    def load(self) -> XSkillsConfig:
        """
        Load configuration from file.

        Returns:
            The loaded configuration object.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            yaml.YAMLError: If config file is invalid YAML.
        """
        if not self.config_path.exists():
            # Return default config if file doesn't exist
            self.config = XSkillsConfig()
            self._loaded = True
            return self.config

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self.config = self._dict_to_config(data)
        self._loaded = True
        return self.config

    def save(self, config: Optional[XSkillsConfig] = None) -> None:
        """
        Save configuration to file.

        Args:
            config: Configuration to save. If None, saves current config.
        """
        if config:
            self.config = config

        if not self.config:
            self.config = XSkillsConfig()

        # Ensure parent directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self._config_to_dict(self.config), f, default_flow_style=False)

    def get_enabled_skills(
        self,
        available_skills: List[str],
        categories: Dict[str, List[str]],
        tags: Dict[str, List[str]],
    ) -> Set[str]:
        """
        Get the set of enabled skill names based on current configuration.

        Args:
            available_skills: All available skill names
            categories: Mapping of category to skill names
            tags: Mapping of tag to skill names

        Returns:
            Set of enabled skill names
        """
        if not self._loaded:
            self.load()

        if not self.config:
            return set()

        enabled: Set[str] = set()
        available_set = set(available_skills)

        # Enable by name
        for name in self.config.enabled.by_name:
            if name in available_set:
                enabled.add(name)

        # Enable by category
        for category, config in self.config.enabled.by_category.items():
            if category in categories:
                category_skills = set(categories[category])
                excluded: Set[str] = set()

                if config and isinstance(config, dict):
                    excluded = set(config.get("exclude", []))

                enabled.update(category_skills - excluded)

        # Enable by tag
        for tag in self.config.enabled.by_tag:
            if tag in tags:
                enabled.update(tags[tag])

        return enabled

    def add_skill_by_name(self, name: str) -> None:
        """Add a skill to the enabled list by name."""
        if not self._loaded:
            self.load()

        if name not in self.config.enabled.by_name:
            self.config.enabled.by_name.append(name)

    def remove_skill_by_name(self, name: str) -> None:
        """Remove a skill from the enabled list by name."""
        if not self._loaded:
            self.load()

        if name in self.config.enabled.by_name:
            self.config.enabled.by_name.remove(name)

    def add_category(self, category: str, exclude: Optional[List[str]] = None) -> None:
        """
        Enable a category.

        Args:
            category: Category name to enable
            exclude: Optional list of skill names to exclude
        """
        if not self._loaded:
            self.load()

        if exclude:
            self.config.enabled.by_category[category] = {"exclude": exclude}
        else:
            self.config.enabled.by_category[category] = None

    def remove_category(self, category: str) -> None:
        """Disable a category."""
        if not self._loaded:
            self.load()

        self.config.enabled.by_category.pop(category, None)

    def add_tag(self, tag: str) -> None:
        """Add a tag to the enabled list."""
        if not self._loaded:
            self.load()

        if tag not in self.config.enabled.by_tag:
            self.config.enabled.by_tag.append(tag)

    def remove_tag(self, tag: str) -> None:
        """Remove a tag from the enabled list."""
        if not self._loaded:
            self.load()

        if tag in self.config.enabled.by_tag:
            self.config.enabled.by_tag.remove(tag)

    def clear_all(self) -> None:
        """Clear all enabled skills."""
        if not self._loaded:
            self.load()

        self.config.enabled.by_name.clear()
        self.config.enabled.by_category.clear()
        self.config.enabled.by_tag.clear()

    @staticmethod
    def _dict_to_config(data: Dict[str, Any]) -> XSkillsConfig:
        """Convert dict to XSkillsConfig object."""
        config = XSkillsConfig()

        config.version = data.get("version", "1.0")
        config.xskills_path = data.get("xskills_path", "./skillflow_repos/X-Skills")
        config.link_target = data.get("link_target", ".claude/skills/xskills")

        enabled_data = data.get("enabled", {})
        config.enabled.by_name = enabled_data.get("by_name", [])

        for cat, cat_config in enabled_data.get("by_category", {}).items():
            config.enabled.by_category[cat] = cat_config

        config.enabled.by_tag = enabled_data.get("by_tag", [])

        settings_data = data.get("settings", {})
        config.settings.auto_update = settings_data.get("auto_update", True)
        config.settings.link_strategy = settings_data.get("link_strategy", "symlink")

        return config

    @staticmethod
    def _config_to_dict(config: XSkillsConfig) -> Dict[str, Any]:
        """Convert XSkillsConfig object to dict."""
        return {
            "version": config.version,
            "xskills_path": config.xskills_path,
            "link_target": config.link_target,
            "enabled": {
                "by_name": config.enabled.by_name,
                "by_category": config.enabled.by_category,
                "by_tag": config.enabled.by_tag,
            },
            "settings": {
                "auto_update": config.settings.auto_update,
                "link_strategy": config.settings.link_strategy,
            },
        }

    @staticmethod
    def create_default_config(path: Path) -> None:
        """
        Create a default configuration file at the specified path.

        Args:
            path: Where to create the config file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        default_config = """# X-Skills Configuration
version: "1.0"

# Path to the X-Skills repository
xskills_path: "./skillflow_repos/X-Skills"

# Target directory for skill symlinks
link_target: ".claude/skills/xskills"

# Enabled skills configuration
enabled:
  # Enable specific skills by name
  by_name:
    - tui-reference

  # Enable all skills in a category (optional: exclude specific skills)
  by_category:
    development:
      exclude: []
    automation: ~  # ~ means enable all, no exclusions

  # Enable skills by tag
  by_tag:
    - api
    - testing

# Global settings
settings:
  auto_update: true
  link_strategy: "symlink"  # symlink | copy
"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(default_config)


def get_default_config_manager() -> ConfigManager:
    """
    Get the default configuration manager instance.

    Returns:
        A ConfigManager instance with the default config path.
    """
    return ConfigManager()
