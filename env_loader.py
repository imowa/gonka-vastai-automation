"""Environment loader utilities."""

from __future__ import annotations

from pathlib import Path


def load_env(path: str = "config/.env") -> None:
    """Load environment variables from a .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return

    env_path = Path(path)
    if env_path.exists():
        load_dotenv(env_path)
