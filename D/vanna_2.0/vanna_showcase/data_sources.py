"""Local data-source registry and safe file-backed SQL runners for the showcase."""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import sqlite3
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import httpx
import pandas as pd

from vanna.capabilities.sql_runner import RunSqlToolArgs, SqlRunner
from vanna.core.tool import ToolContext


MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_RESULT_ROWS = 5000
MAX_CHINOOK_BYTES = 5 * 1024 * 1024
CHINOOK_DOWNLOAD_URL = "https://vanna.ai/Chinook.sqlite"
SQLITE_HEADER = b"SQLite format 3\x00"
EXPECTED_CHINOOK_TABLES = frozenset(
    {
        "Album",
        "Artist",
        "Customer",
        "Employee",
        "Genre",
        "Invoice",
        "InvoiceLine",
        "MediaType",
        "Playlist",
        "PlaylistTrack",
        "Track",
    }
)
SAFE_NAME = re.compile(r"[^0-9A-Za-z_.-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_identifier(value: str) -> str:
    value = SAFE_NAME.sub("_", value.strip().lstrip("."))
    value = value.strip("_") or "table"
    if value[0].isdigit():
        value = f"table_{value}"
    return value[:120]


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def validate_chinook_database(database_path: Path) -> None:
    """Verify a file is a healthy Chinook SQLite sample."""
    if not database_path.is_file():
        raise FileNotFoundError(f"Chinook database not found: {database_path}")
    if database_path.stat().st_size == 0:
        raise RuntimeError(f"Chinook database is empty: {database_path}")
    with database_path.open("rb") as database_file:
        if database_file.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise RuntimeError(f"Invalid SQLite header: {database_path}")
    try:
        uri = f"{database_path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if not quick_check or quick_check[0] != "ok":
                raise RuntimeError(f"SQLite integrity check failed: {quick_check!r}")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
    except sqlite3.Error as exc:
        raise RuntimeError(f"Unable to read Chinook database: {exc}") from exc
    missing = EXPECTED_CHINOOK_TABLES - tables
    if missing:
        raise RuntimeError(
            "Database is not the Chinook sample; missing: " + ", ".join(sorted(missing))
        )


class DataSourceManager:
    """Persist data-source metadata and route conversations to their database."""

    def __init__(
        self, working_directory: Path, default_database: Path | None = None
    ) -> None:
        self.root = working_directory.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.dataset_root = self.root / "datasets"
        self.dataset_root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "data_sources.sqlite"
        self.default_database = default_database.resolve() if default_database else None
        self.managed_chinook_path = self.dataset_root / "chinook" / "database.sqlite"
        self.chinook_error: str | None = None
        self._chinook_lock = threading.Lock()
        self._chinook_async_lock = asyncio.Lock()
        self._initialize()
        self._reconcile_chinook()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.registry_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    access_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    database_path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    allowed_groups_json TEXT NOT NULL DEFAULT '["user", "admin"]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_sources (
                    conversation_id TEXT PRIMARY KEY,
                    data_source_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(data_source_id) REFERENCES data_sources(id)
                );
                """
            )

    def _register_chinook(self, database_path: Path, *, managed: bool) -> dict:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO data_sources
                    (id, name, kind, access_mode, status, database_path,
                     metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    kind=excluded.kind,
                    access_mode=excluded.access_mode,
                    status=excluded.status,
                    database_path=excluded.database_path,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    "chinook",
                    "Chinook SQLite",
                    "sqlite",
                    "sample",
                    "ready",
                    str(database_path.resolve()),
                    json.dumps(
                        {
                            "description": "Official Vanna Chinook sample database",
                            "sample": True,
                            "managed": managed,
                        }
                    ),
                    now,
                    now,
                ),
            )
        return self.get_source("chinook") or {}

    def _remove_chinook_registration(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM conversation_sources WHERE data_source_id='chinook'"
            )
            connection.execute("DELETE FROM data_sources WHERE id='chinook'")

    def _reconcile_chinook(self) -> None:
        """Register a valid existing sample, otherwise keep startup non-blocking."""
        existing = self.get_source("chinook")
        candidates: list[tuple[Path, bool]] = []
        if existing:
            candidates.append(
                (
                    Path(existing["database_path"]),
                    bool(existing["metadata"].get("managed")),
                )
            )
        if self.default_database and all(
            path.resolve() != self.default_database for path, _ in candidates
        ):
            candidates.append((self.default_database, False))
        if self.managed_chinook_path.is_file() and all(
            path.resolve() != self.managed_chinook_path.resolve()
            for path, _ in candidates
        ):
            candidates.append((self.managed_chinook_path, True))

        self.chinook_error = None
        for candidate, managed in candidates:
            if not candidate.exists():
                continue
            try:
                validate_chinook_database(candidate)
            except Exception as exc:
                self.chinook_error = str(exc)
                continue
            self.chinook_error = None
            self._register_chinook(candidate, managed=managed)
            return
        self._remove_chinook_registration()

    def _row(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["allowed_groups"] = json.loads(item.pop("allowed_groups_json") or "[]")
        return item

    @staticmethod
    def public_source(source: dict | None) -> dict | None:
        """Return source metadata without exposing local paths or credentials."""
        if source is None:
            return None
        return {key: value for key, value in source.items() if key != "database_path"}

    def list_sources(self, groups: Iterable[str] = ("user", "admin")) -> list[dict]:
        group_set = set(groups)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM data_sources ORDER BY created_at"
            ).fetchall()
        result = []
        for row in rows:
            item = self._row(row)
            if item and group_set.intersection(item["allowed_groups"]):
                result.append(item)
        return result

    def get_source(self, source_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM data_sources WHERE id = ?", (source_id,)
            ).fetchone()
        return self._row(row)

    def require_source(self, source_id: str, groups: Iterable[str] = ("user",)) -> dict:
        source = self.get_source(source_id)
        if not source:
            raise KeyError(f"Data source not found: {source_id}")
        if not set(groups).intersection(source["allowed_groups"]):
            raise PermissionError("You do not have access to this data source")
        if source["status"] != "ready":
            raise RuntimeError(f"Data source is not ready: {source['status']}")
        return source

    def set_conversation_source(self, conversation_id: str, source_id: str) -> dict:
        source = self.require_source(source_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_sources(conversation_id, data_source_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    data_source_id=excluded.data_source_id, updated_at=excluded.updated_at
                """,
                (conversation_id, source_id, _now()),
            )
        return source

    def source_for_conversation(self, conversation_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT data_source_id FROM conversation_sources
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if row:
            selected = self.get_source(row["data_source_id"])
            if (
                selected
                and selected["status"] == "ready"
                and Path(selected["database_path"]).is_file()
            ):
                return selected
        chinook = self.get_source("chinook")
        if chinook and Path(chinook["database_path"]).is_file():
            return chinook
        for fallback in self.list_sources():
            if (
                fallback["status"] == "ready"
                and Path(fallback["database_path"]).is_file()
            ):
                return fallback
        return None

    def ready_source_count(self) -> int:
        return sum(
            1
            for source in self.list_sources()
            if source["status"] == "ready" and Path(source["database_path"]).is_file()
        )

    def delete_source(self, source_id: str) -> dict:
        """Delete one uploaded source, its files, and all conversation bindings."""
        source = self.get_source(source_id)
        if not source:
            raise KeyError(f"Data source not found: {source_id}")
        database_path = Path(source["database_path"]).resolve()
        source_root = database_path.parent
        dataset_root = self.dataset_root.resolve()
        is_managed_directory = source_root.parent == dataset_root
        is_known_chinook = source_id == "chinook" and database_path in {
            path
            for path in (
                self.default_database,
                self.managed_chinook_path.resolve(),
            )
            if path is not None
        }
        if not is_managed_directory and not is_known_chinook:
            raise RuntimeError(
                "Refusing to delete files outside the managed dataset directory"
            )

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM conversation_sources WHERE data_source_id = ?",
                (source_id,),
            )
            connection.execute("DELETE FROM data_sources WHERE id = ?", (source_id,))
            if is_managed_directory:
                shutil.rmtree(source_root)
                if source_root.exists():
                    raise RuntimeError(
                        "The database directory still exists after deletion"
                    )
            else:
                database_path.unlink()
                if database_path.exists():
                    raise RuntimeError("The database file still exists after deletion")
        return source

    async def install_chinook(self, url: str = CHINOOK_DOWNLOAD_URL) -> dict:
        """Download, validate, atomically install, and register the shared sample."""
        async with self._chinook_async_lock:
            existing = self.get_source("chinook")
            if existing and Path(existing["database_path"]).is_file():
                validate_chinook_database(Path(existing["database_path"]))
                return existing
            chunks = []
            total = 0
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_CHINOOK_BYTES:
                            raise ValueError(
                                "Chinook download exceeded the 5 MB safety limit"
                            )
                        chunks.append(chunk)
            return self._install_chinook_chunks(chunks)

    def install_chinook_bytes(self, payload: bytes) -> dict:
        """Install validated sample bytes; used by deterministic tests."""
        with self._chinook_lock:
            existing = self.get_source("chinook")
            if existing and Path(existing["database_path"]).is_file():
                validate_chinook_database(Path(existing["database_path"]))
                return existing
            return self._install_chinook_chunks((payload,))

    def _install_chinook_chunks(self, chunks: Iterable[bytes]) -> dict:
        target = self.managed_chinook_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".part")
        total = 0
        try:
            with temporary.open("wb") as output:
                for chunk in chunks:
                    total += len(chunk)
                    if total > MAX_CHINOOK_BYTES:
                        raise ValueError(
                            "Chinook download exceeded the 5 MB safety limit"
                        )
                    output.write(chunk)
            validate_chinook_database(temporary)
            os.replace(temporary, target)
            self.chinook_error = None
            return self._register_chinook(target, managed=True)
        except Exception:
            temporary.unlink(missing_ok=True)
            if target.parent.is_dir() and not any(target.parent.iterdir()):
                target.parent.rmdir()
            raise

    def import_files(self, source_name: str, files: list[tuple[str, bytes]]) -> dict:
        if not source_name.strip():
            raise ValueError("source_name is required")
        if len(source_name.strip()) > 120:
            raise ValueError("source_name must not exceed 120 characters")
        if not files:
            raise ValueError("At least one CSV or ZIP file is required")

        source_id = f"upload_{uuid.uuid4().hex[:12]}"
        source_root = self.dataset_root / source_id
        upload_root = source_root / "uploads"
        database_path = source_root / "database.duckdb"
        upload_root.mkdir(parents=True, exist_ok=False)

        try:
            csv_files: list[tuple[str, bytes]] = []
            total_size = 0
            for filename, content in files:
                total_size += len(content)
                if total_size > MAX_UPLOAD_BYTES:
                    raise ValueError("The total upload size must not exceed 100 MB")
                suffix = Path(filename).suffix.lower()
                if suffix == ".zip":
                    try:
                        with zipfile.ZipFile(io.BytesIO(content)) as archive:
                            expanded_size = 0
                            for member in archive.infolist():
                                if (
                                    member.is_dir()
                                    or Path(member.filename).suffix.lower() != ".csv"
                                ):
                                    continue
                                safe_path = Path(member.filename)
                                if safe_path.is_absolute() or ".." in safe_path.parts:
                                    raise ValueError("ZIP contains an unsafe file path")
                                expanded_size += member.file_size
                                if total_size + expanded_size > MAX_UPLOAD_BYTES:
                                    raise ValueError(
                                        "The expanded upload size must not exceed 100 MB"
                                    )
                                csv_files.append((safe_path.name, archive.read(member)))
                    except zipfile.BadZipFile as exc:
                        raise ValueError("The uploaded ZIP file is invalid") from exc
                elif suffix == ".csv":
                    csv_files.append((Path(filename).name, content))
                else:
                    raise ValueError(
                        "Only CSV and ZIP files are supported in this version"
                    )

            if not csv_files:
                raise ValueError("No CSV files found in the upload")

            import duckdb

            table_names: list[str] = []
            with duckdb.connect(str(database_path)) as connection:
                for filename, content in csv_files:
                    table_name = _safe_identifier(Path(filename).stem)
                    if table_name in table_names:
                        raise ValueError(
                            f"Duplicate table name after normalization: {table_name}"
                        )
                    table_names.append(table_name)
                    target = upload_root / f"{table_name}.csv"
                    target.write_bytes(content)
                    connection.execute(
                        f"CREATE TABLE {_quote_identifier(table_name)} AS "
                        "SELECT * FROM read_csv_auto(?, header=true, sample_size=-1)",
                        [str(target)],
                    )

                schema = self._duckdb_schema(connection, table_names)

            metadata = {
                "tables": table_names,
                "schema": schema,
                "file_count": len(csv_files),
                "row_counts": {
                    name: item["row_count"] for name, item in schema.items()
                },
            }
            now = _now()
            with self._connect() as registry:
                registry.execute(
                    """
                    INSERT INTO data_sources
                        (id, name, kind, access_mode, status, database_path,
                         metadata_json, created_at, updated_at)
                    VALUES (?, ?, 'duckdb', 'upload', 'ready', ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        source_name.strip(),
                        str(database_path),
                        json.dumps(metadata),
                        now,
                        now,
                    ),
                )
            return self.get_source(source_id) or {}
        except Exception:
            shutil.rmtree(source_root, ignore_errors=True)
            raise

    @staticmethod
    def _duckdb_schema(connection, table_names: list[str]) -> dict:
        result = {}
        for table_name in table_names:
            columns = connection.execute(
                f"DESCRIBE {_quote_identifier(table_name)}"
            ).fetchall()
            row_count = connection.execute(
                f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}"
            ).fetchone()[0]
            result[table_name] = {
                "row_count": int(row_count),
                "columns": [
                    {"name": row[0], "type": row[1], "nullable": row[2]}
                    for row in columns
                ],
            }
        return result

    def schema(self, source_id: str) -> dict:
        source = self.require_source(source_id)
        stored_schema = source["metadata"].get("schema", {})
        if stored_schema or source["kind"] != "sqlite":
            return stored_schema
        with sqlite3.connect(
            f"{Path(source['database_path']).resolve().as_uri()}?mode=ro", uri=True
        ) as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
            result = {}
            for table in tables:
                result[table] = {
                    "row_count": int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {_quote_identifier(table)}"
                        ).fetchone()[0]
                    ),
                    "columns": [
                        {"name": row[1], "type": row[2], "nullable": "YES"}
                        for row in connection.execute(
                            f"PRAGMA table_info({_quote_identifier(table)})"
                        )
                    ],
                }
            return result


class MultiSourceSqlRunner(SqlRunner):
    """Select a safe read-only runner from the conversation's active source."""

    def __init__(self, manager: DataSourceManager):
        self.manager = manager

    async def run_sql(self, args: RunSqlToolArgs, context: ToolContext) -> pd.DataFrame:
        source = self.manager.source_for_conversation(context.conversation_id)
        if not source:
            raise RuntimeError("No active data source is configured")
        sql = args.sql.strip()
        if not sql or sql.split(None, 1)[0].upper() != "SELECT":
            raise PermissionError("Only read-only SELECT queries are allowed")
        if ";" in sql.rstrip(";"):
            raise PermissionError("Only one SQL statement is allowed")

        if source["kind"] == "sqlite":
            uri = f"{Path(source['database_path']).resolve().as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=10) as connection:
                connection.execute("PRAGMA query_only = ON")
                frame = pd.read_sql_query(sql, connection)
        elif source["kind"] == "duckdb":
            import duckdb

            with duckdb.connect(source["database_path"], read_only=True) as connection:
                frame = connection.sql(sql).limit(MAX_RESULT_ROWS).to_df()
        else:
            raise RuntimeError(f"Unsupported data source kind: {source['kind']}")

        return frame.head(MAX_RESULT_ROWS)
