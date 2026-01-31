"""Configuration loader for SkillFlow."""

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml
from dotenv import load_dotenv


class Config:
    """Configuration manager for SkillFlow."""

    def __init__(self, config_path: str = "config/config.yaml", search_terms_path: str = "config/search_terms.yaml"):
        """Initialize configuration.

        Args:
            config_path: Path to main configuration file
            search_terms_path: Path to search terms configuration file
        """
        load_dotenv()
        self.config_path = Path(config_path)
        self.search_terms_path = Path(search_terms_path)
        self._config: Dict[str, Any] = {}
        self._search_terms: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML files."""
        with open(self.config_path, "r") as f:
            self._config = yaml.safe_load(f)

        with open(self.search_terms_path, "r") as f:
            self._search_terms = yaml.safe_load(f)

    def _substitute_env_vars(self, value: str) -> str:
        """Substitute environment variables in configuration values.

        Args:
            value: String that may contain ${VAR} patterns

        Returns:
            String with environment variables substituted
        """
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            return os.environ.get(var_name, "")
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-separated key.

        Args:
            key: Dot-separated configuration key (e.g., 'github.max_results')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        # Substitute environment variables for string values
        if isinstance(value, str):
            value = self._substitute_env_vars(value)

        return value

    @property
    def github_token(self) -> str:
        """Get GitHub token from environment."""
        return os.environ.get("GITHUB_TOKEN", "")

    @property
    def zhipu_api_key(self) -> str:
        """Get Zhipu AI API key from environment."""
        return os.environ.get("ZHIPU_API_KEY", "")

    @property
    def github_max_results(self) -> int:
        """Get maximum GitHub search results."""
        return self.get("github.max_results", 20)

    @property
    def github_min_stars(self) -> int:
        """Get minimum star count for repositories."""
        return self.get("github.min_stars", 5)

    @property
    def skills_dir(self) -> Path:
        """Get skills directory path."""
        return Path(self.get("paths.skills_dir", "skills"))

    @property
    def data_dir(self) -> Path:
        """Get data directory path."""
        return Path(self.get("paths.data_dir", "data"))

    @property
    def log_dir(self) -> Path:
        """Get log directory path."""
        return Path(self.get("paths.log_dir", "logs"))

    @property
    def search_terms(self) -> List[str]:
        """Get search terms list."""
        return self._search_terms.get("terms", [])

    @property
    def excluded_repos(self) -> List[str]:
        """Get excluded repositories list."""
        return self._search_terms.get("excluded_repos", [])

    @property
    def required_file_patterns(self) -> List[str]:
        """Get required file patterns for skills."""
        return self._search_terms.get("required_file_patterns", ["**/*.md"])

    @property
    def search_languages(self) -> List[str]:
        """Get search languages filter."""
        return self.get("search.languages", ["python", "javascript", "typescript"])

    @property
    def search_sort_by(self) -> str:
        """Get search sort criteria."""
        return self.get("search.sort_by", "updated")

    @property
    def search_order(self) -> str:
        """Get search order."""
        return self.get("search.order", "desc")
