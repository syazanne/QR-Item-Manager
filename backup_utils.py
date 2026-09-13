"""Portable, versioned backups of active records (not legacy database tables)."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import zipfile
import zlib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from database import get_connection
from field_utils import FIELD_TYPES, DATE_FORMATS
from qr_utils import generate_qr_code

MAX_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 10001
MAX_ID = 2**63 - 2


class BackupError(ValueError):
    pass


def _require(condition, message="The backup contains invalid record data."):
    if not condition:
        raise BackupError(message)


def _integer(value, minimum=1):
    return type(value) is int and minimum <= value <= MAX_ID


def _timestamp(value, nullable=False):
    if value is None:
        return nullable
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def _snapshot(connection, qr_dir: Path) -> bytes:
    data = {
        "application": "QR Item Manager", "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "fields": [dict(row) for row in connection.execute("SELECT * FROM custom_fields ORDER BY sort_order, id")],
        "records": [dict(row) for row in connection.execute("SELECT * FROM records ORDER BY id")],
        "values": [dict(row) for row in connection.execute("SELECT * FROM record_values ORDER BY record_id, field_id")],
        "sequences": {name: 0 for name in ("records", "custom_fields")},
        "images": {}, "missing_qr_images": [],
    }
    for row in connection.execute("SELECT name, seq FROM sqlite_sequence WHERE name IN ('records', 'custom_fields')"):
        data["sequences"][row["name"]] = row["seq"]
    images = {}
    image_bytes = 0
    root = qr_dir.resolve()
    for record in data["records"]:
        filename = record["qr_filename"]
        record["qr_filename"] = None
        if filename:
            path = (qr_dir / filename).resolve()
            _require(root in path.parents, "A QR image path is outside the QR folder.")
            if path.is_file():
                _require(path.stat().st_size <= MAX_BYTES, "The QR image is too large to back up.")
                content = path.read_bytes()
                image_bytes += len(content)
                _require(image_bytes <= MAX_BYTES, "The QR images exceed the 100 MB backup limit.")
                name = f"qr_codes/{record['record_id']}.png"
                images[name] = content
                record["qr_filename"] = name
                data["images"][name] = hashlib.sha256(content).hexdigest()
            else:
                data["missing_qr_images"].append(record["record_id"])
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(data, ensure_ascii=False).encode("utf-8"))
        for name, content in images.items():
            archive.writestr(name, content)
    result = output.getvalue()
    # Never offer a backup that this version cannot restore.
    read_backup(result)
    return result


def create_backup(db_path: Path, qr_dir: Path) -> bytes:
    with closing(get_connection(db_path)) as connection:
        connection.execute("BEGIN")
        return _snapshot(connection, qr_dir)


def read_backup(payload: bytes) -> dict:
    """Validate without extracting files or changing any application data."""
    _require(len(payload) <= MAX_BYTES, "Backup files must be 100 MB or smaller.")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            _require(len(entries) <= MAX_ENTRIES and len(names) == len(set(names)), "The ZIP has too many files or duplicate file names.")
            _require(sum(entry.file_size for entry in entries) <= MAX_BYTES, "The expanded backup exceeds 100 MB.")
            _require("manifest.json" in names, "Choose a Backup ZIP created by this app.")
            data = json.loads(archive.read("manifest.json"))
            _validate_manifest(data)
            _require(set(names) == {"manifest.json", *data["images"]}, "The ZIP contains missing or unexpected files.")
            for name, digest in data["images"].items():
                _require(hashlib.sha256(archive.read(name)).hexdigest() == digest, "A QR image is damaged or does not match the backup.")
            return data
    except BackupError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        raise BackupError("This backup is damaged or has an unsupported format.") from exc


def _validate_manifest(data):
    _require(isinstance(data, dict))
    # Accept archives made before the app was renamed as well.
    _require(data.get("application") in ("QR Item Manager", "QR-MedTech") and type(data.get("version")) is int and data["version"] == 1,
             "Choose a supported QR Item Manager backup (version 1).")
    _require(_timestamp(data.get("exported_at")))
    fields, records, values = data.get("fields"), data.get("records"), data.get("values")
    _require(isinstance(fields, list) and len(fields) <= 6)
    _require(isinstance(records, list) and isinstance(values, list))
    sequences, images = data.get("sequences"), data.get("images")
    _require(isinstance(sequences, dict) and set(sequences) == {"records", "custom_fields"})
    _require(all(_integer(seq, 0) for seq in sequences.values()))
    _require(isinstance(images, dict))
    field_ids, field_names, named_fields = set(), set(), set()
    for field in fields:
        _require(isinstance(field, dict) and set(field) == {"id", "sort_order", "field_name", "field_type", "date_format"})
        _require(_integer(field["id"]) and field["id"] not in field_ids and _integer(field["sort_order"], 0))
        _require(field["field_type"] in FIELD_TYPES and field["date_format"] in DATE_FORMATS)
        name = field["field_name"]
        _require(name is None or isinstance(name, str) and 1 <= len(name) <= 10 and name == name.strip())
        if name is not None:
            _require(name.casefold() not in field_names | {"record id", "qr code"})
            field_names.add(name.casefold())
            named_fields.add(field["id"])
        field_ids.add(field["id"])
    record_ids, integer_ids, qr_names = set(), set(), set()
    for record in records:
        _require(isinstance(record, dict) and set(record) == {"id", "record_id", "qr_filename", "created_at", "updated_at"})
        _require(_integer(record["id"]) and record["id"] not in integer_ids)
        _require(record["record_id"] == f"REC-{record['id']:04d}")
        _require(_timestamp(record["created_at"]) and _timestamp(record["updated_at"], nullable=True))
        filename = record["qr_filename"]
        _require(filename is None or filename == f"qr_codes/{record['record_id']}.png")
        if filename:
            qr_names.add(filename)
        record_ids.add(record["record_id"])
        integer_ids.add(record["id"])
    _require(set(images) == qr_names)
    _require(all(isinstance(digest, str) and len(digest) == 64 for digest in images.values()))
    _require(sequences["records"] >= max(integer_ids, default=0) and sequences["custom_fields"] >= max(field_ids, default=0))
    pairs, populated = set(), set()
    for value in values:
        _require(isinstance(value, dict) and set(value) == {"record_id", "field_id", "field_value"})
        _require(isinstance(value["record_id"], str) and _integer(value["field_id"]))
        pair = value["record_id"], value["field_id"]
        _require(pair not in pairs and pair[0] in record_ids and pair[1] in field_ids and isinstance(value["field_value"], str))
        pairs.add(pair)
        if pair[1] in named_fields and value["field_value"].strip():
            populated.add(pair[0])
    _require(all(record["record_id"] in populated for record in records if record["qr_filename"]))
    missing = data.get("missing_qr_images")
    _require(isinstance(missing, list) and all(isinstance(rid, str) and rid in record_ids for rid in missing))


def restore_backup(payload: bytes, db_path: Path, qr_dir: Path, safety_dir: Path) -> Path:
    """Restore atomically in SQLite; new QR files never overwrite current images."""
    data = read_backup(payload)
    staged = qr_dir / f"restore_{uuid4().hex}"
    try:
        # Regenerate from permanent IDs so an uploaded image cannot point at another record.
        for record in data["records"]:
            if record["qr_filename"]:
                filename = generate_qr_code(record["record_id"], staged)
                record["qr_filename"] = f"{staged.name}/{filename}"
        with closing(get_connection(db_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            # The lock keeps the safety copy and replaced database at the same revision.
            safety = _snapshot(connection, qr_dir)
            safety_dir.mkdir(parents=True, exist_ok=True)
            path = safety_dir / f"before-restore-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.zip"
            temporary = path.with_suffix(".tmp")
            try:
                with temporary.open("xb") as output:
                    output.write(safety)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            previous_sequences = dict(connection.execute("SELECT name, seq FROM sqlite_sequence"))
            connection.execute("DELETE FROM record_values")
            connection.execute("DELETE FROM records")
            connection.execute("DELETE FROM custom_fields")
            connection.executemany(
                "INSERT INTO custom_fields (id, sort_order, field_name, field_type, date_format) VALUES (:id, :sort_order, :field_name, :field_type, :date_format)", data["fields"])
            connection.executemany(
                "INSERT INTO records (id, record_id, qr_filename, created_at, updated_at) VALUES (:id, :record_id, :qr_filename, :created_at, :updated_at)", data["records"])
            connection.executemany(
                "INSERT INTO record_values (record_id, field_id, field_value) VALUES (:record_id, :field_id, :field_value)", data["values"])
            for name, seq in data["sequences"].items():
                connection.execute("DELETE FROM sqlite_sequence WHERE name = ?", (name,))
                connection.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (name, max(seq, previous_sequences.get(name, 0))))
        return path
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise
