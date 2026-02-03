"""
X-Skills Plugin for Claude Code

A plugin system that allows interactive selection and management of skills
from the X-Skills repository.
"""

__version__ = "1.0.0"

from .skill_indexer import SkillIndex, SkillMetadata
from .skill_loader import SkillLoader
from .skill_manager import SkillManager
from .config_manager import ConfigManager
from .linker import Linker

__all__ = [
    "SkillIndex",
    "SkillMetadata",
    "SkillLoader",
    "SkillManager",
    "ConfigManager",
    "Linker",
]
