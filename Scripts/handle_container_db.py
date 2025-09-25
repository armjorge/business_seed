"""Utility helpers to persist project/container information in a SQLite database."""

import os
import sqlite3
from contextlib import closing
from typing import Dict, List, Optional


class ProjectDatabase:
    """High level wrapper around the projects SQLite database."""

    def __init__(self, working_folder: str) -> None:
        self.working_folder = working_folder
        os.makedirs(self.working_folder, exist_ok=True)
        self.db_path = os.path.join(self.working_folder, "container_projects.db")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the projects table when the database file is brand new."""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT NOT NULL,
                    container_name TEXT,
                    container_id TEXT,
                    apex_url TEXT,
                    apex_installed INTEGER NOT NULL DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._upgrade_schema(connection)

    def _upgrade_schema(self, connection: sqlite3.Connection) -> None:
        """Apply schema migrations for older database versions."""
        connection.row_factory = sqlite3.Row
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(projects)")
        }
        reset_container_ids = False
        if "container_name" not in columns:
            connection.execute("ALTER TABLE projects ADD COLUMN container_name TEXT")
            connection.execute(
                "UPDATE projects SET container_name = container_id WHERE container_name IS NULL OR TRIM(container_name) = ''"
            )
            reset_container_ids = True
        if reset_container_ids:
            connection.execute(
                "UPDATE projects SET container_id = NULL WHERE container_name = container_id"
            )

    def add_project(
        self,
        project_name: str,
        container_name: Optional[str] = None,
        apex_url: Optional[str] = None,
        container_id: Optional[str] = None,
    ) -> int:
        """Insert a new project row and return the row id."""
        apex_url = apex_url or "http://localhost:8080/ords"
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects (project_name, container_name, container_id, apex_url)
                VALUES (?, ?, ?, ?)
                """,
                (
                    project_name.strip(),
                    self._normalize(container_name),
                    self._normalize(container_id),
                    apex_url.strip(),
                ),
            )
            return cursor.lastrowid

    def list_projects(self, only_missing_container: bool = False, only_without_apex: bool = False) -> List[Dict]:
        """Return all projects as dictionaries, optionally filtered by status."""
        query = (
            "SELECT id, project_name, container_name, container_id, apex_url, apex_installed "
            "FROM projects"
        )
        filters = []
        params: List = []

        if only_missing_container:
            filters.append(
                "(container_name IS NULL OR TRIM(container_name) = '' "
                "OR container_id IS NULL OR TRIM(container_id) = '')"
            )
        if only_without_apex:
            filters.append("apex_installed = 0")

        if filters:
            query += " WHERE " + " AND ".join(filters)

        query += " ORDER BY id"

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def get_project(self, project_id: int) -> Optional[Dict]:
        """Return a single project row."""
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT id, project_name, container_name, container_id, apex_url, apex_installed
                FROM projects WHERE id = ?
                """,
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_container(
        self,
        project_id: int,
        container_name: Optional[str] = None,
        container_id: Optional[str] = None,
    ) -> None:
        """Update the container metadata for a project."""
        assignments = []
        values: List = []
        if container_name is not None:
            assignments.append("container_name = ?")
            values.append(self._normalize(container_name))
        if container_id is not None:
            assignments.append("container_id = ?")
            values.append(self._normalize(container_id))
        if not assignments:
            return

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                f"""
                UPDATE projects
                SET {', '.join(assignments)}, last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (*values, project_id),
            )

    def update_project_name(self, project_id: int, project_name: str) -> None:
        """Change the name of a tracked project."""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE projects
                SET project_name = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (project_name.strip(), project_id),
            )

    def update_apex_url(self, project_id: int, apex_url: str) -> None:
        """Persist a new APEX URL for a project."""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE projects
                SET apex_url = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (apex_url.strip(), project_id),
            )

    def mark_apex_status(self, project_id: int, installed: bool) -> None:
        """Set the APEX installation flag."""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE projects
                SET apex_installed = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (1 if installed else 0, project_id),
            )

    def delete_project(self, project_id: int) -> None:
        """Remove a project from the database."""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def database_exists(self) -> bool:
        """Signal whether the backing database file is present."""
        return os.path.exists(self.db_path)

    def _normalize(self, value: Optional[str]) -> Optional[str]:
        """Normalize optional string inputs for persistence."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
