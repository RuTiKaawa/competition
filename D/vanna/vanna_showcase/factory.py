"""Application factory for the Vanna capability homepage and rich chat UI."""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from vanna import Agent, AgentConfig
from vanna.capabilities.sql_runner import RunSqlToolArgs, SqlRunner
from vanna.core.agent.config import AuditConfig
from vanna.core.enhancer import LlmContextEnhancer
from vanna.core.llm import LlmRequest
from vanna.core.registry import ToolRegistry
from vanna.core.system_prompt import DefaultSystemPromptBuilder
from vanna.core.tool import ToolContext
from vanna.core.user import RequestContext, User, UserResolver
from vanna.integrations.local import LocalFileSystem
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.integrations.openai import OpenAILlmService
from vanna.servers.fastapi import VannaFastAPIServer
from vanna.tools import RunSqlTool, VisualizeDataTool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE_PATH = Path(__file__).with_name("homepage.html")
CHATPAGE_PATH = Path(__file__).with_name("chatpage.html")
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

SYSTEM_PROMPT = """You are the Vanna data assistant for the read-only Chinook SQLite sample database.
Always answer in the same language as the user and base every data claim on an actual tool result.

Tool workflow:
- Use run_sql for database questions. SQL must be a single read-only SQLite SELECT statement and must start with SELECT.
- To inspect the schema, query sqlite_master with SELECT name, sql FROM sqlite_master WHERE type = 'table'.
- When the user explicitly asks for a chart, graph, plot, or visualization, first call run_sql, then call visualize_data with the exact CSV filename returned by run_sql. Do not finish the response before the visualization tool succeeds.
- Query results and rich components are already shown in the interface; finish with a concise interpretation instead of repeating the whole table.

Useful Chinook relationships:
- Customer.CustomerId = Invoice.CustomerId
- Invoice.InvoiceId = InvoiceLine.InvoiceId
- InvoiceLine.TrackId = Track.TrackId
- Track.AlbumId = Album.AlbumId; Album.ArtistId = Artist.ArtistId
- Invoice.BillingCountry contains the sales country and Invoice.Total contains the invoice total.

Never invent rows, totals, filenames, or tool results. If a query fails, correct the SQL and retry."""


def _resolve_project_path(raw_value: str | None, default: Path) -> Path:
    if not raw_value or not raw_value.strip():
        return default.resolve()

    candidate = Path(raw_value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _read_only_sqlite_uri(database_path: Path) -> str:
    return f"{database_path.resolve().as_uri()}?mode=ro"


@dataclass(frozen=True, slots=True)
class ShowcaseSettings:
    """Runtime settings kept separate from the Vanna package internals."""

    database_path: Path = PROJECT_ROOT / "Chinook.sqlite"
    working_directory: Path = PROJECT_ROOT / ".vanna_data"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    @classmethod
    def from_environment(cls) -> ShowcaseSettings:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        return cls(
            database_path=_resolve_project_path(
                os.getenv("VANNA_CHINOOK_PATH"), PROJECT_ROOT / "Chinook.sqlite"
            ),
            working_directory=_resolve_project_path(
                os.getenv("VANNA_WORKING_DIRECTORY"), PROJECT_ROOT / ".vanna_data"
            ),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_base_url=os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).rstrip("/"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        )

    def validate(self) -> None:
        if not self.deepseek_api_key.strip():
            raise RuntimeError(
                "DEEPSEEK_API_KEY is required. Add it to /home/rutika/vanna/.env "
                "before starting the showcase."
            )
        if not self.deepseek_base_url.strip():
            raise RuntimeError("DEEPSEEK_BASE_URL must not be empty.")
        if not self.deepseek_model.strip():
            raise RuntimeError("DEEPSEEK_MODEL must not be empty.")
        validate_chinook_database(self.database_path)


def validate_chinook_database(database_path: Path) -> None:
    """Reject missing, empty, corrupt, or non-Chinook files without creating one."""

    if not database_path.is_file():
        raise FileNotFoundError(
            f"Chinook database not found at {database_path}. Download it from "
            "https://vanna.ai/Chinook.sqlite before starting the app."
        )
    if database_path.stat().st_size == 0:
        raise RuntimeError(f"Chinook database is empty: {database_path}")

    with database_path.open("rb") as database_file:
        if database_file.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise RuntimeError(
                f"Chinook database has an invalid SQLite header: {database_path}"
            )

    try:
        with sqlite3.connect(
            _read_only_sqlite_uri(database_path), uri=True, timeout=5
        ) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if not quick_check or quick_check[0] != "ok":
                raise RuntimeError(
                    f"Chinook database integrity check failed: {quick_check!r}"
                )
            actual_tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
    except sqlite3.Error as exc:
        raise RuntimeError(f"Unable to read Chinook database: {exc}") from exc

    missing_tables = EXPECTED_CHINOOK_TABLES - actual_tables
    if missing_tables:
        missing = ", ".join(sorted(missing_tables))
        raise RuntimeError(
            f"Database is not the expected Chinook sample; missing: {missing}"
        )


class ReadOnlySqliteRunner(SqlRunner):
    """SQLite runner that enforces SELECT-only access and opens the file read-only."""

    def __init__(self, database_path: Path):
        self.database_path = database_path

    async def run_sql(self, args: RunSqlToolArgs, context: ToolContext) -> pd.DataFrame:
        del context
        sql = args.sql.strip()
        if not sql or sql.split(None, 1)[0].upper() != "SELECT":
            raise PermissionError(
                "The Chinook demo accepts read-only SELECT queries only."
            )

        with sqlite3.connect(
            _read_only_sqlite_uri(self.database_path), uri=True, timeout=10
        ) as connection:
            connection.execute("PRAGMA query_only = ON")
            cursor = connection.execute(sql)
            columns = [description[0] for description in cursor.description or ()]
            rows = cursor.fetchall()

        return pd.DataFrame.from_records(rows, columns=columns)


class DeepSeekLlmService(OpenAILlmService):
    """OpenAI-compatible DeepSeek client with reliable multi-step tool calls."""

    def _build_payload(self, request: LlmRequest) -> dict[str, Any]:
        payload = super()._build_payload(request)
        # Vanna 2.0.2 does not round-trip DeepSeek's reasoning_content field.
        # Non-thinking mode keeps multi-turn SQL -> visualization tool calls valid.
        payload["extra_body"] = {"thinking": {"type": "disabled"}}
        return payload


class LocalDemoUserResolver(UserResolver):
    """Resolve every local request to the explicitly documented demo identity."""

    async def resolve_user(self, request_context: RequestContext) -> User:
        del request_context
        return User(
            id="local-demo",
            username="local-demo",
            email="local-demo@localhost",
            group_memberships=["user", "admin"],
        )


def build_agent(settings: ShowcaseSettings) -> Agent:
    """Build the DeepSeek + Chinook agent without modifying Vanna internals."""

    shared_file_system = LocalFileSystem(
        working_directory=str(settings.working_directory)
    )
    tools = ToolRegistry()
    tools.register_local_tool(
        RunSqlTool(
            sql_runner=ReadOnlySqliteRunner(settings.database_path),
            file_system=shared_file_system,
            custom_tool_description=(
                "Run one read-only SELECT query against the Chinook SQLite music-store "
                "database. Query sqlite_master with SELECT when schema details are needed."
            ),
        ),
        access_groups=["user", "admin"],
    )
    tools.register_local_tool(
        VisualizeDataTool(file_system=shared_file_system),
        access_groups=["user", "admin"],
    )

    llm_service = DeepSeekLlmService(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    inactive_demo_memory = DemoAgentMemory(max_items=256)

    return Agent(
        llm_service=llm_service,
        tool_registry=tools,
        user_resolver=LocalDemoUserResolver(),
        agent_memory=inactive_demo_memory,
        config=AgentConfig(
            max_tool_iterations=10,
            stream_responses=True,
            include_thinking_indicators=False,
            audit_config=AuditConfig(enabled=False),
        ),
        system_prompt_builder=DefaultSystemPromptBuilder(base_prompt=SYSTEM_PROMPT),
        llm_context_enhancer=LlmContextEnhancer(),
    )


def build_vanna_app(agent: Agent) -> FastAPI:
    """Create the official Vanna child application for the /chat mount."""

    server = VannaFastAPIServer(
        agent,
        config={
            "api_base_url": "/chat",
            "cors": {"enabled": False},
            "fastapi": {
                "docs_url": None,
                "redoc_url": None,
                "openapi_url": None,
            },
        },
    )
    return server.create_app()


def create_app(settings: ShowcaseSettings | None = None) -> FastAPI:
    """Create the outer FastAPI app and mount Vanna under ``/chat``."""

    resolved_settings = settings or ShowcaseSettings.from_environment()
    resolved_settings.validate()
    agent = build_agent(resolved_settings)
    chat_app = build_vanna_app(agent)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        resolved_settings.working_directory.mkdir(parents=True, exist_ok=True)
        yield

    application = FastAPI(
        title="Vanna Data Assistant Showcase",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.vanna_agent = agent
    application.state.vanna_chat_app = chat_app

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def homepage() -> HTMLResponse:
        return HTMLResponse(
            HOMEPAGE_PATH.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/chat/", response_class=HTMLResponse, include_in_schema=False)
    async def chatpage() -> HTMLResponse:
        return HTMLResponse(
            CHATPAGE_PATH.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": "vanna-showcase",
            "chat": "/chat/",
        }

    application.mount("/chat", chat_app, name="vanna-chat")
    return application
