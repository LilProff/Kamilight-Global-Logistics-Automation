from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database: SQLite locally, Supabase Postgres in production
    # e.g. postgresql+psycopg://postgres:<pw>@db.<ref>.supabase.co:5432/postgres
    database_url: str = "sqlite:///./kgl.db"

    # Staff login (single admin for Phase 1)
    admin_email: str = "admin@kamilightglobal.com"
    admin_password: str = "change-me"
    jwt_secret: str = "dev-secret-change-me"
    jwt_hours: int = 12
    cors_origins: str = "http://localhost:5173"

    # WhatsApp Cloud API. Leave token empty to run in test mode (nothing is really sent).
    wa_token: str = ""
    wa_phone_number_id: str = ""
    wa_api_version: str = "v21.0"
    wa_verify_token: str = "kgl-verify"
    wa_app_secret: str = ""  # enables webhook signature checks when set

    # Email (optional)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Meta fees for Nigeria from 1 Oct 2026, in naira per delivered message
    wa_marketing_fee_ngn: float = 84.0
    wa_utility_fee_ngn: float = 14.0

    # Sending pace and lifecycle rules
    send_rate_per_second: float = 10.0
    dormant_after_days: int = 60
    vip_min_shipments: int = 5
    vip_min_spend_ngn: float = 5_000_000.0

    run_worker: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
