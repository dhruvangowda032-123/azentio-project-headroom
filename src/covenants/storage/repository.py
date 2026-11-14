"""SQLite persistence: parameterized SQL, atomic writes, immutable extraction identities."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from covenants.schemas import ExtractionResult


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "headroom.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS agreements (
                    agreement_id TEXT PRIMARY KEY, original_text TEXT NOT NULL, extraction TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, agreement_id TEXT NOT NULL,
                    period TEXT NOT NULL, input_hash TEXT NOT NULL, results TEXT NOT NULL,
                    extraction_meta TEXT NOT NULL, timestamp TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
                    BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
                    BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
            """)

    @contextmanager
    def connection(self):
        with sqlite3.connect(self.path, timeout=10) as db:
            yield db

    def save(self, text: str, result: ExtractionResult) -> None:
        with self.connection() as db:
            # Re-ingestion never silently changes covenants used by earlier audit records.
            db.execute("INSERT OR IGNORE INTO agreements VALUES (?, ?, ?)",
                       (result.agreement_id, text, result.model_dump_json()))

    def get(self, agreement_id: str) -> ExtractionResult:
        with self.connection() as db:
            row = db.execute("SELECT extraction FROM agreements WHERE agreement_id = ?", (agreement_id,)).fetchone()
        if row is None:
            raise KeyError(agreement_id)
        return ExtractionResult.model_validate_json(row[0])

    def audit(self, agreement_id: str, period: str, input_hash: str, results: list[dict], meta: dict) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO audit (agreement_id,period,input_hash,results,extraction_meta,timestamp) VALUES (?,?,?,?,?,?)",
                       (agreement_id, period, input_hash, json.dumps(results, sort_keys=True),
                        json.dumps(meta, sort_keys=True), datetime.now(timezone.utc).isoformat()))

