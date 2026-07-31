"""Tests for manual import, switching, sample installation, and physical deletion."""

from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path

import httpx
import pytest

from vanna.core.tool import ToolCall, ToolContext
from vanna.core.user import User
from vanna_showcase.factory import EXPECTED_CHINOOK_TABLES, ShowcaseSettings, create_app


def _create_chinook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        for table in EXPECTED_CHINOOK_TABLES:
            connection.execute(f'CREATE TABLE "{table}" (id INTEGER)')


def _chinook_payload(tmp_path: Path) -> bytes:
    database = tmp_path / "sample-source.sqlite"
    _create_chinook(database)
    return database.read_bytes()


def test_upload_form_keeps_element_reference_across_await() -> None:
    page = (
        Path(__file__).parents[1] / "vanna_showcase" / "data_sources.html"
    ).read_text()
    assert "const formElement = event.currentTarget" in page
    assert "formElement.reset()" in page
    assert "event.currentTarget.reset()" not in page


@pytest.mark.asyncio
async def test_manual_csv_import_schema_and_conversation_switch(tmp_path: Path) -> None:
    app = create_app(
        ShowcaseSettings(
            database_path=tmp_path / "missing.sqlite",
            working_directory=tmp_path / "work",
            deepseek_api_key="test-key",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/data-sources/import",
            data={"source_name": "制造业分析库"},
            files=[
                (
                    "files",
                    (
                        "mes_process_output.csv",
                        b"output_id,good_qty\nOUT-1,12\n",
                        "text/csv",
                    ),
                )
            ],
        )
        assert response.status_code == 200
        source = response.json()
        assert source["kind"] == "duckdb"
        assert "database_path" not in source

        schema = await client.get(f"/api/data-sources/{source['id']}/schema")
        assert schema.status_code == 200
        assert schema.json()["schema"]["mes_process_output"]["row_count"] == 1

        switched = await client.post(
            "/api/conversations/conversation-1/data-source",
            json={"data_source_id": source["id"]},
        )
        assert switched.status_code == 200
        assert (await client.get("/api/readiness")).json()["chat_ready"] is True

    agent = app.state.vanna_agent
    result = await agent.tool_registry.execute(
        ToolCall(
            id="query-1",
            name="run_sql",
            arguments={"sql": "SELECT * FROM mes_process_output"},
        ),
        ToolContext(
            user=User(id="local-demo", group_memberships=["user", "admin"]),
            conversation_id="conversation-1",
            request_id="request-1",
            agent_memory=agent.agent_memory,
        ),
    )
    assert result.success is True
    assert result.metadata["row_count"] == 1


@pytest.mark.asyncio
async def test_zip_import_rejects_path_traversal(tmp_path: Path) -> None:
    app = create_app(
        ShowcaseSettings(
            database_path=tmp_path / "missing.sqlite",
            working_directory=tmp_path / "work",
            deepseek_api_key="test-key",
        )
    )
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escape.csv", "id\n1\n")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/data-sources/import",
            data={"source_name": "bad"},
            files=[("files", ("bad.zip", payload.getvalue(), "application/zip"))],
        )
    assert response.status_code == 400
    assert "unsafe" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_delete_removes_uploaded_files_and_resets_binding(
    tmp_path: Path,
) -> None:
    chinook = tmp_path / "Chinook.sqlite"
    _create_chinook(chinook)
    app = create_app(
        ShowcaseSettings(
            database_path=chinook,
            working_directory=tmp_path / "work",
            deepseek_api_key="test-key",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        imported = await client.post(
            "/api/data-sources/import",
            data={"source_name": "temporary"},
            files=[("files", ("items.csv", b"id,name\n1,one\n", "text/csv"))],
        )
        source_id = imported.json()["id"]
        internal = app.state.data_sources.get_source(source_id)
        database_path = Path(internal["database_path"])
        await client.post(
            "/api/conversations/to-reset/data-source",
            json={"data_source_id": source_id},
        )

        forbidden = await client.delete(
            f"/api/data-sources/{source_id}", headers={"x-demo-role": "user"}
        )
        assert forbidden.status_code == 403
        assert database_path.is_file()

        deleted = await client.delete(f"/api/data-sources/{source_id}")
        assert deleted.status_code == 200
        assert deleted.json()["physical_deleted"] is True
        assert deleted.json()["dataset_directory_deleted"] is True
        assert deleted.json()["conversation_fallback"]["id"] == "chinook"
        assert not database_path.parent.exists()

        conversation = await client.get("/api/conversations/to-reset/data-source")
        assert conversation.json()["data_source"]["id"] == "chinook"
        assert "database_path" not in conversation.json()["data_source"]


@pytest.mark.asyncio
async def test_existing_root_chinook_is_discovered_and_physically_deletable(
    tmp_path: Path,
) -> None:
    chinook = tmp_path / "Chinook.sqlite"
    _create_chinook(chinook)
    app = create_app(
        ShowcaseSettings(
            database_path=chinook,
            working_directory=tmp_path / "work",
            deepseek_api_key="",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        listed = (await client.get("/api/data-sources")).json()
        assert [item["id"] for item in listed] == ["chinook"]

        deleted = await client.delete("/api/data-sources/chinook")
        assert deleted.status_code == 200
        body = deleted.json()
        assert body["physical_deleted"] is True
        assert body["dataset_directory_deleted"] is False
        assert body["conversation_fallback"] is None

    assert not chinook.exists()
    assert tmp_path.exists()


@pytest.mark.asyncio
async def test_chinook_install_is_idempotent_deleteable_and_reinstallable(
    tmp_path: Path,
) -> None:
    payload = _chinook_payload(tmp_path)
    app = create_app(
        ShowcaseSettings(
            database_path=tmp_path / "missing.sqlite",
            working_directory=tmp_path / "work",
            deepseek_api_key="",
        )
    )
    manager = app.state.data_sources
    app.state.chinook_installer = lambda: manager.install_chinook_bytes(payload)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/api/sample-data/chinook")
        second = await client.post("/api/sample-data/chinook")
        assert first.status_code == second.status_code == 200
        assert first.json()["source"]["id"] == "chinook"
        assert second.json()["source"]["id"] == "chinook"
        installed_path = Path(manager.get_source("chinook")["database_path"])
        assert installed_path.is_file()

        deleted = await client.delete("/api/data-sources/chinook")
        assert deleted.json()["physical_deleted"] is True
        assert not installed_path.exists()
        assert manager.get_source("chinook") is None

        reinstalled = await client.post("/api/sample-data/chinook")
        assert reinstalled.status_code == 200
        assert Path(manager.get_source("chinook")["database_path"]).is_file()


@pytest.mark.asyncio
async def test_invalid_chinook_download_leaves_no_partial_database(
    tmp_path: Path,
) -> None:
    app = create_app(
        ShowcaseSettings(
            database_path=tmp_path / "missing.sqlite",
            working_directory=tmp_path / "work",
            deepseek_api_key="",
        )
    )
    manager = app.state.data_sources
    app.state.chinook_installer = lambda: manager.install_chinook_bytes(b"bad")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/sample-data/chinook")

    assert response.status_code == 400
    assert manager.get_source("chinook") is None
    assert not manager.managed_chinook_path.exists()
    assert not manager.managed_chinook_path.with_suffix(".part").exists()
