"""License Checker Agent - Detects and filters skills based on their licenses.

This agent scans skill files for license information and filters out skills
with restrictive licenses that are incompatible with open-source distribution.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config import Config


logger = logging.getLogger(__name__)


class LicenseType(Enum):
    """Types of software licenses."""
    PERMISSIVE = "permissive"  # MIT, Apache, BSD, ISC, etc.
    WEAK_COPLEFT = "weak_copyleft"  # LGPL, MPL, EPL
    STRONG_COPyleft = "strong_copyleft"  # GPL, AGPL
    PROPRIETARY = "proprietary"  # Commercial, custom restrictive
    UNKNOWN = "unknown"


@dataclass
class LicenseInfo:
    """Information about a detected license."""
    license_type: LicenseType
    license_name: str
    confidence: float  # 0.0 to 1.0
    matched_text: str
    is_compatible: bool


class LicenseChecker:
    """Checks skill files for license compatibility."""

    # Common permissive licenses (allowed)
    PERMISSIVE_LICENSES = {
        "mit", "apache license", "apache-2.0", "apache 2.0", "apache-2",
        "bsd", "bsd-2-clause", "bsd-3-clause", "bsd 2-clause", "bsd 3-clause",
        "isc", "isc license",
        "unlicense", "unlicense",
        "wtfpl", "wtfpl",
        "cc0", "cc0", "creative commons zero", "public domain", "pd",
        "boost software license", "boost",
    }

    # Weak copyleft licenses (generally allowed with conditions)
    WEAK_COPLEFT_LICENSES = {
        "lgpl", "lgpl-2.1", "lgpl-2.0", "lgpl-3.0", "lesser gpl",
        "mpl", "mpl-2.0", "mozilla public license",
        "epl", "epl-1.0", "epl-2.0", "eclipse public license",
        "cddl", "cddl-1.0", "common development and distribution license",
    }

    # Strong copyleft licenses (generally restricted for open-source projects)
    STRONG_COPLEFT_LICENSES = {
        "gpl", "gnu gpl", "gpl-2.0", "gpl-3.0", "gplv2", "gplv3",
        "agpl", "gnu agpl", "agpl-3.0", "agplv3",
        "gpl-3.0-or-later", "gpl-3.0-or-later",
        "agpl-3.0-or-later", "agpl-3.0-or-later",
    }

    # Proprietary/restricted indicators
    PROPRIETARY_INDICATORS = {
        "proprietary", "confidential", "trade secret", "trade secret",
        "all rights reserved", "copyright .*all rights reserved",
        "commercial license", "restricted", "restricted rights",
        "non-commercial", "nc-", "attribution-required",
        "no redistribution", "no derivative", "non-transferable",
    }

    def __init__(self, config: Optional[Config] = None):
        """Initialize the License Checker.

        Args:
            config: Optional configuration object
        """
        self.config = config or Config()
        self.strict_mode = self.config.get("license_checker.strict_mode", True)
        self.allow_weak_copyleft = self.config.get("license_checker.allow_weak_copyleft", True)
        self.require_compatible_license = self.config.get("license_checker.require_compatible", True)

    def check_skill(self, content: str, source_path: str = "") -> Optional[LicenseInfo]:
        """Check if a skill has a compatible license.

        Args:
            content: Skill file content
            source_path: Original file path (for context)

        Returns:
            LicenseInfo if license detected, None if no license found
        """
        # Check for license in various locations
        license_info = None

        # 1. Check YAML frontmatter
        license_info = self._check_yaml_frontmatter(content)
        if license_info:
            return self._determine_compatibility(license_info)

        # 2. Check SPDX license identifier
        license_info = self._check_spdx_license(content)
        if license_info:
            return self._determine_compatibility(license_info)

        # 3. Check license header comments
        license_info = self._check_license_header(content)
        if license_info:
            return self._determine_compatibility(license_info)

        # 4. Check for common license text patterns
        license_info = self._check_license_text(content)
        if license_info:
            return self._determine_compatibility(license_info)

        # 5. Check for proprietary/restricted indicators
        license_info = self._check_proprietary_indicators(content)
        if license_info:
            return self._determine_compatibility(license_info)

        return None

    def should_filter_skill(self, content: str, source_path: str = "") -> tuple[bool, str]:
        """Determine if a skill should be filtered based on license.

        Args:
            content: Skill file content
            source_path: Original file path

        Returns:
            Tuple of (should_filter, reason)
        """
        license_info = self.check_skill(content, source_path)

        if license_info is None:
            # No license detected
            if self.require_compatible_license:
                # Strict mode: require explicit compatible license
                return True, "No compatible license found"
            else:
                # Lenient mode: allow skills without license
                return False, ""

        if not license_info.is_compatible:
            return True, f"Incompatible license: {license_info.license_name}"

        return False, ""

    def _determine_compatibility(self, license_info: LicenseInfo) -> LicenseInfo:
        """Determine if a license is compatible with open-source distribution.

        Args:
            license_info: License information

        Returns:
            Updated LicenseInfo with compatibility flag
        """
        lic_type = license_info.license_type

        if lic_type == LicenseType.PERMISSIVE:
            license_info.is_compatible = True
        elif lic_type == LicenseType.WEAK_COPLEFT:
            license_info.is_compatible = self.allow_weak_copyleft
        elif lic_type == LicenseType.STRONG_COPyleft:
            license_info.is_compatible = False
        elif lic_type == LicenseType.PROPRIETARY:
            license_info.is_compatible = False
        else:
            # Unknown license - be conservative in strict mode
            license_info.is_compatible = not self.strict_mode

        return license_info

    def _check_yaml_frontmatter(self, content: str) -> Optional[LicenseInfo]:
        """Check for license in YAML frontmatter.

        Args:
            content: File content

        Returns:
            LicenseInfo if found, None otherwise
        """
        if not content.startswith('---'):
            return None

        # Extract frontmatter
        parts = content.split('---', 2)
        if len(parts) < 3:
            return None

        frontmatter = parts[1].lower()

        # Look for license field
        license_match = re.search(r'license\s*:\s*["\']?([^"\'\n]+)["\']?', frontmatter)
        if license_match:
            license_text = license_match.group(1).strip()
            return self._classify_license(license_text, confidence=0.9)

        return None

    def _check_spdx_license(self, content: str) -> Optional[LicenseInfo]:
        """Check for SPDX license identifier.

        Args:
            content: File content

        Returns:
            LicenseInfo if found, None otherwise
        """
        # SPDX identifiers are usually at the top
        lines = content.split('\n')[:10]

        for line in lines:
            # Look for SPDX-License-Identifier header
            match = re.search(r'SPDX-License-Identifier:\s*(.+)', line, re.IGNORECASE)
            if match:
                spdx_id = match.group(1).strip()
                return self._classify_license(spdx_id, confidence=0.95)

        return None

    def _check_license_header(self, content: str) -> Optional[LicenseInfo]:
        """Check for license in comment headers.

        Args:
            content: File content

        Returns:
            LicenseInfo if found, None otherwise
        """
        # Check first 20 lines for license comments
        lines = content.split('\n')[:20]
        header_text = '\n'.join(lines)

        # Look for common license comment patterns
        patterns = [
            r'(?:Licensed under the |License:\s*)(.+?)(?:\n|,|\.)',
            r'(?:Copyright.*?\n.*?)(?:Licensed|Permission|Redistribution)',
            r'(?:MIT|Apache|BSD|GPL|LGPL) License',
        ]

        for pattern in patterns:
            match = re.search(pattern, header_text, re.IGNORECASE | re.DOTALL)
            if match:
                license_text = match.group(1).strip()
                # Clean up common trailing text
                license_text = re.sub(r'\s.*$', '', license_text)
                return self._classify_license(license_text, confidence=0.7)

        return None

    def _check_license_text(self, content: str) -> Optional[LicenseInfo]:
        """Check for full license text in content.

        Args:
            content: File content

        Returns:
            LicenseInfo if found, None otherwise
        """
        content_lower = content.lower()

        # Check for specific license mentions
        for license_name in self.PERMISSIVE_LICENSES:
            if license_name in content_lower:
                return self._classify_license(license_name, confidence=0.6)

        for license_name in self.STRONG_COPLEFT_LICENSES:
            if license_name in content_lower:
                return self._classify_license(license_name, confidence=0.6)

        return None

    def _check_proprietary_indicators(self, content: str) -> Optional[LicenseInfo]:
        """Check for proprietary/restricted license indicators.

        Args:
            content: File content

        Returns:
            LicenseInfo if found, None otherwise
        """
        content_lower = content.lower()

        for indicator in self.PROPRIETARY_INDICATORS:
            if indicator in content_lower:
                return LicenseInfo(
                    license_type=LicenseType.PROPRIETARY,
                    license_name="Proprietary/Restricted",
                    confidence=0.5,
                    matched_text=indicator,
                    is_compatible=False
                )

        return None

    def _classify_license(self, license_text: str, confidence: float) -> LicenseInfo:
        """Classify a license string into a LicenseType.

        Args:
            license_text: License string to classify
            confidence: Confidence level (0.0 to 1.0)

        Returns:
            LicenseInfo with classification
        """
        text_lower = license_text.lower().strip()

        # Remove common qualifiers
        text_lower = re.sub(r'\s+', ' ', text_lower)
        text_lower = re.sub(r'^\s*(?:license|licensed under)\s+', '', text_lower)

        # Check strong copyleft (most restrictive)
        for lic in self.STRONG_COPLEFT_LICENSES:
            if lic in text_lower:
                return LicenseInfo(
                    license_type=LicenseType.STRONG_COPyleft,
                    license_name=license_text,
                    confidence=confidence,
                    matched_text=lic,
                    is_compatible=False
                )

        # Check weak copyleft
        for lic in self.WEAK_COPLEFT_LICENSES:
            if lic in text_lower:
                return LicenseInfo(
                    license_type=LicenseType.WEAK_COPyleft,
                    license_name=license_text,
                    confidence=confidence,
                    matched_text=lic,
                    is_compatible=self.allow_weak_copyleft
                )

        # Check permissive
        for lic in self.PERMISSIVE_LICENSES:
            if lic in text_lower:
                return LicenseInfo(
                    license_type=LicenseType.PERMISSIVE,
                    license_name=license_text,
                    confidence=confidence,
                    matched_text=lic,
                    is_compatible=True
                )

        # Unknown license
        return LicenseInfo(
            license_type=LicenseType.UNKNOWN,
            license_name=license_text,
            confidence=confidence,
            matched_text=text_lower,
            is_compatible=not self.strict_mode
        )


def check_licenses_for_skills(
    skills: List[tuple[str, str]],  # List of (content, source_path) tuples
    config: Optional[Config] = None
) -> Dict[str, LicenseInfo]:
    """Check licenses for multiple skills.

    Args:
        skills: List of (content, source_path) tuples
        config: Optional configuration

    Returns:
        Dict mapping source_path to LicenseInfo
    """
    checker = LicenseChecker(config)
    results = {}

    for content, source_path in skills:
        license_info = checker.check_skill(content, source_path)
        if license_info:
            results[source_path] = license_info

    return results


# Convenience function for filtering
def filter_incompatible_skills(
    skills: List[tuple[str, str]],
    config: Optional[Config] = None
) -> tuple[List[str], Dict[str, str]]:
    """Filter out skills with incompatible licenses.

    Args:
        skills: List of (content, source_path) tuples
        config: Optional configuration

    Returns:
        Tuple of (filtered_paths, rejection_reasons dict)
    """
    checker = LicenseChecker(config)
    filtered = []
    reasons = {}

    for content, source_path in skills:
        should_filter, reason = checker.should_filter_skill(content, source_path)
        if should_filter:
            filtered.append(source_path)
            reasons[source_path] = reason

    return filtered, reasons


if __name__ == "__main__":
    import sys

    # Test the license checker
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        with open(test_file, 'r') as f:
            content = f.read()

        checker = LicenseChecker()
        should_filter, reason = checker.should_filter_skill(content, test_file)

        print(f"File: {test_file}")
        print(f"Should filter: {should_filter}")
        if reason:
            print(f"Reason: {reason}")
    else:
        print("Usage: python -m src.license_checker <skill_file.md>")
