from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "data" / "machines.db"

EQUIPMENT_FIELDS = (
    "supplier_vendor",
    "contact_person",
    "contact_info",
    "purchase_date",
    "installation_date",
    "last_service_date",
    "next_service_date",
    "setup_notes",
    "troubleshooting_notes",
    "custom_fields",
)


def initialize_db(db_path: Path) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT UNIQUE NOT NULL,
            machine_name TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT,
            manual_filename TEXT,
            qr_filename TEXT,
            supplier_vendor TEXT,
            contact_person TEXT,
            contact_info TEXT,
            purchase_date TEXT,
            installation_date TEXT,
            last_service_date TEXT,
            next_service_date TEXT,
            setup_notes TEXT,
            troubleshooting_notes TEXT,
            custom_fields TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(machines)").fetchall()
    }
    for field in EQUIPMENT_FIELDS:
        if field not in columns:
            default = " DEFAULT '[]'" if field == "custom_fields" else ""
            connection.execute(f"ALTER TABLE machines ADD COLUMN {field} TEXT{default}")
    connection.commit()
    connection.close()
    return db_path


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def insert_machine(db_path: Path, machine: Dict[str, Any]) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO machines (
                machine_id,
                machine_name,
                location,
                description,
                manual_filename,
                qr_filename,
                supplier_vendor,
                contact_person,
                contact_info,
                purchase_date,
                installation_date,
                last_service_date,
                next_service_date,
                setup_notes,
                troubleshooting_notes,
                custom_fields
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                machine["machine_id"],
                machine["machine_name"],
                machine["location"],
                machine.get("description", ""),
                machine.get("manual_filename"),
                machine.get("qr_filename"),
                machine.get("supplier_vendor", ""),
                machine.get("contact_person", ""),
                machine.get("contact_info", ""),
                machine.get("purchase_date", ""),
                machine.get("installation_date", ""),
                machine.get("last_service_date", ""),
                machine.get("next_service_date", ""),
                machine.get("setup_notes", ""),
                machine.get("troubleshooting_notes", ""),
                json.dumps(machine.get("custom_fields", [])),
            ),
        )
        connection.commit()


def update_machine(db_path: Path, machine_id: str, machine: Dict[str, Any]) -> None:
    """Update equipment details without changing its permanent ID or QR filename."""
    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE machines
            SET machine_name = ?,
                location = ?,
                description = ?,
                manual_filename = ?,
                supplier_vendor = ?,
                contact_person = ?,
                contact_info = ?,
                purchase_date = ?,
                installation_date = ?,
                last_service_date = ?,
                next_service_date = ?,
                setup_notes = ?,
                troubleshooting_notes = ?,
                custom_fields = ?
            WHERE machine_id = ?
            """,
            (
                machine["machine_name"],
                machine["location"],
                machine.get("description", ""),
                machine.get("manual_filename"),
                machine.get("supplier_vendor", ""),
                machine.get("contact_person", ""),
                machine.get("contact_info", ""),
                machine.get("purchase_date", ""),
                machine.get("installation_date", ""),
                machine.get("last_service_date", ""),
                machine.get("next_service_date", ""),
                machine.get("setup_notes", ""),
                machine.get("troubleshooting_notes", ""),
                json.dumps(machine.get("custom_fields", [])),
                machine_id,
            ),
        )
        connection.commit()


def update_qr_filename(db_path: Path, machine_id: str, qr_filename: str) -> None:
    """Store the QR filename after an explicit equipment QR generation action."""
    with get_connection(db_path) as connection:
        connection.execute(
            "UPDATE machines SET qr_filename = ? WHERE machine_id = ?",
            (qr_filename, machine_id),
        )
        connection.commit()


def delete_machine(db_path: Path, machine_id: str) -> None:
    """Delete one machine record from the local database."""
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM machines WHERE machine_id = ?", (machine_id,))
        connection.commit()


def get_all_machines(db_path: Path) -> List[Dict[str, Any]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM machines ORDER BY machine_name ASC"
        ).fetchall()
    return [_decode_machine(dict(row)) for row in rows]


def get_machine_by_id(db_path: Path, machine_id: str) -> Optional[Dict[str, Any]]:
    machine_id = (machine_id or "").strip()
    if not machine_id:
        return None
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM machines WHERE machine_id = ?",
            (machine_id,),
        ).fetchone()
    return _decode_machine(dict(row)) if row else None


def _decode_machine(machine: Dict[str, Any]) -> Dict[str, Any]:
    try:
        machine["custom_fields"] = json.loads(machine.get("custom_fields") or "[]")
    except (TypeError, json.JSONDecodeError):
        machine["custom_fields"] = []
    return machine
