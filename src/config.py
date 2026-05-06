"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    """Centralized runtime settings for CLI and web workflows."""

    github_token: str
    ollama_host: str
    ollama_model: str
    gemini_api_key: str
    gemini_model: str
    app_base_path: str

    @classmethod
    def from_env(cls, *, load_dotenv_file: bool = True) -> "AppConfig":
        if load_dotenv_file:
            load_dotenv()

        return cls(
            github_token=os.getenv("GITHUB_TOKEN", ""),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            app_base_path=os.getenv("APP_BASE_PATH", ""),
        )
