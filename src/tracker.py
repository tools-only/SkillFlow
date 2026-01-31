"""Tracking module for managing processed skills using SQLite + JSON."""

import json
import logging
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import Config


logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Information about a processed skill."""

    file_hash: str
    source_repo: str
    source_path: str
    source_url: str
    skill_name: str
    category: str
    subcategory: str
    processed_at: str
    local_path: Optional[str] = None


class Tracker:
    """Track processed skills to prevent duplicates."""

    def __init__(self, config: Config):
        """Initialize tracker.

        Args:
            config: Configuration object
        """
        self.config = config
        self.data_dir = config.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # SQLite database path
        self.db_path = self.data_dir / "skills_tracker.db"

        # JSON backup path
        self.json_path = self.data_dir / "skills_tracker.json"

        # Initialize database
        self._init_database()

        # Load existing JSON data if database is empty
        self._migrate_from_json()

    def _init_database(self) -> None:
        """Initialize SQLite database with required tables."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_skills (
                    file_hash TEXT PRIMARY KEY,
                    source_repo TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    skill_name TEXT,
                    category TEXT,
                    subcategory TEXT,
                    processed_at TEXT NOT NULL,
                    local_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_repo
                ON processed_skills(source_repo)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_category
                ON processed_skills(category, subcategory)
            """)

            conn.commit()
            conn.close()

            logger.debug(f"Initialized tracker database at {self.db_path}")

        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def _migrate_from_json(self) -> None:
        """Migrate data from JSON file if database is empty."""
        # Check if database has any records
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM processed_skills")
        count = cursor.fetchone()[0]
        conn.close()

        if count > 0:
            return  # Database already has data

        # Check if JSON file exists
        if not self.json_path.exists():
            return

        try:
            with open(self.json_path, "r") as f:
                data = json.load(f)

            if not isinstance(data, list):
                return

            logger.info(f"Migrating {len(data)} records from JSON to database")

            for item in data:
                if isinstance(item, dict):
                    skill_info = SkillInfo(
                        file_hash=item.get("file_hash", ""),
                        source_repo=item.get("source_repo", ""),
                        source_path=item.get("source_path", ""),
                        source_url=item.get("source_url", ""),
                        skill_name=item.get("skill_name", ""),
                        category=item.get("category", ""),
                        subcategory=item.get("subcategory", ""),
                        processed_at=item.get("processed_at", datetime.utcnow().isoformat()),
                        local_path=item.get("local_path"),
                    )
                    self._insert_to_db(skill_info)

            # Backup the migrated JSON
            backup_path = self.json_path.with_suffix(".json.bak")
            self.json_path.rename(backup_path)
            logger.info(f"Backed up migrated JSON to {backup_path}")

        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Could not migrate from JSON: {e}")

    def _insert_to_db(self, skill_info: SkillInfo) -> None:
        """Insert skill info into database.

        Args:
            skill_info: Skill information to insert
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO processed_skills
                (file_hash, source_repo, source_path, source_url, skill_name, category, subcategory, processed_at, local_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                skill_info.file_hash,
                skill_info.source_repo,
                skill_info.source_path,
                skill_info.source_url,
                skill_info.skill_name,
                skill_info.category,
                skill_info.subcategory,
                skill_info.processed_at,
                skill_info.local_path,
            ))

            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database insert error: {e}")
        finally:
            conn.close()

    def is_already_processed(self, file_hash: str) -> bool:
        """Check if a skill has already been processed.

        Args:
            file_hash: Hash of the skill content

        Returns:
            True if already processed, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT 1 FROM processed_skills WHERE file_hash = ? LIMIT 1", (file_hash,))
            result = cursor.fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return False
        finally:
            conn.close()

    def mark_as_processed(self, skill_info: SkillInfo) -> bool:
        """Mark a skill as processed.

        Args:
            skill_info: Skill information to record

        Returns:
            True if successful, False otherwise
        """
        try:
            self._insert_to_db(skill_info)
            self._save_json_backup()
            logger.debug(f"Marked as processed: {skill_info.source_repo}/{skill_info.source_path}")
            return True
        except Exception as e:
            logger.error(f"Error marking as processed: {e}")
            return False

    def get_all_processed(self) -> List[SkillInfo]:
        """Get all processed skills.

        Returns:
            List of SkillInfo objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT file_hash, source_repo, source_path, source_url,
                       skill_name, category, subcategory, processed_at, local_path
                FROM processed_skills
                ORDER BY processed_at DESC
            """)

            results = []
            for row in cursor.fetchall():
                results.append(SkillInfo(
                    file_hash=row[0],
                    source_repo=row[1],
                    source_path=row[2],
                    source_url=row[3],
                    skill_name=row[4] or "",
                    category=row[5] or "",
                    subcategory=row[6] or "",
                    processed_at=row[7],
                    local_path=row[8],
                ))

            return results

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
        finally:
            conn.close()

    def get_processed_by_repo(self, repo_name: str) -> List[SkillInfo]:
        """Get all processed skills from a specific repository.

        Args:
            repo_name: Repository full name (e.g., "user/repo")

        Returns:
            List of SkillInfo objects from the repository
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT file_hash, source_repo, source_path, source_url,
                       skill_name, category, subcategory, processed_at, local_path
                FROM processed_skills
                WHERE source_repo = ?
                ORDER BY processed_at DESC
            """, (repo_name,))

            results = []
            for row in cursor.fetchall():
                results.append(SkillInfo(
                    file_hash=row[0],
                    source_repo=row[1],
                    source_path=row[2],
                    source_url=row[3],
                    skill_name=row[4] or "",
                    category=row[5] or "",
                    subcategory=row[6] or "",
                    processed_at=row[7],
                    local_path=row[8],
                ))

            return results

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """Get statistics about processed skills.

        Returns:
            Dictionary with statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Total count
            cursor.execute("SELECT COUNT(*) FROM processed_skills")
            total = cursor.fetchone()[0]

            # Count by category
            cursor.execute("""
                SELECT category, COUNT(*)
                FROM processed_skills
                GROUP BY category
                ORDER BY COUNT(*) DESC
            """)
            by_category = dict(cursor.fetchall())

            # Count by source repo
            cursor.execute("""
                SELECT source_repo, COUNT(*)
                FROM processed_skills
                GROUP BY source_repo
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """)
            top_repos = dict(cursor.fetchall())

            return {
                "total_skills": total,
                "by_category": by_category,
                "top_repos": top_repos,
            }

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return {}
        finally:
            conn.close()

    def _save_json_backup(self) -> None:
        """Save a JSON backup of the database."""
        try:
            skills = self.get_all_processed()
            data = [asdict(skill) for skill in skills]

            # Write to temporary file first
            temp_path = self.json_path.with_suffix(".json.tmp")
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)

            # Rename to actual path
            temp_path.replace(self.json_path)

            logger.debug(f"Saved JSON backup with {len(data)} records")

        except (IOError, json.JSONEncodeError) as e:
            logger.warning(f"Could not save JSON backup: {e}")

    def remove_skill(self, file_hash: str) -> bool:
        """Remove a skill from the tracker.

        Args:
            file_hash: Hash of the skill to remove

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM processed_skills WHERE file_hash = ?", (file_hash,))
            conn.commit()
            self._save_json_backup()

            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Removed skill with hash: {file_hash}")

            return deleted

        except sqlite3.Error as e:
            logger.error(f"Database delete error: {e}")
            return False
        finally:
            conn.close()
