from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime, timezone

from field_utils import FIELD_TYPES, DATE_FORMATS, normalize_value

DB_PATH = Path(__file__).resolve().parent / "data" / "machines.db"


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_db(db_path: Path) -> Path:
    """Initialize records and import the previous schema once, keeping its tables."""
    with closing(get_connection(db_path)) as connection, connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS custom_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sort_order INTEGER NOT NULL,
                field_name TEXT COLLATE NOCASE UNIQUE,
                CHECK(field_name IS NULL OR length(field_name) BETWEEN 1 AND 10)
            );
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT UNIQUE,
                qr_filename TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TRIGGER IF NOT EXISTS permanent_record_id
            BEFORE UPDATE OF record_id ON records
            WHEN OLD.record_id IS NOT NULL AND NEW.record_id IS NOT OLD.record_id
            BEGIN SELECT RAISE(ABORT, 'Record ID cannot be changed'); END;
            CREATE TABLE IF NOT EXISTS record_values (
                record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
                field_id INTEGER NOT NULL REFERENCES custom_fields(id) ON DELETE CASCADE,
                field_value TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (record_id, field_id)
            );
            CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY);
        """)
        connection.execute("BEGIN IMMEDIATE")
        if not connection.execute("SELECT 1 FROM schema_migrations WHERE version = 1").fetchone():
            _import_legacy_data(connection)
            connection.execute("INSERT INTO schema_migrations VALUES (1)")
            if not connection.execute("SELECT 1 FROM custom_fields").fetchone():
                connection.execute("INSERT INTO custom_fields (sort_order) VALUES (0)")
        if not connection.execute("SELECT 1 FROM schema_migrations WHERE version = 2").fetchone():
            connection.execute("ALTER TABLE custom_fields ADD COLUMN field_type TEXT NOT NULL DEFAULT 'Text' CHECK(field_type IN ('Text', 'Date', 'Number'))")
            connection.execute("ALTER TABLE custom_fields ADD COLUMN date_format TEXT NOT NULL DEFAULT 'DD/MM/YYYY' CHECK(date_format IN ('DD/MM/YYYY', 'MM/DD/YYYY', 'YYYY/MM/DD'))")
            # Older records have no reliable edit history. Do not invent a timestamp.
            connection.execute("ALTER TABLE records ADD COLUMN updated_at TEXT")
            connection.execute("INSERT INTO schema_migrations VALUES (2)")
        if not connection.execute("SELECT 1 FROM schema_migrations WHERE version = 3").fetchone():
            # Merge numeric fields into the general input without rewriting values.
            connection.execute("UPDATE custom_fields SET field_type = 'Text' WHERE field_type = 'Number'")
            connection.execute("INSERT INTO schema_migrations VALUES (3)")
        _reset_empty_record_qrs(connection)
    return db_path


def _reset_empty_record_qrs(connection: sqlite3.Connection, record_id: str | None = None) -> None:
    """Invalidate generated QR references when no saved, nonblank field value remains."""
    empty_records = set()
    populated_records = set()
    for row in connection.execute(
        """SELECT r.record_id, v.field_value, f.field_name
           FROM records r
           LEFT JOIN record_values v ON v.record_id = r.record_id
           LEFT JOIN custom_fields f ON f.id = v.field_id
           WHERE r.qr_filename IS NOT NULL AND (? IS NULL OR r.record_id = ?)""",
        (record_id, record_id),
    ):
        empty_records.add(row["record_id"])
        if row["field_name"] and row["field_value"] and row["field_value"].strip():
            populated_records.add(row["record_id"])
    connection.executemany(
        "UPDATE records SET qr_filename = NULL WHERE record_id = ?",
        [(value,) for value in empty_records - populated_records],
    )


def _import_legacy_data(connection: sqlite3.Connection) -> None:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "field_settings" in tables:
        for row in connection.execute("SELECT * FROM field_settings ORDER BY sort_order LIMIT 6").fetchall():
            connection.execute(
                "INSERT INTO custom_fields (sort_order, field_name) VALUES (?, ?)",
                (row["sort_order"], row["field_name"]),
            )
    if "equipment" not in tables:
        return
    fields = {row["field_name"].casefold(): row["id"] for row in connection.execute(
        "SELECT id, field_name FROM custom_fields WHERE field_name IS NOT NULL"
    )}
    for row in connection.execute("SELECT * FROM equipment ORDER BY id").fetchall():
        record_id = row["record_id"] if "record_id" in row.keys() else None
        if record_id and record_id.startswith("REC-") and record_id[4:].isdigit():
            # Preserve existing IDs and advance AUTOINCREMENT beyond them.
            connection.execute(
                "INSERT INTO records (id, record_id, qr_filename) VALUES (?, ?, ?)",
                (int(record_id[4:]), record_id, row["qr_filename"]),
            )
        else:
            record_id = _insert_record(connection)
        if "equipment_custom_fields" in tables:
            for value in connection.execute(
                "SELECT field_name, field_value FROM equipment_custom_fields WHERE equipment_id = ?",
                (row["id"],),
            ).fetchall():
                field_id = fields.get(value["field_name"].casefold())
                if field_id is not None:
                    connection.execute(
                        "INSERT OR REPLACE INTO record_values VALUES (?, ?, ?)",
                        (record_id, field_id, value["field_value"] or ""),
                    )


def get_fields(db_path: Path, *, saved_only: bool = False) -> list[dict]:
    with closing(get_connection(db_path)) as connection:
        where = "WHERE field_name IS NOT NULL" if saved_only else ""
        return [dict(row) for row in connection.execute(
            f"SELECT * FROM custom_fields {where} ORDER BY sort_order, id"
        )]


def add_field(db_path: Path) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        count, last = connection.execute("SELECT count(*), max(sort_order) FROM custom_fields").fetchone()
        if count >= 6:
            raise ValueError("A maximum of 6 field names is allowed.")
        connection.execute("INSERT INTO custom_fields (sort_order) VALUES (?)", ((last or 0) + 1,))


def save_field_name(db_path: Path, field_id: int, name: str, field_type: str | None = None, date_format: str | None = None) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Field name is required before saving.")
    if len(name) > 10:
        raise ValueError("Field names must be 10 characters or fewer.")
    if name.casefold() in {"record id", "qr code"}:
        raise ValueError("Record ID and QR Code are reserved system columns.")
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute("SELECT * FROM custom_fields WHERE id = ?", (field_id,)).fetchone()
        if not existing:
            raise ValueError("This field no longer exists. Refresh the page.")
        field_type = field_type if field_type is not None else existing["field_type"]
        date_format = date_format if date_format is not None else existing["date_format"]
        if field_type not in FIELD_TYPES or date_format not in DATE_FORMATS:
            raise ValueError("Choose a valid field type and date format.")
        if any(row["id"] != field_id and (row["field_name"] or "").casefold() == name.casefold()
               for row in connection.execute("SELECT id, field_name FROM custom_fields")):
            raise ValueError("Field names must be unique.")
        connection.execute("UPDATE custom_fields SET field_name = ?, field_type = ?, date_format = ? WHERE id = ?",
                           (name, field_type, date_format, field_id))
        # Preserve existing text. Ambiguous dates must be reviewed on each record.


def remove_field(db_path: Path, field_id: int) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE records SET updated_at = ? WHERE record_id IN (SELECT record_id FROM record_values WHERE field_id = ?)",
                           (_now(), field_id))
        connection.execute("DELETE FROM custom_fields WHERE id = ?", (field_id,))
        _reset_empty_record_qrs(connection)


def _insert_record(connection: sqlite3.Connection) -> str:
    cursor = connection.execute("INSERT INTO records DEFAULT VALUES")
    record_id = f"REC-{cursor.lastrowid:04d}"
    connection.execute("UPDATE records SET record_id = ? WHERE id = ?", (record_id, cursor.lastrowid))
    return record_id


def create_record(db_path: Path) -> str:
    with closing(get_connection(db_path)) as connection, connection:
        record_id = _insert_record(connection)
        connection.execute("UPDATE records SET updated_at = ? WHERE record_id = ?", (_now(), record_id))
        return record_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def get_records(db_path: Path) -> list[dict]:
    with closing(get_connection(db_path)) as connection:
        connection.execute("BEGIN")
        records = {row["record_id"]: dict(row) | {"values": {}} for row in connection.execute(
            "SELECT * FROM records ORDER BY id"
        )}
        for row in connection.execute("SELECT * FROM record_values"):
            records[row["record_id"]]["values"][row["field_id"]] = row["field_value"]
        return list(records.values())


def get_record(db_path: Path, record_id: str) -> dict | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute("SELECT * FROM records WHERE record_id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        values = {value["field_id"]: value["field_value"] for value in connection.execute(
            "SELECT field_id, field_value FROM record_values WHERE record_id = ?", (record_id,)
        )}
        return dict(row) | {"values": values}


def save_record_value(db_path: Path, record_id: str, field_id: int, value) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        field = connection.execute("SELECT * FROM custom_fields WHERE id = ?", (field_id,)).fetchone()
        if not field or not field["field_name"]:
            raise ValueError("Save this field name in Admin Panel first.")
        value = normalize_value(field["field_type"], value)
        if not connection.execute("SELECT 1 FROM records WHERE record_id = ?", (record_id,)).fetchone():
            raise ValueError("This record no longer exists.")
        previous = connection.execute("SELECT field_value FROM record_values WHERE record_id = ? AND field_id = ?", (record_id, field_id)).fetchone()
        if (previous["field_value"] if previous else "") == value:
            return
        connection.execute(
            """INSERT INTO record_values VALUES (?, ?, ?)
               ON CONFLICT(record_id, field_id) DO UPDATE SET field_value = excluded.field_value""",
            (record_id, field_id, value),
        )
        _reset_empty_record_qrs(connection, record_id)
        connection.execute("UPDATE records SET updated_at = ? WHERE record_id = ?", (_now(), record_id))


def save_record_qr(db_path: Path, record_id: str, qr_filename: str) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        values = connection.execute(
            """SELECT v.field_value FROM record_values v
               JOIN custom_fields f ON f.id = v.field_id
               WHERE v.record_id = ? AND f.field_name IS NOT NULL""",
            (record_id,),
        ).fetchall()
        if not any(row["field_value"].strip() for row in values):
            raise ValueError("Save at least one field value before generating QR.")
        connection.execute("UPDATE records SET qr_filename = ? WHERE record_id = ?", (qr_filename, record_id))


def delete_records(db_path: Path, record_ids: list[str]) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.executemany("DELETE FROM records WHERE record_id = ?", [(value,) for value in record_ids])
