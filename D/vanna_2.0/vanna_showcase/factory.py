"""Application factory for the Vanna capability homepage and rich chat UI."""

from __future__ import annotations

import inspect
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from vanna import Agent, AgentConfig
from vanna.core.agent.config import AuditConfig
from vanna.core.enhancer import LlmContextEnhancer
from vanna.core.registry import ToolRegistry
from vanna.core.system_prompt import DefaultSystemPromptBuilder
from vanna.core.user import RequestContext, User, UserResolver
from vanna.integrations.local import LocalFileSystem
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.servers.fastapi import VannaFastAPIServer
from vanna.tools import RunSqlTool, VisualizeDataTool

from .credentials import (
    CredentialStore,
    DeepSeekLlmService,
    UserRoutedDeepSeekService,
    validate_deepseek_key,
)
from .data_sources import (
    EXPECTED_CHINOOK_TABLES,
    MAX_UPLOAD_BYTES,
    DataSourceManager,
    MultiSourceSqlRunner,
    validate_chinook_database,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE_PATH = Path(__file__).with_name("homepage.html")
CHATPAGE_PATH = Path(__file__).with_name("chatpage.html")
SETTINGS_PATH = Path(__file__).with_name("data_sources.html")
DEMO_USER_ID = "local-demo"

SYSTEM_PROMPT = """You are the Vanna data assistant for the currently selected read-only data source.
Always answer in the same language as the user and base every data claim on an actual tool result.

Tool workflow:
- Use run_sql for database questions. SQL must be a single read-only SELECT statement and must start with SELECT.
- If the table names or columns are not known, inspect the schema first. For SQLite use sqlite_master; for DuckDB use information_schema.tables and information_schema.columns.
- When the user explicitly asks for a chart, graph, plot, or visualization, first call run_sql, then call visualize_data with the exact CSV filename returned by run_sql. Do not finish the response before the visualization tool succeeds.
- Query results and rich components are already shown in the interface; finish with a concise interpretation instead of repeating the whole table.

Useful relationships for the bundled Chinook sample:
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
        if not self.deepseek_base_url.strip():
            raise RuntimeError("DEEPSEEK_BASE_URL must not be empty.")
        if not self.deepseek_model.strip():
            raise RuntimeError("DEEPSEEK_MODEL must not be empty.")


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


def build_agent(
    settings: ShowcaseSettings,
    data_sources: DataSourceManager | None = None,
    credentials: CredentialStore | None = None,
) -> Agent:
    """Build the DeepSeek agent with a conversation-routed SQL data source."""

    shared_file_system = LocalFileSystem(
        working_directory=str(settings.working_directory)
    )
    tools = ToolRegistry()
    manager = data_sources or DataSourceManager(
        settings.working_directory, settings.database_path
    )
    credential_store = credentials or CredentialStore(
        settings.working_directory,
        environment_api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    tools.register_local_tool(
        RunSqlTool(
            sql_runner=MultiSourceSqlRunner(manager),
            file_system=shared_file_system,
            custom_tool_description=(
                "Run one read-only SELECT query against the currently selected data source. "
                "Inspect the selected database schema first when needed."
            ),
        ),
        access_groups=["user", "admin"],
    )
    tools.register_local_tool(
        VisualizeDataTool(file_system=shared_file_system),
        access_groups=["user", "admin"],
    )

    llm_service = UserRoutedDeepSeekService(credential_store)
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
    data_sources = DataSourceManager(
        resolved_settings.working_directory, resolved_settings.database_path
    )
    credentials = CredentialStore(
        resolved_settings.working_directory,
        environment_api_key=resolved_settings.deepseek_api_key,
        base_url=resolved_settings.deepseek_base_url,
        model=resolved_settings.deepseek_model,
    )
    agent = build_agent(resolved_settings, data_sources, credentials)
    chat_app = build_vanna_app(agent)

    async def credential_validator(api_key: str) -> None:
        await validate_deepseek_key(
            api_key,
            base_url=resolved_settings.deepseek_base_url,
            model=resolved_settings.deepseek_model,
            user_id=DEMO_USER_ID,
        )

    def readiness() -> dict:
        llm_status = credentials.public_status(DEMO_USER_ID)
        source_count = data_sources.ready_source_count()
        actions = []
        if not llm_status["configured"]:
            actions.append(
                {
                    "id": "configure_llm",
                    "label": "配置 DeepSeek API Key",
                    "href": "/settings#model-api",
                }
            )
        if source_count == 0:
            actions.append(
                {
                    "id": "add_data_source",
                    "label": "添加数据源",
                    "href": "/settings#data-sources",
                }
            )
        return {
            "chat_ready": bool(llm_status["configured"] and source_count),
            "llm": llm_status,
            "data_sources": {
                "configured": source_count > 0,
                "ready_count": source_count,
                "chinook_error": data_sources.chinook_error,
            },
            "actions": actions,
        }

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
    application.state.data_sources = data_sources
    application.state.credentials = credentials
    application.state.credential_validator = credential_validator
    application.state.chinook_installer = data_sources.install_chinook
    application.state.readiness = readiness

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
    async def health() -> dict:
        current = readiness()
        return {
            "status": "healthy",
            "service": "vanna-showcase",
            "chat": "/chat/",
            "chat_ready": current["chat_ready"],
        }

    @application.get("/settings", response_class=HTMLResponse, include_in_schema=False)
    async def settings_page() -> HTMLResponse:
        return HTMLResponse(
            SETTINGS_PATH.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store"},
        )

    @application.get("/data-sources", include_in_schema=False)
    async def legacy_data_sources_page() -> RedirectResponse:
        return RedirectResponse(url="/settings#data-sources", status_code=307)

    @application.get("/api/readiness")
    async def get_readiness() -> dict:
        return readiness()

    @application.get("/api/settings/llm")
    async def get_llm_settings() -> dict:
        return credentials.public_status(DEMO_USER_ID)

    @application.put("/api/settings/llm")
    async def save_llm_settings(request: Request) -> dict:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Request body must be JSON"
            ) from exc
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400, detail="Request body must be an object"
            )
        api_key = str(body.get("api_key", "")).strip()
        if not api_key:
            raise HTTPException(status_code=422, detail="api_key is required")
        try:
            await application.state.credential_validator(api_key)
        except Exception as exc:
            safe_detail = str(exc).replace(api_key, "[REDACTED]")
            raise HTTPException(
                status_code=400,
                detail=f"DeepSeek API Key validation failed: {safe_detail}",
            ) from exc
        credentials.save_personal_key(DEMO_USER_ID, api_key)
        agent.llm_service.invalidate_user(DEMO_USER_ID)
        return credentials.public_status(DEMO_USER_ID)

    @application.delete("/api/settings/llm")
    async def delete_llm_settings() -> dict:
        deleted = credentials.delete_personal_key(DEMO_USER_ID)
        agent.llm_service.invalidate_user(DEMO_USER_ID)
        return {
            "deleted": deleted,
            "llm": credentials.public_status(DEMO_USER_ID),
        }

    @application.post("/api/sample-data/chinook")
    async def install_chinook() -> dict:
        try:
            install_result = application.state.chinook_installer()
            source = (
                await install_result
                if inspect.isawaitable(install_result)
                else install_result
            )
            return {
                "installed": True,
                "source": data_sources.public_source(source),
            }
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Unable to download Chinook from the official source: {exc}",
            ) from exc

    @application.get("/api/data-sources")
    async def list_data_sources(request: Request) -> list[dict]:
        role = request.headers.get("x-demo-role", "admin")
        return [
            data_sources.public_source(item)
            for item in data_sources.list_sources((role,))
        ]

    @application.post("/api/data-sources/import")
    async def import_data_source(
        request: Request,
        source_name: str = Form(...),
        files: list[UploadFile] = File(...),
    ) -> dict:
        role = request.headers.get("x-demo-role", "admin")
        if role != "admin":
            raise HTTPException(
                status_code=403, detail="Only admin can import data sources"
            )
        try:
            payloads = []
            total_size = 0
            for upload in files:
                filename = upload.filename or "upload.csv"
                payload = bytearray()
                while chunk := await upload.read(1024 * 1024):
                    total_size += len(chunk)
                    if total_size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="The total upload size must not exceed 100 MB",
                        )
                    payload.extend(chunk)
                payloads.append((filename, bytes(payload)))
            imported = data_sources.import_files(source_name, payloads)
            return data_sources.public_source(imported)
        except HTTPException:
            raise
        except (ValueError, ImportError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Import failed: {exc}"
            ) from exc
        finally:
            for upload in files:
                await upload.close()

    @application.get("/api/data-sources/{source_id}/schema")
    async def data_source_schema(source_id: str, request: Request) -> dict:
        role = request.headers.get("x-demo-role", "user")
        try:
            data_sources.require_source(source_id, (role,))
            return {"source_id": source_id, "schema": data_sources.schema(source_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @application.delete("/api/data-sources/{source_id}")
    async def delete_data_source(source_id: str, request: Request) -> dict:
        role = request.headers.get("x-demo-role", "admin")
        if role != "admin":
            raise HTTPException(
                status_code=403, detail="Only admin can delete data sources"
            )
        try:
            deleted = data_sources.delete_source(source_id)
            database_deleted = not Path(deleted["database_path"]).exists()
            fallback = data_sources.source_for_conversation("")
            return {
                "deleted": True,
                "physical_deleted": database_deleted,
                "database_deleted": database_deleted,
                "dataset_directory_deleted": not Path(
                    deleted["database_path"]
                ).parent.exists(),
                "source": data_sources.public_source(deleted),
                "conversation_fallback": data_sources.public_source(fallback),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @application.post("/api/conversations/{conversation_id}/data-source")
    async def set_conversation_data_source(
        conversation_id: str, request: Request
    ) -> dict:
        body = await request.json()
        source_id = body.get("data_source_id")
        role = request.headers.get("x-demo-role", "user")
        if not source_id:
            raise HTTPException(status_code=422, detail="data_source_id is required")
        try:
            source = data_sources.require_source(source_id, (role,))
            data_sources.set_conversation_source(conversation_id, source_id)
            return {
                "conversation_id": conversation_id,
                "data_source": data_sources.public_source(source),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/conversations/{conversation_id}/data-source")
    async def get_conversation_data_source(conversation_id: str) -> dict:
        source = data_sources.source_for_conversation(conversation_id)
        return {
            "conversation_id": conversation_id,
            "data_source": data_sources.public_source(source),
        }

    application.mount("/chat", chat_app, name="vanna-chat")
    return application
