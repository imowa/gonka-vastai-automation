"""Environment loader utilities."""

from __future__ import annotations

import os
import importlib
import importlib.util
from pathlib import Path


def load_env(path: str = "config/.env") -> None:
    """Load environment variables from a .env file if python-dotenv is available."""
    env_path = Path(path)
    if env_path.exists():
        dotenv_spec = importlib.util.find_spec("dotenv")
        if dotenv_spec is not None:
            load_dotenv = importlib.import_module("dotenv").load_dotenv
            load_dotenv(env_path)
            return

        with env_path.open() as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if value and value[0] in {"'", '"'}:
                    value = value.strip("'\"")
                else:
                    value = value.split("#", 1)[0].strip()
                if not key:
                    continue
                existing = os.environ.get(key)
                if existing is None:
                    os.environ[key] = value
                    continue
                if "#" in existing and existing.split("#", 1)[0].strip() == value:
                    os.environ[key] = value
