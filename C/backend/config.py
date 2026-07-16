import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mes_user:mes_pass@localhost:5432/mes_db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "mes_db")
DB_USER = os.getenv("DB_USER", "mes_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "mes_pass")
SQL_QUERY_TIMEOUT = 5
MAX_RETURN_ROWS = 200
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "*"]
