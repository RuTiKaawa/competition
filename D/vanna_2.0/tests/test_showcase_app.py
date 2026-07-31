"""Acceptance tests for the standalone Vanna showcase application."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest

from vanna.components import ChartComponent, DataFrameComponent
from vanna.core.llm import LlmMessage, LlmRequest
from vanna.core.tool import ToolCall, ToolContext
from vanna.core.user import User
from vanna_showcase.factory import (
    EXPECTED_CHINOOK_TABLES,
    DeepSeekLlmService,
    ShowcaseSettings,
    build_agent,
    create_app,
)


def _create_minimal_chinook(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        for table in sorted(EXPECTED_CHINOOK_TABLES - {"Invoice"}):
            connection.execute(f'CREATE TABLE "{table}" (Id INTEGER PRIMARY KEY)')
        connection.execute(
            """
            CREATE TABLE Invoice (
                InvoiceId INTEGER PRIMARY KEY,
                BillingCountry TEXT NOT NULL,
                Total REAL NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO Invoice (InvoiceId, BillingCountry, Total) VALUES (?, ?, ?)",
            [(1, "Brazil", 10.5), (2, "Brazil", 7.5), (3, "Canada", 12.0)],
        )


@pytest.fixture
def showcase_settings(tmp_path: Path) -> ShowcaseSettings:
    database_path = tmp_path / "Chinook.sqlite"
    _create_minimal_chinook(database_path)
    return ShowcaseSettings(
        database_path=database_path,
        working_directory=tmp_path / "tool-files",
        deepseek_api_key="test-secret-must-not-leak",
    )


@pytest.mark.asyncio
async def test_homepage_settings_health_and_chat_routes(
    showcase_settings: ShowcaseSettings,
) -> None:
    application = create_app(showcase_settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        homepage = await client.get("/")
        assert homepage.status_code == 200
        assert "Vanna Web Component" in homepage.text
        assert "配置模型与数据源" in homepage.text
        assert showcase_settings.deepseek_api_key not in homepage.text

        health = await client.get("/health")
        assert health.json() == {
            "status": "healthy",
            "service": "vanna-showcase",
            "chat": "/chat/",
            "chat_ready": True,
        }

        settings_page = await client.get("/settings")
        assert settings_page.status_code == 200
        assert 'id="model-api"' in settings_page.text
        assert 'id="data-sources"' in settings_page.text
        assert "后续接入（未完成）" in settings_page.text
        assert showcase_settings.deepseek_api_key not in settings_page.text

        legacy = await client.get("/data-sources", follow_redirects=False)
        assert legacy.status_code == 307
        assert legacy.headers["location"] == "/settings#data-sources"

        chat = await client.get("/chat/")
        assert chat.status_code == 200
        assert "createElement('vanna-chat')" in chat.text
        assert "nativeFetch('/api/readiness')" in chat.text
        assert "setAttribute('api-base', '/chat')" in chat.text
        assert "setAttribute('sse-endpoint', '/api/vanna/v2/chat_sse')" in chat.text
        assert "<vanna-chat" not in chat.text
        assert showcase_settings.deepseek_api_key not in chat.text

        child_health = await client.get("/chat/health")
        assert child_health.json() == {"status": "healthy", "service": "vanna"}
        assert (
            await client.post("/chat/api/vanna/v2/chat_sse", json={})
        ).status_code == 422
        assert (
            await client.post("/chat/api/vanna/v2/chat_poll", json={})
        ).status_code == 422


@pytest.mark.asyncio
async def test_missing_database_and_api_key_start_in_setup_mode(tmp_path: Path) -> None:
    missing_path = tmp_path / "not-present.sqlite"
    application = create_app(
        ShowcaseSettings(
            database_path=missing_path,
            working_directory=tmp_path / "work",
            deepseek_api_key="",
        )
    )
    assert not missing_path.exists()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        health = await client.get("/health")
        readiness = await client.get("/api/readiness")
        chat = await client.get("/chat/")

    assert health.status_code == 200
    assert health.json()["chat_ready"] is False
    assert readiness.json()["llm"]["configured"] is False
    assert readiness.json()["data_sources"]["ready_count"] == 0
    assert {item["id"] for item in readiness.json()["actions"]} == {
        "configure_llm",
        "add_data_source",
    }
    assert "showSetup(readiness)" in chat.text


@pytest.mark.asyncio
async def test_invalid_optional_chinook_does_not_block_startup(tmp_path: Path) -> None:
    invalid = tmp_path / "Chinook.sqlite"
    invalid.write_bytes(b"not sqlite")
    application = create_app(
        ShowcaseSettings(
            database_path=invalid,
            working_directory=tmp_path / "work",
            deepseek_api_key="configured",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        state = (await client.get("/api/readiness")).json()

    assert state["chat_ready"] is False
    assert state["llm"]["configured"] is True
    assert state["data_sources"]["ready_count"] == 0
    assert "Invalid SQLite header" in state["data_sources"]["chinook_error"]
    assert invalid.read_bytes() == b"not sqlite"


def test_deepseek_payload_disables_thinking_for_tool_round_trips() -> None:
    service = DeepSeekLlmService(
        api_key="test-secret",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )
    payload = service._build_payload(
        LlmRequest(
            messages=[LlmMessage(role="user", content="列出所有表")],
            user=User(id="local-demo"),
        )
    )

    assert payload["model"] == "deepseek-v4-flash"
    assert payload["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "test-secret" not in str(payload)


@pytest.mark.asyncio
async def test_sql_table_csv_and_plotly_chain_share_one_file_system(
    showcase_settings: ShowcaseSettings,
) -> None:
    agent = build_agent(showcase_settings)
    context = ToolContext(
        user=User(id="local-demo", group_memberships=["user", "admin"]),
        conversation_id="acceptance",
        request_id="request-1",
        agent_memory=agent.agent_memory,
    )
    sql_result = await agent.tool_registry.execute(
        ToolCall(
            id="sql-1",
            name="run_sql",
            arguments={
                "sql": (
                    "SELECT BillingCountry AS country, SUM(Total) AS sales "
                    "FROM Invoice GROUP BY BillingCountry ORDER BY sales DESC"
                )
            },
        ),
        context,
    )

    assert sql_result.success is True
    assert sql_result.metadata["row_count"] == 2
    assert isinstance(sql_result.ui_component.rich_component, DataFrameComponent)
    filename = sql_result.metadata["output_file"]
    assert list(showcase_settings.working_directory.rglob(filename))

    chart_result = await agent.tool_registry.execute(
        ToolCall(
            id="chart-1",
            name="visualize_data",
            arguments={"filename": filename, "title": "Sales by country"},
        ),
        context,
    )
    assert chart_result.success is True
    assert isinstance(chart_result.ui_component.rich_component, ChartComponent)
    assert chart_result.ui_component.rich_component.chart_type == "plotly"
    assert chart_result.metadata["rows"] == 2


@pytest.mark.asyncio
async def test_sql_tool_rejects_mutation(showcase_settings: ShowcaseSettings) -> None:
    agent = build_agent(showcase_settings)
    context = ToolContext(
        user=User(id="local-demo", group_memberships=["user"]),
        conversation_id="read-only",
        request_id="request-2",
        agent_memory=agent.agent_memory,
    )
    result = await agent.tool_registry.execute(
        ToolCall(
            id="sql-delete",
            name="run_sql",
            arguments={"sql": "DELETE FROM Invoice"},
        ),
        context,
    )

    assert result.success is False
    assert "read-only SELECT" in result.error
    with sqlite3.connect(showcase_settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM Invoice").fetchone()[0] == 3
