"""
ReaBot Daemon - Configuration

Loads configuration from environment variables (via .env file).
"""

import os
import sys
import tempfile
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    """Daemon configuration loaded from environment."""

    # OpenRouter
    openrouter_api_key: str
    model: str

    # Daemon network
    host: str
    port: int

    # Paths
    temp_dir: Path
    project_root: Path

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty if valid)."""
        errors = []
        if not self.openrouter_api_key or self.openrouter_api_key == "sk-or-v1-your-key-here":
            errors.append(
                "OPENROUTER_API_KEY is not set. "
                "Get a free key at https://openrouter.ai/keys and add it to .env"
            )
        if not self.model:
            errors.append("REABOT_MODEL is not set.")
        if not (1024 <= self.port <= 65535):
            errors.append(f"REABOT_PORT must be between 1024 and 65535, got {self.port}")
        return errors


def load_config() -> Config:
    """Load configuration from .env file and environment variables."""
    # Find project root (where .env lives)
    project_root = Path(__file__).parent.parent.resolve()

    # Load .env from project root
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Build temp directory
    temp_dir_str = os.environ.get("REABOT_TEMP_DIR", "")
    if temp_dir_str:
        temp_dir = Path(temp_dir_str)
    else:
        temp_dir = Path(tempfile.gettempdir()) / "reabot"

    # Ensure temp dir exists
    temp_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model=os.environ.get("REABOT_MODEL", "meta-llama/llama-3.1-70b-instruct:free"),
        host=os.environ.get("REABOT_HOST", "127.0.0.1"),
        port=int(os.environ.get("REABOT_PORT", "9876")),
        temp_dir=temp_dir,
        project_root=project_root,
    )
