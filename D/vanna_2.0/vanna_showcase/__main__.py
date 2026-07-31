"""Run the showcase with ``python -m vanna_showcase``."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "vanna_showcase.app:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
