"""Encrypted per-user DeepSeek credentials and request-time LLM routing."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from cryptography.fernet import Fernet, InvalidToken

from vanna.core.llm import (
    LlmMessage,
    LlmRequest,
    LlmResponse,
    LlmService,
    LlmStreamChunk,
)
from vanna.core.tool import ToolSchema
from vanna.core.user import User
from vanna.integrations.openai import OpenAILlmService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeepSeekLlmService(OpenAILlmService):
    """OpenAI-compatible DeepSeek client with reliable multi-step tool calls."""

    def _build_payload(self, request: LlmRequest) -> dict[str, Any]:
        payload = super()._build_payload(request)
        payload["extra_body"] = {"thinking": {"type": "disabled"}}
        return payload


class CredentialStore:
    """Store personal API keys encrypted at rest and expose effective settings."""

    def __init__(
        self,
        working_directory: Path,
        *,
        environment_api_key: str = "",
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        encryption_key: str | None = None,
    ) -> None:
        self.root = working_directory.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "data_sources.sqlite"
        self.key_path = self.root / "credential.key"
        self.environment_api_key = environment_api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._fernet = Fernet(self._resolve_key(encryption_key))
        self._initialize()

    def _resolve_key(self, explicit_key: str | None) -> bytes:
        configured = explicit_key or os.getenv("VANNA_CREDENTIAL_ENCRYPTION_KEY")
        if configured:
            return configured.strip().encode("ascii")
        if self.key_path.is_file():
            return self.key_path.read_bytes().strip()
        key = Fernet.generate_key()
        descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as key_file:
            key_file.write(key + b"\n")
        return key

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.registry_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_llm_credentials (
                    user_id TEXT PRIMARY KEY,
                    encrypted_api_key BLOB NOT NULL,
                    validated_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save_personal_key(self, user_id: str, api_key: str) -> None:
        normalized = api_key.strip()
        if not normalized:
            raise ValueError("API Key must not be empty")
        encrypted = self._fernet.encrypt(normalized.encode("utf-8"))
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_llm_credentials
                    (user_id, encrypted_api_key, validated_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    encrypted_api_key=excluded.encrypted_api_key,
                    validated_at=excluded.validated_at,
                    updated_at=excluded.updated_at
                """,
                (user_id, encrypted, now, now),
            )

    def delete_personal_key(self, user_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM user_llm_credentials WHERE user_id = ?", (user_id,)
            )
        return cursor.rowcount > 0

    def _personal_key(self, user_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT encrypted_api_key FROM user_llm_credentials WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        try:
            return self._fernet.decrypt(row["encrypted_api_key"]).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError(
                "The saved API Key cannot be decrypted; replace it in Personal Settings"
            ) from exc

    def effective_credentials(self, user_id: str) -> dict[str, str] | None:
        personal = self._personal_key(user_id)
        api_key = personal or self.environment_api_key
        if not api_key:
            return None
        return {
            "api_key": api_key,
            "base_url": self.base_url,
            "model": self.model,
            "source": "personal" if personal else "environment",
        }

    def public_status(self, user_id: str) -> dict[str, Any]:
        try:
            credentials = self.effective_credentials(user_id)
            error = None
        except RuntimeError as exc:
            credentials = None
            error = str(exc)
        return {
            "configured": credentials is not None,
            "source": credentials["source"] if credentials else "none",
            "provider": "DeepSeek",
            "base_url": self.base_url,
            "model": self.model,
            "error": error,
        }


class UserRoutedDeepSeekService(LlmService):
    """Resolve one DeepSeek client from the requesting user's effective credentials."""

    def __init__(self, credentials: CredentialStore) -> None:
        self.credentials = credentials
        self._clients: dict[tuple[str, str], DeepSeekLlmService] = {}

    def _client_for(self, user_id: str) -> DeepSeekLlmService:
        settings = self.credentials.effective_credentials(user_id)
        if not settings:
            raise RuntimeError(
                "DeepSeek API Key is not configured. Open Personal Settings before chatting."
            )
        fingerprint = hashlib.sha256(settings["api_key"].encode()).hexdigest()
        cache_key = (user_id, fingerprint)
        client = self._clients.get(cache_key)
        if client is None:
            client = DeepSeekLlmService(
                api_key=settings["api_key"],
                base_url=settings["base_url"],
                model=settings["model"],
            )
            self.invalidate_user(user_id)
            self._clients[cache_key] = client
        return client

    def invalidate_user(self, user_id: str) -> None:
        """Discard cached clients when one user's effective key changes."""
        for cache_key in tuple(self._clients):
            if cache_key[0] == user_id:
                self._clients.pop(cache_key, None)

    async def send_request(self, request: LlmRequest) -> LlmResponse:
        return await self._client_for(request.user.id).send_request(request)

    async def stream_request(
        self, request: LlmRequest
    ) -> AsyncGenerator[LlmStreamChunk, None]:
        async for chunk in self._client_for(request.user.id).stream_request(request):
            yield chunk

    async def validate_tools(self, tools: list[ToolSchema]) -> list[str]:
        return [
            f"Invalid tool name: {tool.name!r}"
            for tool in tools
            if not tool.name or len(tool.name) > 64
        ]


async def validate_deepseek_key(
    api_key: str, *, base_url: str, model: str, user_id: str
) -> None:
    """Make a minimal real request before accepting a personal API key."""
    service = DeepSeekLlmService(api_key=api_key, base_url=base_url, model=model)
    response = await service.send_request(
        LlmRequest(
            messages=[LlmMessage(role="user", content="Reply with OK only.")],
            user=User(id=user_id),
            max_tokens=8,
            temperature=0,
        )
    )
    if not response.content and not response.tool_calls:
        raise RuntimeError("DeepSeek returned an empty validation response")
