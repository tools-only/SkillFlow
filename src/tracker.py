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
    source_created_at: Optional[str] = None
    source_updated_at: Optional[str] = None
    repo_stars: Optional[int] = None
    repo_forks: Optional[int] = None
    repo_last_synced: Optional[str] = None
    repo_description: Optional[str] = None
    health_status: Optional[str] = None
    last_health_check: Optional[str] = None


@dataclass
class IssueInfo:
    """Information about a GitHub Issue."""

    issue_number: int
    issue_title: str
    issue_body: Optional[str]
    issue_state: str
    issue_author: str
    created_at: str
    updated_at: str
    processed_at: Optional[str] = None
    processing_status: str = "pending"
    labels: Optional[str] = None
    analysis_result: Optional[str] = None
    filter_reason: Optional[str] = None
    update_plan: Optional[str] = None
    error_message: Optional[str] = None
    local_created_at: Optional[str] = None


@dataclass
class UpdatePlanInfo:
    """Information about an update plan."""

    plan_id: int
    plan_type: str
    source_issue: int
    plan_data: str
    execution_status: str = "pending"
    created_at: Optional[str] = None
    executed_at: Optional[str] = None
    execution_result: Optional[str] = None


@dataclass
class PRInfo:
    """Information about a Pull Request."""

    pr_number: int
    pr_title: str
    pr_author: str
    pr_state: str
    head_ref: str
    base_ref: str
    created_at: str
    updated_at: str
    processed_at: Optional[str] = None
    processing_status: str = "pending"
    validation_results: Optional[str] = None
    skill_files_added: Optional[str] = None
    error_message: Optional[str] = None
    local_created_at: Optional[str] = None


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    check_id: int
    check_type: str
    skill_id: str
    check_result: str
    check_details: Optional[str] = None
    checked_at: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class WebhookEvent:
    """Information about a webhook event."""

    event_id: int
    event_type: str
    repo_name: str
    event_payload: Optional[str] = None
    received_at: Optional[str] = None
    processed_at: Optional[str] = None
    processing_status: str = "pending"
    retry_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[str] = None


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

        # Database version tracking
        self.db_version_path = self.data_dir / ".db_version"

        # Initialize database
        self._init_database()

        # Run migrations if needed
        self._run_migrations()

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
                    source_created_at TEXT,
                    source_updated_at TEXT,
                    repo_stars INTEGER,
                    repo_forks INTEGER,
                    repo_last_synced TEXT,
                    repo_description TEXT,
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

            # Create index for source_path lookups (for updates)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_path
                ON processed_skills(source_path)
            """)

            conn.commit()
            conn.close()

            logger.debug(f"Initialized tracker database at {self.db_path}")

        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def _get_db_version(self) -> int:
        """Get the current database version.

        Returns:
            Current database version (0 if not tracked)
        """
        if self.db_version_path.exists():
            try:
                return int(self.db_version_path.read_text().strip())
            except (IOError, ValueError):
                pass
        return 0

    def _set_db_version(self, version: int) -> None:
        """Set the database version.

        Args:
            version: Version number to write
        """
        self.db_version_path.write_text(str(version))

    def _run_migrations(self) -> None:
        """Run database migrations if needed."""
        current_version = self._get_db_version()
        target_version = 4  # Current schema version

        if current_version >= target_version:
            return

        logger.info(f"Migrating database from version {current_version} to {target_version}")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Migration 1: Add source_created_at and source_updated_at columns
            if current_version < 1:
                try:
                    cursor.execute("""
                        ALTER TABLE processed_skills
                        ADD COLUMN source_created_at TEXT
                    """)
                    cursor.execute("""
                        ALTER TABLE processed_skills
                        ADD COLUMN source_updated_at TEXT
                    """)
                    logger.info("Added source_created_at and source_updated_at columns")
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise

            # Migration 2: Add index for source_path
            if current_version < 2:
                try:
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_source_path
                        ON processed_skills(source_path)
                    """)
                    logger.info("Added index for source_path")
                except sqlite3.OperationalError:
                    pass

            # Migration 3: Add repo metadata columns
            if current_version < 3:
                try:
                    cursor.execute("""
                        ALTER TABLE processed_skills
                        ADD COLUMN repo_stars INTEGER
                    """)
                    cursor.execute("""
                        ALTER TABLE processed_skills
                        ADD COLUMN repo_forks INTEGER
                    """)
                    cursor.execute("""
                        ALTER TABLE processed_skills
                        ADD COLUMN repo_last_synced TEXT
                    """)
                    cursor.execute("""
                        ALTER TABLE processed_skills
                        ADD COLUMN repo_description TEXT
                    """)
                    logger.info("Added repo_stars, repo_forks, repo_last_synced, repo_description columns")
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise

            # Migration 4: Add Issues, PRs, Health Checks, and Webhooks tables
            if current_version < 4:
                try:
                    # Create issues table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS issues (
                            issue_number INTEGER PRIMARY KEY,
                            issue_title TEXT NOT NULL,
                            issue_body TEXT,
                            issue_state TEXT NOT NULL,
                            issue_author TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            processed_at TEXT,
                            processing_status TEXT DEFAULT 'pending',
                            labels TEXT,
                            analysis_result TEXT,
                            filter_reason TEXT,
                            update_plan TEXT,
                            error_message TEXT,
                            local_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Create update_plans table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS update_plans (
                            plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            plan_type TEXT NOT NULL,
                            source_issue INTEGER,
                            plan_data TEXT NOT NULL,
                            execution_status TEXT DEFAULT 'pending',
                            created_at TEXT NOT NULL,
                            executed_at TEXT,
                            execution_result TEXT,
                            FOREIGN KEY (source_issue) REFERENCES issues(issue_number)
                        )
                    """)

                    # Create pull_requests table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS pull_requests (
                            pr_number INTEGER PRIMARY KEY,
                            pr_title TEXT NOT NULL,
                            pr_author TEXT,
                            pr_state TEXT NOT NULL,
                            head_ref TEXT,
                            base_ref TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            processed_at TEXT,
                            processing_status TEXT DEFAULT 'pending',
                            validation_results TEXT,
                            skill_files_added TEXT,
                            error_message TEXT,
                            local_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Create health_checks table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS health_checks (
                            check_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            check_type TEXT NOT NULL,
                            skill_id TEXT NOT NULL,
                            check_result TEXT NOT NULL,
                            check_details TEXT,
                            checked_at TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Create webhook_events table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS webhook_events (
                            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            event_type TEXT NOT NULL,
                            repo_name TEXT NOT NULL,
                            event_payload TEXT,
                            received_at TEXT NOT NULL,
                            processed_at TEXT,
                            processing_status TEXT DEFAULT 'pending',
                            retry_count INTEGER DEFAULT 0,
                            error_message TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Add health status columns to processed_skills
                    cursor.execute("""
                        ALTER TABLE processed_skills
                        ADD COLUMN health_status TEXT DEFAULT 'unknown'
                    """)
                    cursor.execute("""
                        ALTER TABLE processed_skills
                        ADD COLUMN last_health_check TEXT
                    """)

                    # Create indexes for new tables
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_issues_status
                        ON issues(processing_status)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_plans_status
                        ON update_plans(execution_status)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_prs_status
                        ON pull_requests(processing_status)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_health_checks_skill
                        ON health_checks(skill_id)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_webhook_events_status
                        ON webhook_events(processing_status)
                    """)

                    logger.info("Added issues, update_plans, pull_requests, health_checks, webhook_events tables")
                    logger.info("Added health_status and last_health_check columns to processed_skills")
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise

            conn.commit()
            conn.close()

            # Update version
            self._set_db_version(target_version)
            logger.info(f"Database migration complete (version {target_version})")

        except sqlite3.Error as e:
            logger.error(f"Database migration error: {e}")
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
                (file_hash, source_repo, source_path, source_url, skill_name, category, subcategory, processed_at, local_path, source_created_at, source_updated_at, repo_stars, repo_forks, repo_last_synced, repo_description, health_status, last_health_check)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                skill_info.source_created_at,
                skill_info.source_updated_at,
                skill_info.repo_stars,
                skill_info.repo_forks,
                skill_info.repo_last_synced,
                skill_info.repo_description,
                skill_info.health_status,
                skill_info.last_health_check,
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
                       skill_name, category, subcategory, processed_at, local_path,
                       source_created_at, source_updated_at, repo_stars, repo_forks,
                       repo_last_synced, repo_description, health_status, last_health_check
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
                    source_created_at=row[9],
                    source_updated_at=row[10],
                    repo_stars=row[11],
                    repo_forks=row[12],
                    repo_last_synced=row[13],
                    repo_description=row[14],
                    health_status=row[15],
                    last_health_check=row[16],
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
                       skill_name, category, subcategory, processed_at, local_path,
                       source_created_at, source_updated_at, repo_stars, repo_forks,
                       repo_last_synced, repo_description, health_status, last_health_check
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
                    source_created_at=row[9],
                    source_updated_at=row[10],
                    repo_stars=row[11],
                    repo_forks=row[12],
                    repo_last_synced=row[13],
                    repo_description=row[14],
                    health_status=row[15],
                    last_health_check=row[16],
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

        except (IOError, TypeError, OSError) as e:
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

    def get_skill_by_source_path(self, source_path: str) -> Optional[SkillInfo]:
        """Get a skill by its source path (for update detection).

        Args:
            source_path: The source file path in the original repository

        Returns:
            SkillInfo if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT file_hash, source_repo, source_path, source_url,
                       skill_name, category, subcategory, processed_at, local_path,
                       source_created_at, source_updated_at, repo_stars, repo_forks,
                       repo_last_synced, repo_description, health_status, last_health_check
                FROM processed_skills
                WHERE source_path = ?
                LIMIT 1
            """, (source_path,))

            row = cursor.fetchone()
            if row:
                return SkillInfo(
                    file_hash=row[0],
                    source_repo=row[1],
                    source_path=row[2],
                    source_url=row[3],
                    skill_name=row[4] or "",
                    category=row[5] or "",
                    subcategory=row[6] or "",
                    processed_at=row[7],
                    local_path=row[8],
                    source_created_at=row[9],
                    source_updated_at=row[10],
                    repo_stars=row[11],
                    repo_forks=row[12],
                    repo_last_synced=row[13],
                    repo_description=row[14],
                    health_status=row[15],
                    last_health_check=row[16],
                )
            return None

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return None
        finally:
            conn.close()

    def update_skill_hash(self, source_path: str, new_file_hash: str, new_content_data: dict) -> bool:
        """Update a skill when its content has changed.

        This is used when a source file is updated - we track it by source_path
        and update the hash and related metadata.

        Args:
            source_path: The source file path
            new_file_hash: New content hash
            new_content_data: New metadata dictionary

        Returns:
            True if updated, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE processed_skills
                SET file_hash = ?,
                    skill_name = ?,
                    processed_at = ?,
                    source_created_at = ?,
                    source_updated_at = ?,
                    repo_stars = ?,
                    repo_forks = ?,
                    repo_last_synced = ?,
                    repo_description = ?,
                    health_status = ?,
                    last_health_check = ?
                WHERE source_path = ?
            """, (
                new_file_hash,
                new_content_data.get('skill_name'),
                new_content_data.get('processed_at', datetime.utcnow().isoformat()),
                new_content_data.get('source_created_at'),
                new_content_data.get('source_updated_at'),
                new_content_data.get('repo_stars'),
                new_content_data.get('repo_forks'),
                new_content_data.get('repo_last_synced', datetime.utcnow().isoformat()),
                new_content_data.get('repo_description'),
                new_content_data.get('health_status', 'unknown'),
                new_content_data.get('last_health_check'),
                source_path,
            ))

            conn.commit()
            self._save_json_backup()

            updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Updated skill hash for {source_path}: {new_file_hash}")

            return updated

        except sqlite3.Error as e:
            logger.error(f"Database update error: {e}")
            return False
        finally:
            conn.close()

    # ========== Issue Tracking Methods ==========

    def add_issue(self, issue_info: IssueInfo) -> bool:
        """Add or update an issue in the database.

        Args:
            issue_info: Issue information to add/update

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO issues
                (issue_number, issue_title, issue_body, issue_state, issue_author,
                 created_at, updated_at, processed_at, processing_status, labels,
                 analysis_result, filter_reason, update_plan, error_message, local_created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                issue_info.issue_number,
                issue_info.issue_title,
                issue_info.issue_body,
                issue_info.issue_state,
                issue_info.issue_author,
                issue_info.created_at,
                issue_info.updated_at,
                issue_info.processed_at,
                issue_info.processing_status,
                issue_info.labels,
                issue_info.analysis_result,
                issue_info.filter_reason,
                issue_info.update_plan,
                issue_info.error_message,
                issue_info.local_created_at or datetime.utcnow().isoformat(),
            ))

            conn.commit()
            logger.debug(f"Added/updated issue #{issue_info.issue_number}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Database insert error for issue: {e}")
            return False
        finally:
            conn.close()

    def get_issue(self, issue_number: int) -> Optional[IssueInfo]:
        """Get an issue by its number.

        Args:
            issue_number: GitHub issue number

        Returns:
            IssueInfo if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT issue_number, issue_title, issue_body, issue_state, issue_author,
                       created_at, updated_at, processed_at, processing_status, labels,
                       analysis_result, filter_reason, update_plan, error_message, local_created_at
                FROM issues WHERE issue_number = ?
            """, (issue_number,))

            row = cursor.fetchone()
            if row:
                return IssueInfo(
                    issue_number=row[0],
                    issue_title=row[1],
                    issue_body=row[2],
                    issue_state=row[3],
                    issue_author=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                    processed_at=row[7],
                    processing_status=row[8],
                    labels=row[9],
                    analysis_result=row[10],
                    filter_reason=row[11],
                    update_plan=row[12],
                    error_message=row[13],
                    local_created_at=row[14],
                )
            return None

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return None
        finally:
            conn.close()

    def get_pending_issues(self, status: str = "pending") -> List[IssueInfo]:
        """Get issues with a specific status.

        Args:
            status: Processing status to filter by (default: pending)

        Returns:
            List of IssueInfo objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT issue_number, issue_title, issue_body, issue_state, issue_author,
                       created_at, updated_at, processed_at, processing_status, labels,
                       analysis_result, filter_reason, update_plan, error_message, local_created_at
                FROM issues WHERE processing_status = ?
                ORDER BY created_at ASC
            """, (status,))

            results = []
            for row in cursor.fetchall():
                results.append(IssueInfo(
                    issue_number=row[0],
                    issue_title=row[1],
                    issue_body=row[2],
                    issue_state=row[3],
                    issue_author=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                    processed_at=row[7],
                    processing_status=row[8],
                    labels=row[9],
                    analysis_result=row[10],
                    filter_reason=row[11],
                    update_plan=row[12],
                    error_message=row[13],
                    local_created_at=row[14],
                ))

            return results

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
        finally:
            conn.close()

    def update_issue_status(self, issue_number: int, status: str, **kwargs) -> bool:
        """Update issue processing status.

        Args:
            issue_number: GitHub issue number
            status: New processing status
            **kwargs: Additional fields to update (processed_at, analysis_result, etc.)

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            update_fields = ["processing_status = ?"]
            values = [status]

            if 'processed_at' in kwargs:
                update_fields.append("processed_at = ?")
                values.append(kwargs['processed_at'])
            if 'analysis_result' in kwargs:
                update_fields.append("analysis_result = ?")
                values.append(kwargs['analysis_result'])
            if 'filter_reason' in kwargs:
                update_fields.append("filter_reason = ?")
                values.append(kwargs['filter_reason'])
            if 'update_plan' in kwargs:
                update_fields.append("update_plan = ?")
                values.append(kwargs['update_plan'])
            if 'error_message' in kwargs:
                update_fields.append("error_message = ?")
                values.append(kwargs['error_message'])

            values.append(issue_number)

            cursor.execute(f"""
                UPDATE issues SET {', '.join(update_fields)}
                WHERE issue_number = ?
            """, values)

            conn.commit()
            logger.debug(f"Updated issue #{issue_number} status to {status}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Database update error: {e}")
            return False
        finally:
            conn.close()

    # ========== Update Plan Methods ==========

    def add_update_plan(self, plan_info: UpdatePlanInfo) -> int:
        """Add an update plan to the database.

        Args:
            plan_info: Update plan information

        Returns:
            Plan ID if successful, -1 otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO update_plans
                (plan_type, source_issue, plan_data, execution_status, created_at, executed_at, execution_result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                plan_info.plan_type,
                plan_info.source_issue,
                plan_info.plan_data,
                plan_info.execution_status,
                plan_info.created_at or datetime.utcnow().isoformat(),
                plan_info.executed_at,
                plan_info.execution_result,
            ))

            conn.commit()
            plan_id = cursor.lastrowid
            logger.debug(f"Added update plan #{plan_id}")
            return plan_id

        except sqlite3.Error as e:
            logger.error(f"Database insert error for plan: {e}")
            return -1
        finally:
            conn.close()

    def get_pending_plans(self) -> List[UpdatePlanInfo]:
        """Get all pending update plans.

        Returns:
            List of UpdatePlanInfo objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT plan_id, plan_type, source_issue, plan_data, execution_status, created_at, executed_at, execution_result
                FROM update_plans WHERE execution_status = 'pending'
                ORDER BY created_at ASC
            """)

            results = []
            for row in cursor.fetchall():
                results.append(UpdatePlanInfo(
                    plan_id=row[0],
                    plan_type=row[1],
                    source_issue=row[2],
                    plan_data=row[3],
                    execution_status=row[4],
                    created_at=row[5],
                    executed_at=row[6],
                    execution_result=row[7],
                ))

            return results

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
        finally:
            conn.close()

    def update_plan_status(self, plan_id: int, status: str, execution_result: str = None) -> bool:
        """Update plan execution status.

        Args:
            plan_id: Plan ID
            status: New execution status
            execution_result: Optional execution result JSON

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            if execution_result:
                cursor.execute("""
                    UPDATE update_plans
                    SET execution_status = ?, executed_at = ?, execution_result = ?
                    WHERE plan_id = ?
                """, (status, datetime.utcnow().isoformat(), execution_result, plan_id))
            else:
                cursor.execute("""
                    UPDATE update_plans
                    SET execution_status = ?, executed_at = ?
                    WHERE plan_id = ?
                """, (status, datetime.utcnow().isoformat(), plan_id))

            conn.commit()
            logger.debug(f"Updated plan #{plan_id} status to {status}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Database update error: {e}")
            return False
        finally:
            conn.close()

    # ========== PR Tracking Methods ==========

    def add_pr(self, pr_info: PRInfo) -> bool:
        """Add or update a PR in the database.

        Args:
            pr_info: PR information to add/update

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO pull_requests
                (pr_number, pr_title, pr_author, pr_state, head_ref, base_ref,
                 created_at, updated_at, processed_at, processing_status,
                 validation_results, skill_files_added, error_message, local_created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pr_info.pr_number,
                pr_info.pr_title,
                pr_info.pr_author,
                pr_info.pr_state,
                pr_info.head_ref,
                pr_info.base_ref,
                pr_info.created_at,
                pr_info.updated_at,
                pr_info.processed_at,
                pr_info.processing_status,
                pr_info.validation_results,
                pr_info.skill_files_added,
                pr_info.error_message,
                pr_info.local_created_at or datetime.utcnow().isoformat(),
            ))

            conn.commit()
            logger.debug(f"Added/updated PR #{pr_info.pr_number}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Database insert error for PR: {e}")
            return False
        finally:
            conn.close()

    def get_pr(self, pr_number: int) -> Optional[PRInfo]:
        """Get a PR by its number.

        Args:
            pr_number: GitHub PR number

        Returns:
            PRInfo if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT pr_number, pr_title, pr_author, pr_state, head_ref, base_ref,
                       created_at, updated_at, processed_at, processing_status,
                       validation_results, skill_files_added, error_message, local_created_at
                FROM pull_requests WHERE pr_number = ?
            """, (pr_number,))

            row = cursor.fetchone()
            if row:
                return PRInfo(
                    pr_number=row[0],
                    pr_title=row[1],
                    pr_author=row[2],
                    pr_state=row[3],
                    head_ref=row[4],
                    base_ref=row[5],
                    created_at=row[6],
                    updated_at=row[7],
                    processed_at=row[8],
                    processing_status=row[9],
                    validation_results=row[10],
                    skill_files_added=row[11],
                    error_message=row[12],
                    local_created_at=row[13],
                )
            return None

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return None
        finally:
            conn.close()

    def get_pending_prs(self, status: str = "pending") -> List[PRInfo]:
        """Get PRs with a specific status.

        Args:
            status: Processing status to filter by (default: pending)

        Returns:
            List of PRInfo objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT pr_number, pr_title, pr_author, pr_state, head_ref, base_ref,
                       created_at, updated_at, processed_at, processing_status,
                       validation_results, skill_files_added, error_message, local_created_at
                FROM pull_requests WHERE processing_status = ?
                ORDER BY created_at ASC
            """, (status,))

            results = []
            for row in cursor.fetchall():
                results.append(PRInfo(
                    pr_number=row[0],
                    pr_title=row[1],
                    pr_author=row[2],
                    pr_state=row[3],
                    head_ref=row[4],
                    base_ref=row[5],
                    created_at=row[6],
                    updated_at=row[7],
                    processed_at=row[8],
                    processing_status=row[9],
                    validation_results=row[10],
                    skill_files_added=row[11],
                    error_message=row[12],
                    local_created_at=row[13],
                ))

            return results

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
        finally:
            conn.close()

    def update_pr_status(self, pr_number: int, status: str, **kwargs) -> bool:
        """Update PR processing status.

        Args:
            pr_number: GitHub PR number
            status: New processing status
            **kwargs: Additional fields to update

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            update_fields = ["processing_status = ?"]
            values = [status]

            if 'processed_at' in kwargs:
                update_fields.append("processed_at = ?")
                values.append(kwargs['processed_at'])
            if 'validation_results' in kwargs:
                update_fields.append("validation_results = ?")
                values.append(kwargs['validation_results'])
            if 'skill_files_added' in kwargs:
                update_fields.append("skill_files_added = ?")
                values.append(kwargs['skill_files_added'])
            if 'error_message' in kwargs:
                update_fields.append("error_message = ?")
                values.append(kwargs['error_message'])

            values.append(pr_number)

            cursor.execute(f"""
                UPDATE pull_requests SET {', '.join(update_fields)}
                WHERE pr_number = ?
            """, values)

            conn.commit()
            logger.debug(f"Updated PR #{pr_number} status to {status}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Database update error: {e}")
            return False
        finally:
            conn.close()

    # ========== Health Check Methods ==========

    def add_health_check(self, skill_id: str, check_type: str, check_result: str,
                         check_details: str = None) -> int:
        """Add a health check result.

        Args:
            skill_id: File hash or local path of the skill
            check_type: Type of check (link, format, staleness, syntax)
            check_result: Result of the check (passed, failed, warning)
            check_details: Optional JSON details

        Returns:
            Check ID if successful, -1 otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            checked_at = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT INTO health_checks
                (check_type, skill_id, check_result, check_details, checked_at)
                VALUES (?, ?, ?, ?, ?)
            """, (check_type, skill_id, check_result, check_details, checked_at))

            conn.commit()
            check_id = cursor.lastrowid

            # Update skill health status
            self.update_skill_health(skill_id, check_result, checked_at)

            logger.debug(f"Added health check #{check_id} for skill {skill_id}")
            return check_id

        except sqlite3.Error as e:
            logger.error(f"Database insert error for health check: {e}")
            return -1
        finally:
            conn.close()

    def get_latest_health_check(self, skill_id: str, check_type: str = None) -> Optional[HealthCheckResult]:
        """Get the latest health check for a skill.

        Args:
            skill_id: File hash or local path
            check_type: Optional filter by check type

        Returns:
            HealthCheckResult if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            if check_type:
                cursor.execute("""
                    SELECT check_id, check_type, skill_id, check_result, check_details, checked_at, created_at
                    FROM health_checks
                    WHERE skill_id = ? AND check_type = ?
                    ORDER BY checked_at DESC LIMIT 1
                """, (skill_id, check_type))
            else:
                cursor.execute("""
                    SELECT check_id, check_type, skill_id, check_result, check_details, checked_at, created_at
                    FROM health_checks
                    WHERE skill_id = ?
                    ORDER BY checked_at DESC LIMIT 1
                """, (skill_id,))

            row = cursor.fetchone()
            if row:
                return HealthCheckResult(
                    check_id=row[0],
                    check_type=row[1],
                    skill_id=row[2],
                    check_result=row[3],
                    check_details=row[4],
                    checked_at=row[5],
                    created_at=row[6],
                )
            return None

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return None
        finally:
            conn.close()

    def update_skill_health(self, skill_id: str, health_status: str, checked_at: str) -> bool:
        """Update a skill's health status.

        Args:
            skill_id: File hash of the skill
            health_status: New health status
            checked_at: When the check was performed

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE processed_skills
                SET health_status = ?, last_health_check = ?
                WHERE file_hash = ?
            """, (health_status, checked_at, skill_id))

            conn.commit()
            return cursor.rowcount > 0

        except sqlite3.Error as e:
            logger.error(f"Database update error: {e}")
            return False
        finally:
            conn.close()

    def get_unhealthy_skills(self, status: str = "failed") -> List[SkillInfo]:
        """Get skills with a specific health status.

        Args:
            status: Health status to filter by (default: failed)

        Returns:
            List of SkillInfo objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT file_hash, source_repo, source_path, source_url,
                       skill_name, category, subcategory, processed_at, local_path,
                       source_created_at, source_updated_at, repo_stars, repo_forks,
                       repo_last_synced, repo_description, health_status, last_health_check
                FROM processed_skills WHERE health_status = ?
                ORDER BY last_health_check DESC
            """, (status,))

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
                    source_created_at=row[9],
                    source_updated_at=row[10],
                    repo_stars=row[11],
                    repo_forks=row[12],
                    repo_last_synced=row[13],
                    repo_description=row[14],
                    health_status=row[15],
                    last_health_check=row[16],
                ))

            return results

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
        finally:
            conn.close()

    # ========== Webhook Event Methods ==========

    def add_webhook_event(self, event_type: str, repo_name: str,
                          event_payload: str = None, received_at: str = None) -> int:
        """Add a webhook event to the database.

        Args:
            event_type: Type of event (push, release, repository)
            repo_name: Repository full name
            event_payload: Optional JSON payload
            received_at: When the event was received

        Returns:
            Event ID if successful, -1 otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO webhook_events
                (event_type, repo_name, event_payload, received_at)
                VALUES (?, ?, ?, ?)
            """, (event_type, repo_name, event_payload, received_at or datetime.utcnow().isoformat()))

            conn.commit()
            event_id = cursor.lastrowid
            logger.debug(f"Added webhook event #{event_id} ({event_type} from {repo_name})")
            return event_id

        except sqlite3.Error as e:
            logger.error(f"Database insert error for webhook event: {e}")
            return -1
        finally:
            conn.close()

    def get_pending_events(self, max_retries: int = 3) -> List[WebhookEvent]:
        """Get pending webhook events.

        Args:
            max_retries: Maximum retry count to include

        Returns:
            List of WebhookEvent objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT event_id, event_type, repo_name, event_payload, received_at,
                       processed_at, processing_status, retry_count, error_message, created_at
                FROM webhook_events
                WHERE processing_status = 'pending' OR (processing_status = 'failed' AND retry_count < ?)
                ORDER BY created_at ASC
            """, (max_retries,))

            results = []
            for row in cursor.fetchall():
                results.append(WebhookEvent(
                    event_id=row[0],
                    event_type=row[1],
                    repo_name=row[2],
                    event_payload=row[3],
                    received_at=row[4],
                    processed_at=row[5],
                    processing_status=row[6],
                    retry_count=row[7],
                    error_message=row[8],
                    created_at=row[9],
                ))

            return results

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
        finally:
            conn.close()

    def update_webhook_event(self, event_id: int, status: str,
                             error_message: str = None, increment_retry: bool = False) -> bool:
        """Update webhook event processing status.

        Args:
            event_id: Event ID
            status: New processing status
            error_message: Optional error message
            increment_retry: Whether to increment retry count

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            if increment_retry:
                cursor.execute("""
                    UPDATE webhook_events
                    SET processing_status = ?, processed_at = ?, error_message = ?, retry_count = retry_count + 1
                    WHERE event_id = ?
                """, (status, datetime.utcnow().isoformat(), error_message, event_id))
            else:
                cursor.execute("""
                    UPDATE webhook_events
                    SET processing_status = ?, processed_at = ?, error_message = ?
                    WHERE event_id = ?
                """, (status, datetime.utcnow().isoformat(), error_message, event_id))

            conn.commit()
            logger.debug(f"Updated webhook event #{event_id} status to {status}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Database update error: {e}")
            return False
        finally:
            conn.close()

    def mark_event_processed(self, event_id: int) -> bool:
        """Mark a webhook event as successfully processed.

        Args:
            event_id: Event ID

        Returns:
            True if successful, False otherwise
        """
        return self.update_webhook_event(event_id, "completed")
