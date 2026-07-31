"""Tests for encrypted, per-user DeepSeek credential handling."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from vanna_showcase.credentials import CredentialStore
from vanna_showcase.factory import ShowcaseSettings, create_app


def test_personal_key_is_encrypted_and_overrides_environment(tmp_path: Path) -> None:
    work = tmp_path / "work"
    personal_key = "personal-secret-that-must-never-appear"
    environment_key = "environment-fallback-secret"
    store = CredentialStore(work, environment_api_key=environment_key)

    assert store.public_status("user-1")["source"] == "environment"
    store.save_personal_key("user-1", personal_key)

    effective = store.effective_credentials("user-1")
    assert effective["api_key"] == personal_key
    assert effective["source"] == "personal"
    public = store.public_status("user-1")
    assert public["configured"] is True
    assert public["source"] == "personal"
    assert "api_key" not in public
    assert personal_key.encode() not in store.registry_path.read_bytes()
    assert personal_key.encode() not in store.key_path.read_bytes()

    assert store.delete_personal_key("user-1") is True
    fallback = store.effective_credentials("user-1")
    assert fallback["api_key"] == environment_key
    assert fallback["source"] == "environment"


@pytest.mark.asyncio
async def test_api_validates_before_saving_and_never_echoes_key(tmp_path: Path) -> None:
    secret = "validated-personal-secret"
    app = create_app(
        ShowcaseSettings(
            database_path=tmp_path / "missing.sqlite",
            working_directory=tmp_path / "work",
            deepseek_api_key="",
        )
    )
    validation_calls = []

    async def validator(candidate: str) -> None:
        assert app.state.credentials.public_status("local-demo")["source"] == "none"
        validation_calls.append(candidate)

    app.state.credential_validator = validator
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        saved = await client.put("/api/settings/llm", json={"api_key": secret})
        status = await client.get("/api/settings/llm")

    assert saved.status_code == 200
    assert validation_calls == [secret]
    assert saved.json()["source"] == "personal"
    assert status.json()["source"] == "personal"
    assert secret not in saved.text
    assert secret not in status.text
    assert secret.encode() not in app.state.credentials.registry_path.read_bytes()


@pytest.mark.asyncio
async def test_failed_validation_does_not_replace_existing_key(tmp_path: Path) -> None:
    app = create_app(
        ShowcaseSettings(
            database_path=tmp_path / "missing.sqlite",
            working_directory=tmp_path / "work",
            deepseek_api_key="server-fallback",
        )
    )
    rejected = "rejected-secret"

    async def validator(_: str) -> None:
        raise RuntimeError(f"provider rejected {rejected}")

    app.state.credential_validator = validator
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put("/api/settings/llm", json={"api_key": rejected})
        status = await client.get("/api/settings/llm")

    assert response.status_code == 400
    assert rejected not in response.text
    assert "[REDACTED]" in response.text
    assert status.json()["source"] == "environment"


@pytest.mark.asyncio
async def test_delete_personal_key_falls_back_to_environment(tmp_path: Path) -> None:
    app = create_app(
        ShowcaseSettings(
            database_path=tmp_path / "missing.sqlite",
            working_directory=tmp_path / "work",
            deepseek_api_key="server-fallback",
        )
    )

    async def validator(_: str) -> None:
        return None

    app.state.credential_validator = validator
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.put("/api/settings/llm", json={"api_key": "personal-key"})
        deleted = await client.delete("/api/settings/llm")

    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.json()["llm"]["source"] == "environment"
