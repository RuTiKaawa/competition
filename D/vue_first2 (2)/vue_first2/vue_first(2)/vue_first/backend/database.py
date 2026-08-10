import os
import json
import re
import csv
import shutil
import tempfile
import urllib.request
import zipfile
from decimal import Decimal, InvalidOperation
from threading import Lock
from pathlib import Path
from typing import Any, Dict, List
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

load_dotenv()

DB_TYPE = os.getenv("DB_TYPE", "postgresql").strip().lower()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "a07_manufacturing")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")

SUPPORTED_DB_TYPES = {"postgresql", "mysql"}
DEFAULT_DB_NAME = "postgres"
DATABASE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")
DATABASE_PROFILES_PATH = Path(__file__).with_name(".database_profiles.json")

if DB_TYPE not in SUPPORTED_DB_TYPES:
    DB_TYPE = "postgresql"

_engine_lock = Lock()
_current_config = {
    "db_type": DB_TYPE,
    "host": DB_HOST,
    "port": int(DB_PORT),
    "name": DB_NAME,
    "user": DB_USER,
}


def build_engine(config: dict, isolation_level=None):
    """按数据库类型生成 SQLAlchemy 引擎（pg8000 / pymysql，均为纯 Python 驱动）"""
    db_type = config.get("db_type", "postgresql")
    database = config.get("name") or config.get("database") or DEFAULT_DB_NAME
    if db_type == "mysql":
        url = URL.create(
            "mysql+pymysql",
            username=config["user"],
            password=config.get("password", ""),
            host=config["host"],
            port=int(config.get("port", 3306)),
            database=database,
        )
    else:
        url = URL.create(
            "postgresql+pg8000",
            username=config["user"],
            password=config.get("password", ""),
            host=config["host"],
            port=int(config.get("port", 5432)),
            database=database,
        )
    return create_engine(url, pool_pre_ping=True, poolclass=NullPool, isolation_level=isolation_level)


engine = build_engine({**_current_config, "password": DB_PASSWORD})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_database_config():
    """返回当前连接配置（不含密码）"""
    return {k: _current_config[k] for k in ("db_type", "host", "port", "name", "user")}


def test_database_connection(config: dict):
    """测试连接是否可用"""
    test_engine = build_engine(config)
    try:
        with test_engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    finally:
        test_engine.dispose()


def switch_database(config: dict):
    """切换当前数据库（config 含 host/port/database|name/user/password）"""
    global engine, SessionLocal, _current_config
    cfg = dict(config)
    cfg.setdefault("db_type", DB_TYPE)
    if "database" in cfg and "name" not in cfg:
        cfg["name"] = cfg["database"]
    new_engine = build_engine(cfg)
    try:
        with new_engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception:
        new_engine.dispose()
        raise

    with _engine_lock:
        old_engine = engine
        engine = new_engine
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        _current_config = {
            "db_type": cfg.get("db_type", "postgresql"),
            "host": cfg["host"],
            "port": int(cfg["port"]),
            "name": cfg["name"],
            "user": cfg["user"],
        }
        old_engine.dispose()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================================================
# 数据库工作区（Profiles）管理
# =========================================================

def validate_database_name(name: str) -> str:
    normalized = name.strip()
    if not DATABASE_NAME_RE.fullmatch(normalized):
        raise ValueError("数据库名只能使用字母、数字和下划线，且必须以字母或下划线开头")
    return normalized


def get_database_profiles() -> List[str]:
    names = [DB_NAME]
    try:
        with open(DATABASE_PROFILES_PATH, "r", encoding="utf-8") as profiles_file:
            saved_names = json.load(profiles_file)
        if isinstance(saved_names, list):
            names.extend(name for name in saved_names if isinstance(name, str) and DATABASE_NAME_RE.fullmatch(name))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return list(dict.fromkeys(names))


def remember_database_profile(name: str) -> None:
    profiles = get_database_profiles()
    if name not in profiles:
        profiles.append(name)
    with open(DATABASE_PROFILES_PATH, "w", encoding="utf-8") as profiles_file:
        json.dump(profiles, profiles_file, ensure_ascii=False, indent=2)


def forget_database_profile(name: str) -> None:
    remaining_profiles = [profile for profile in get_database_profiles() if profile != name]
    with open(DATABASE_PROFILES_PATH, "w", encoding="utf-8") as profiles_file:
        json.dump(remaining_profiles, profiles_file, ensure_ascii=False, indent=2)


def _quote_ident(name: str) -> str:
    return f"`{name}`" if _current_config["db_type"] == "mysql" else f'"{name}"'


def quote_ident(name: str) -> str:
    """按当前数据库类型返回带引号的标识符（公开 API）"""
    return _quote_ident(name)


def get_db_type() -> str:
    """返回当前数据库类型（postgresql / mysql）"""
    return _current_config.get("db_type", "postgresql")


def _database_exists(conn, name: str) -> bool:
    if _current_config["db_type"] == "mysql":
        return conn.execute(
            text("SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = :name"),
            {"name": name},
        ).scalar() is not None
    return conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}).scalar() is not None


def switch_database_workspace(name: str, create_if_missing: bool = True) -> Dict[str, Any]:
    """切换到已保存的工作区数据库；不存在时可自动创建"""
    target_name = validate_database_name(name)
    remember_database_profile(DB_NAME)

    base = dict(_current_config)
    base["name"] = target_name

    # 用服务器管理库连接（不依赖目标库存在）
    admin_cfg = dict(base)
    admin_cfg["password"] = DB_PASSWORD
    if admin_cfg["db_type"] == "mysql":
        admin_cfg["name"] = None  # 连接 MySQL 服务器
    else:
        admin_cfg["name"] = DEFAULT_DB_NAME

    admin_engine = build_engine(admin_cfg, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = _database_exists(conn, target_name)
            if not exists:
                if not create_if_missing:
                    raise ValueError(f"数据库 '{target_name}' 不存在")
                if admin_cfg["db_type"] == "mysql":
                    conn.execute(text(f'CREATE DATABASE `{target_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
                else:
                    conn.execute(text(f'CREATE DATABASE "{target_name}"'))
    finally:
        admin_engine.dispose()

    switch_database({**base, "password": DB_PASSWORD})
    remember_database_profile(target_name)
    return {"name": target_name, "profiles": get_database_profiles()}


def delete_database_workspace(name: str) -> Dict[str, Any]:
    """删除工作区数据库（不能删除当前正在使用的）"""
    target_name = validate_database_name(name)
    if target_name == DB_NAME:
        raise ValueError("不能删除当前使用的数据库，请先切换到另一个数据库")
    if target_name not in get_database_profiles():
        raise ValueError(f"数据库 '{target_name}' 不在已保存的工作区列表中")

    admin_cfg = dict(_current_config)
    admin_cfg["password"] = DB_PASSWORD
    admin_cfg["name"] = None if admin_cfg["db_type"] == "mysql" else DEFAULT_DB_NAME
    admin_engine = build_engine(admin_cfg, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = _database_exists(conn, target_name)
            if not exists:
                raise ValueError(f"数据库 '{target_name}' 不存在")
            if admin_cfg["db_type"] == "mysql":
                conn.execute(text(f'DROP DATABASE `{target_name}`'))
            else:
                conn.execute(text(f'DROP DATABASE "{target_name}"'))
    finally:
        admin_engine.dispose()

    forget_database_profile(target_name)
    return {"name": target_name, "profiles": get_database_profiles()}


# =========================================================
# 配置持久化（写入 .env）
# =========================================================

ENV_PATH = Path(__file__).with_name(".env")


def save_db_config_to_env(config: Dict[str, Any]) -> None:
    """保存数据库连接配置到 .env（含数据库软件类型），并重载连接"""
    db_type = config.get("db_type", "postgresql")
    if db_type not in SUPPORTED_DB_TYPES:
        raise ValueError("DB_TYPE 仅支持 postgresql 或 mysql")

    updates = {
        "DB_TYPE": db_type,
        "DB_HOST": str(config["host"]),
        "DB_PORT": str(config["port"]),
        "DB_NAME": str(config["name"]),
        "DB_USER": str(config["user"]),
        "DB_PASSWORD": str(config.get("password", "")),
    }

    lines: list[str] = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    existing_keys = {line.split("=", 1)[0].strip() for line in lines if "=" in line}
    new_lines = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in existing_keys:
            new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # 重载环境变量并切换连接
    global DB_TYPE, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    DB_TYPE, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = (
        db_type, updates["DB_HOST"], updates["DB_PORT"], updates["DB_NAME"],
        updates["DB_USER"], updates["DB_PASSWORD"],
    )
    switch_database({
        "db_type": db_type,
        "host": updates["DB_HOST"],
        "port": int(updates["DB_PORT"]),
        "name": updates["DB_NAME"],
        "user": updates["DB_USER"],
        "password": updates["DB_PASSWORD"],
    })
    remember_database_profile(updates["DB_NAME"])


# =========================================================
# 数据源导入（CSV / SQLite / ZIP / URL / 文件夹）
# =========================================================

def _quote_ident_import(name: str) -> str:
    return f"`{name}`" if _current_config["db_type"] == "mysql" else f'"{name}"'


def infer_column_type(values: List[str]) -> str:
    cleaned = [v.strip() for v in values if str(v).strip() != ""]
    if not cleaned:
        return "TEXT"
    if all(_looks_like_int(v) for v in cleaned):
        return "INTEGER"
    if all(_looks_like_decimal(v) for v in cleaned):
        return "NUMERIC"
    if all(_looks_like_date(v) for v in cleaned):
        return "DATE"
    return "TEXT"


def _looks_like_int(value: str) -> bool:
    try:
        return Decimal(value.strip()) == Decimal(value.strip()).to_integral_value()
    except (InvalidOperation, ValueError):
        return False


def _looks_like_decimal(value: str) -> bool:
    try:
        Decimal(value.strip())
        return True
    except (InvalidOperation, ValueError):
        return False


def _looks_like_date(value: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()))


def infer_primary_key(columns: List[Dict[str, Any]]) -> str | None:
    """Infer a primary key only when a conventional identifier is unique."""
    ranked_columns = sorted(
        columns,
        key=lambda col: (
            0 if str(col["name"]).strip().lower() == "id" else
            1 if str(col["name"]).strip().lower().endswith("_id") else
            2 if str(col["name"]).strip() in {"编号", "序号", "主键"} else 3,
        ),
    )
    for column in ranked_columns:
        name = str(column["name"]).strip()
        normalized = name.lower()
        is_identifier = normalized == "id" or normalized.endswith("_id") or name in {"编号", "序号", "主键"}
        values = [str(value).strip() for value in column.get("values", [])]
        if is_identifier and values and all(values) and len(set(values)) == len(values):
            return re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_") or None
    return None


def build_create_table_sql(table_name: str, columns: List[Dict[str, Any]], primary_key: str | None = None) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", table_name).strip("_") or "imported_table"
    primary_key = primary_key or infer_primary_key(columns)
    lines = [f'CREATE TABLE IF NOT EXISTS {_quote_ident_import(safe_name)} (']
    column_defs = []
    for col in columns:
        name = re.sub(r"[^a-zA-Z0-9_]+", "_", col["name"]).strip("_") or "column"
        col_type = infer_column_type(col.get("values", []))
        if primary_key and name == re.sub(r"[^a-zA-Z0-9_]+", "_", primary_key).strip("_"):
            column_defs.append(f'{_quote_ident_import(name)} {col_type} PRIMARY KEY')
        else:
            column_defs.append(f'{_quote_ident_import(name)} {col_type}')
    lines.append(",\n    ".join(column_defs))
    lines.append(")")
    return "\n".join(lines)


def build_insert_sql(table_name: str, column_names: List[str]):
    safe_table_name = re.sub(r"[^a-zA-Z0-9_]+", "_", table_name).strip("_") or "imported_table"
    safe_columns = [re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_") or "column" for name in column_names]
    placeholders = ", ".join([":p" + str(i) for i in range(len(safe_columns))])
    columns_sql = ", ".join([_quote_ident_import(name) for name in safe_columns])
    if _current_config["db_type"] == "mysql":
        # MySQL 不支持 ON CONFLICT，使用 INSERT IGNORE 实现幂等导入
        return text(f'INSERT IGNORE INTO {_quote_ident_import(safe_table_name)} ({columns_sql}) VALUES ({placeholders})')
    return text(f'INSERT INTO {_quote_ident_import(safe_table_name)} ({columns_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING')


def import_csv_to_db(file_path: str, table_name: str, primary_key: str | None = None) -> Dict[str, Any]:
    # UTF-8 is the normal browser-upload encoding; GBK is common in exported
    # Chinese database documents.  Do not silently mangle either.
    last_error: UnicodeDecodeError | None = None
    rows = []
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with open(file_path, "r", encoding=encoding, newline="") as f:
                rows = list(csv.DictReader(f))
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError("CSV 编码不受支持，请使用 UTF-8 或 GB18030") from last_error

    if not rows:
        raise ValueError("CSV 文件为空")

    columns = []
    for key in rows[0].keys():
        values = [row.get(key, "") for row in rows]
        columns.append({"name": key, "values": values})

    create_sql = build_create_table_sql(table_name, columns, primary_key=primary_key)
    safe_table_name = re.sub(r"[^a-zA-Z0-9_]+", "_", table_name).strip("_") or "imported_table"
    inserted_rows = 0
    with engine.begin() as conn:
        conn.execute(text(create_sql))
        for row in rows:
            field_names = [re.sub(r"[^a-zA-Z0-9_]+", "_", key).strip("_") or "column" for key in row.keys()]
            sql = build_insert_sql(safe_table_name, field_names)
            params = {f"p{i}": row.get(list(row.keys())[i], "") for i in range(len(field_names))}
            inserted_rows += max(conn.execute(sql, params).rowcount or 0, 0)

    return {
        "table_name": table_name,
        "row_count": len(rows),
        "inserted_rows": inserted_rows,
        "skipped_rows": len(rows) - inserted_rows,
        "columns": [col["name"] for col in columns],
    }


def import_database_source(source: str, target_table_name: str | None = None, primary_key: str | None = None) -> Dict[str, Any]:
    if source.startswith(("http://", "https://")):
        with tempfile.TemporaryDirectory() as tmp_dir:
            downloaded_path = os.path.join(tmp_dir, os.path.basename(source.split("?")[0]) or "downloaded.db")
            urllib.request.urlretrieve(source, downloaded_path)
            return import_database_file(downloaded_path, target_table_name=target_table_name, primary_key=primary_key)

    if os.path.isdir(source):
        return import_folder(source, target_table_name=target_table_name, primary_key=primary_key)

    if os.path.isfile(source):
        if Path(source).suffix.lower() == ".zip":
            return import_zip_archive(source, target_table_name=target_table_name, primary_key=primary_key)
        return import_database_file(source, target_table_name=target_table_name, primary_key=primary_key)

    raise ValueError("暂不支持该数据源")


def collect_import_candidate_files(folder_path: str) -> List[str]:
    candidates: List[str] = []
    for root, _, files in os.walk(folder_path):
        for name in files:
            lower_name = name.lower()
            if lower_name.endswith((".csv", ".sqlite", ".sqlite3", ".db", ".zip")):
                candidates.append(os.path.join(root, name))
            elif lower_name.endswith((".md", ".markdown", ".txt", ".json", ".yaml", ".yml")):
                continue

    candidates.sort(key=lambda p: (0 if os.path.splitext(p)[1].lower() in {".csv"} else 1, os.path.basename(p).lower()))
    return candidates


def import_folder(folder_path: str, target_table_name: str | None = None, primary_key: str | None = None) -> Dict[str, Any]:
    supported_files = collect_import_candidate_files(folder_path)

    if not supported_files:
        raise ValueError("文件夹中没有找到可导入的 CSV/SQLite/ZIP 文件")

    effective_table_name = target_table_name if len(supported_files) == 1 else None
    imported = []
    for path in supported_files:
        if path.lower().endswith(".zip"):
            imported.append(import_zip_archive(path, target_table_name=effective_table_name, primary_key=primary_key))
        else:
            imported.append(import_database_file(path, target_table_name=effective_table_name, primary_key=primary_key))

    return {"mode": "folder", "files": imported}


def import_zip_archive(zip_path: str, target_table_name: str | None = None, primary_key: str | None = None) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # ZIP filenames are untrusted: reject path traversal and avoid
            # extracting directory entries as files.
            destination = Path(tmp_dir).resolve()
            for member in zf.infolist():
                member_path = (destination / member.filename).resolve()
                if not member_path.is_relative_to(destination):
                    raise ValueError("ZIP 包含不安全的文件路径")
                if member.is_dir():
                    member_path.mkdir(parents=True, exist_ok=True)
                    continue
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as source, open(member_path, "wb") as target:
                    shutil.copyfileobj(source, target)
        return import_folder(tmp_dir, target_table_name=target_table_name, primary_key=primary_key)


def import_database_file(file_path: str, target_table_name: str | None = None, primary_key: str | None = None) -> Dict[str, Any]:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".csv":
        table_name = target_table_name or path.stem
        return import_csv_to_db(str(path), table_name, primary_key=primary_key)

    if ext in {".sqlite", ".sqlite3", ".db"}:
        import sqlite3
        conn = sqlite3.connect(str(path))
        try:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            imported_tables = []
            for (table_name,) in tables:
                if table_name.startswith("sqlite_"):
                    continue
                query = conn.execute(f'SELECT * FROM "{table_name}"')
                rows = query.fetchall()
                columns = [desc[0] for desc in query.description or []]
                source_primary_keys = [column[1] for column in conn.execute(f'PRAGMA table_info("{table_name}")') if column[5]]
                detected_primary_key = source_primary_keys[0] if len(source_primary_keys) == 1 else primary_key
                if not rows:
                    create_sql = build_create_table_sql(
                        table_name,
                        [{"name": col, "values": []} for col in columns],
                        primary_key=detected_primary_key,
                    )
                    with engine.begin() as conn_pg:
                        conn_pg.execute(text(create_sql))
                    imported_tables.append({"table_name": table_name, "row_count": 0, "columns": columns})
                    continue
                create_sql = build_create_table_sql(table_name, [{"name": col, "values": [str(row[i]) for row in rows]} for i, col in enumerate(columns)], primary_key=detected_primary_key)
                safe_table_name = re.sub(r"[^a-zA-Z0-9_]+", "_", table_name).strip("_") or "imported_table"
                with engine.begin() as conn_pg:
                    conn_pg.execute(text(create_sql))
                    inserted_rows = 0
                    for row in rows:
                        sql = build_insert_sql(safe_table_name, columns)
                        params = {f"p{i}": row[i] for i in range(len(columns))}
                        inserted_rows += max(conn_pg.execute(sql, params).rowcount or 0, 0)
                imported_tables.append({
                    "table_name": table_name,
                    "row_count": len(rows),
                    "inserted_rows": inserted_rows,
                    "skipped_rows": len(rows) - inserted_rows,
                    "columns": columns,
                })
            return {"mode": "sqlite", "tables": imported_tables}
        finally:
            conn.close()

    raise ValueError("暂不支持的文件类型")
