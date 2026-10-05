"""One-time preservation of an existing install when adopting the LeadZen name."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Historical database identifiers are necessary to find and move the existing rows.
# They are never exposed by the product's interface or its commands.
LEGACY_APP_LABEL = "openoutreach_config"
CURRENT_APP_LABEL = "leadzen_config"


def upgrade_database(database: Path) -> Path | None:
    """Rename this application's tables and migration records, with a SQLite backup.

    Finder/sender tables, foreign keys, IDs, mail history, and credential values are
    left intact. This is idempotent and returns immediately for a new database.
    """
    if not database.is_file():
        return None
    with sqlite3.connect(database, timeout=30) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        old_tables = sorted(table for table in tables if table.startswith(LEGACY_APP_LABEL + "_"))
        if not old_tables:
            return None
        targets = {table.replace(LEGACY_APP_LABEL, CURRENT_APP_LABEL, 1) for table in old_tables}
        if targets & tables:
            raise RuntimeError("LeadZen upgrade found two configurations; resolve the duplicate database before starting")
        backup = database.with_name(database.stem + ".before-leadzen" + database.suffix)
        # Reserve the exact backup path without overwriting a prior recovery copy.
        if not backup.exists():
            descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            with sqlite3.connect(backup) as destination:
                connection.backup(destination)
        # An interrupted backup can leave an empty/corrupt reserved file. Do not
        # mistake its existence for a usable recovery point on the next startup.
        try:
            with sqlite3.connect(backup.resolve().as_uri() + "?mode=ro", uri=True) as recovery:
                recovered_tables = {row[0] for row in recovery.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                valid = recovery.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            if not valid or not set(old_tables).issubset(recovered_tables):
                raise RuntimeError("LeadZen recovery copy is incomplete; restore a verified backup before upgrading")
        except sqlite3.DatabaseError:
            raise RuntimeError("LeadZen recovery copy is unreadable; restore a verified backup before upgrading") from None
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table in old_tables:
                target = table.replace(LEGACY_APP_LABEL, CURRENT_APP_LABEL, 1)
                connection.execute(f'ALTER TABLE "{table}" RENAME TO "{target}"')
            if "django_migrations" in tables:
                connection.execute("UPDATE django_migrations SET app=? WHERE app=?", (CURRENT_APP_LABEL, LEGACY_APP_LABEL))
            if "django_content_type" in tables:
                connection.execute("UPDATE django_content_type SET app_label=? WHERE app_label=?", (CURRENT_APP_LABEL, LEGACY_APP_LABEL))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return backup
