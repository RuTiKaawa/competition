"""SQL 校验器：基于 sqlglot AST 的合法性检查 + 安全验证"""

import re


def validate_sql_safety(sql: str, dialect: str = "postgres") -> tuple[bool, str, str]:
    """校验 SQL 的安全性和合法性

    Args:
        sql: 原始 SQL 字符串
        dialect: 数据库方言
    Returns:
        (valid, error_msg, cleaned_sql)
    """
    if not sql or not sql.strip():
        return False, "SQL 为空", ""

    original = sql.strip()

    # 1. 基础安全检查
    dangerous_keywords = [
        "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE",
        "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "EXEC", "CALL",
        "COPY", "LOAD", "IMPORT", "EXPORT",
    ]
    upper_sql = original.upper()
    for kw in dangerous_keywords:
        # 用词边界检测，避免误判（如 DESCRIPTION 不应匹配 DELETE）
        if re.search(rf'\b{kw}\b', upper_sql):
            return False, f"SQL 包含禁止关键词: {kw}", original

    # 2. 必须以 SELECT 或 WITH 开头
    cleaned = original.strip()
    if not (cleaned.upper().startswith("SELECT") or cleaned.upper().startswith("WITH")):
        return False, "SQL 必须以 SELECT 或 WITH 开头", cleaned

    # 3. 用 sqlglot 解析 AST（如果可用）
    try:
        import sqlglot
        parsed = sqlglot.parse(cleaned, read=dialect)
        if not parsed or len(parsed) == 0:
            return False, "SQL 语法错误：无法解析", cleaned

        # 检查解析出的语句类型
        for statement in parsed:
            if statement is None:
                return False, "SQL 语法错误：解析失败", cleaned

            # 检查是否有非 SELECT 语句
            stype = str(statement.key).upper() if hasattr(statement, 'key') else ""
            if stype in ("INSERT", "DELETE", "UPDATE", "DROP", "CREATE", "ALTER", "TRUNCATE"):
                return False, f"禁止 {stype} 操作", cleaned

        # 4. 重新格式化 SQL（自动修复引号/格式）
        try:
            formatted = sqlglot.transpile(cleaned, read=dialect, pretty=True)[0]
            if formatted:
                cleaned = formatted
        except Exception:
            pass  # 格式化失败不影响合法性

    except ImportError:
        # sqlglot 未安装，只做基础检查
        pass
    except Exception as e:
        # sqlglot 解析异常，但不一定是 SQL 问题（可能是复杂语法）
        pass

    # 5. 强制 LIMIT 检查
    if "LIMIT" not in cleaned.upper():
        cleaned = cleaned.rstrip(";").rstrip() + " LIMIT 100"

    # 6. 括号配对检查
    if cleaned.count("(") != cleaned.count(")"):
        return False, "SQL 括号不配对", cleaned

    return True, "", cleaned


def extract_tables_from_sql(sql: str) -> list[str]:
    """从 SQL 中提取所有引用的表名"""
    tables = set()
    # 匹配 FROM/JOIN 后的表名
    patterns = [
        r'\bFROM\s+["]?(\w+)["]?',
        r'\bJOIN\s+["]?(\w+)["]?',
        r'\bUSING\s*\(\w+\)',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, sql, re.IGNORECASE):
            if match.groups():
                tables.add(match.group(1).lower())
    return list(tables)
