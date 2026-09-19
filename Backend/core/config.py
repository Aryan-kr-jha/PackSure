from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "PackSure AI")
    environment: str = os.getenv("ENVIRONMENT", "development")
    supabase_url: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_key: str = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY",
        os.getenv("SUPABASE_ANON_KEY", ""),
    )
    upload_dir: Path = Path(
        os.getenv(
            "UPLOAD_DIR",
            str(Path(__file__).resolve().parents[1] / "uploads"),
        )
    )
    max_upload_bytes: int = int(
        os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
    )
    cors_origins: tuple[str, ...] = tuple(
        x.strip()
        for x in os.getenv("CORS_ORIGINS", "*").split(",")
        if x.strip()
    )
    compliance_tolerance: float = float(
        os.getenv("COMPLIANCE_PRICE_TOLERANCE", "0.05")
    )

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)


def reload_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "settings", "reload_settings"]
