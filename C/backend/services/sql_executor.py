import logging

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DML

from database import run_raw_query

logger = logging.getLogger(__name__)

FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "REPLACE",
    "MERGE", "CALL", "LOAD", "IMPORT", "COPY", "VACUUM",
}


def _get_statement_type(parsed: Statement) -> str | None:
    for token in parsed.tokens:
        if token.ttype in (DML, Keyword):
            return token.value.upper()
    return None


def validate_sql(sql: str) -> tuple[bool, str]:
    if not sql or not sql.strip():
        return False, "SQL statement is empty"

    sql_stripped = sql.strip()

    semicolon_count = sql_stripped.count(";")
    if semicolon_count > 1:
        return False, "Multiple statements are not allowed"
    if semicolon_count == 1 and not sql_stripped.endswith(";"):
        return False, "Semicolon is only allowed at the end of a single statement"

    clean_sql = sql_stripped.rstrip(";").strip()

    try:
        statements = sqlparse.parse(clean_sql)
    except Exception as e:
        return False, f"Failed to parse SQL: {str(e)}"

    if not statements:
        return False, "No valid SQL statement found"

    if len(statements) > 1:
        return False, "Multiple statements are not allowed"

    statement = statements[0]
    stmt_type = _get_statement_type(statement)

    if stmt_type is None:
        return False, "Could not determine statement type"

    if stmt_type not in ("SELECT",):
        return False, f"Statement type '{stmt_type}' is not allowed. Only SELECT queries are permitted"

    for token in statement.flatten():
        if token.ttype is Keyword and token.value.upper() in FORBIDDEN_KEYWORDS:
            return False, f"Forbidden keyword detected: {token.value}"

    return True, "OK"


def execute_query(sql: str) -> dict:
    is_valid, error_message = validate_sql(sql)
    if not is_valid:
        logger.warning(f"SQL validation failed: {error_message}")
        return {"error": error_message}

    try:
        rows = run_raw_query(sql)
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        return {"error": f"Query execution failed: {str(e)}"}

    if not rows:
        return {"columns": [], "rows": []}

    columns = list(rows[0].keys())
    data_rows = []
    for row in rows:
        converted_row = []
        for col in columns:
            val = row[col]
            converted_row.append(str(val) if val is not None else None)
        data_rows.append(converted_row)

    return {"columns": columns, "rows": data_rows}
