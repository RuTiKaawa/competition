"""Acceptance tests for the standalone Vanna showcase application."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
            [
                (1, "Brazil", 10.5),
                (2, "Brazil", 7.5),
                (3, "Canada", 12.0),
            ],
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


def test_homepage_health_and_official_chat_routes(
    showcase_settings: ShowcaseSettings,
) -> None:
    application = create_app(showcase_settings)

    with TestClient(application) as client:
        homepage = client.get("/")
        assert homepage.status_code == 200
        assert "Vanna Web Component" in homepage.text
        assert "DeepSeek V4 Flash" in homepage.text
        assert "可扩展" in homepage.text
        assert homepage.text.count('href="/chat/"') >= 3
        assert showcase_settings.deepseek_api_key not in homepage.text

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {
            "status": "healthy",
            "service": "vanna-showcase",
            "chat": "/chat/",
        }

        chat = client.get("/chat/")
        assert chat.status_code == 200
        assert "<vanna-chat" in chat.text
        assert 'api-base="/chat"' in chat.text
        assert 'sse-endpoint="/chat/api/vanna/v2/chat_sse"' in chat.text
        assert 'ws-endpoint="/chat/api/vanna/v2/chat_websocket"' in chat.text
        assert 'poll-endpoint="/chat/api/vanna/v2/chat_poll"' in chat.text
        assert 'sse-endpoint="/api/vanna/v2/chat_sse"' not in chat.text
        assert showcase_settings.deepseek_api_key not in chat.text

        child_health = client.get("/chat/health")
        assert child_health.status_code == 200
        assert child_health.json() == {"status": "healthy", "service": "vanna"}

        assert client.post("/chat/api/vanna/v2/chat_sse", json={}).status_code == 422
        assert client.post("/chat/api/vanna/v2/chat_poll", json={}).status_code == 422


def test_homepage_css_has_mobile_single_column_guards(
    showcase_settings: ShowcaseSettings,
) -> None:
    with TestClient(create_app(showcase_settings)) as client:
        html = client.get("/").text

    assert "overflow-x: hidden" in html
    assert "min-width: 0" in html
    assert "@media (max-width: 760px)" in html
    assert "grid-template-columns: minmax(0, 1fr)" in html
    assert "@media (max-width: 380px)" in html


def test_startup_rejects_missing_or_empty_database_without_creating_one(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.sqlite"
    settings = ShowcaseSettings(
        database_path=missing_path,
        working_directory=tmp_path / "work",
        deepseek_api_key="configured",
    )

    with pytest.raises(FileNotFoundError, match="Chinook database not found"):
        create_app(settings)
    assert not missing_path.exists()

    empty_path = tmp_path / "empty.sqlite"
    empty_path.touch()
    with pytest.raises(RuntimeError, match="database is empty"):
        create_app(
            ShowcaseSettings(
                database_path=empty_path,
                working_directory=tmp_path / "work",
                deepseek_api_key="configured",
            )
        )
    assert empty_path.stat().st_size == 0


def test_startup_rejects_missing_api_key(showcase_settings: ShowcaseSettings) -> None:
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY is required"):
        create_app(
            ShowcaseSettings(
                database_path=showcase_settings.database_path,
                working_directory=showcase_settings.working_directory,
                deepseek_api_key="",
            )
        )


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
