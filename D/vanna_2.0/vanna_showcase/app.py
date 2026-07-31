"""ASGI entry point for ``uvicorn vanna_showcase.app:app``."""

from .factory import create_app

app = create_app()
