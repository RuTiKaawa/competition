"""项目配置 — 从 .env 加载敏感信息，支持环境变量覆盖"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM 配置 (支持 OpenAI 兼容接口, 如 DeepSeek) ──
LLM_CONFIG = {
    "model":       os.getenv("LLM_MODEL", "deepseek-chat"),
    "api_key":     os.getenv("LLM_API_KEY", ""),
    "base_url":    os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
    "max_tokens":  int(os.getenv("LLM_MAX_TOKENS", "8192")),
}

# ── 服务配置 ──
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5173"))

# ── PostgreSQL 数据库配置 ──
DB_CONFIG = {
    "dbname":   os.getenv("DB_NAME", "postgres"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
}

# ── 前端静态文件路径 ──
UI_DIR = os.getenv("UI_DIR", os.path.join(os.path.dirname(__file__), "static"))
