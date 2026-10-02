from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me"
DEV_ADMIN_PASSWORD = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database: SQLite locally, Supabase Postgres in production
    # e.g. postgresql+psycopg://postgres:<pw>@db.<ref>.supabase.co:5432/postgres
    database_url: str = "sqlite:///./kgl.db"

    # First admin account. Created automatically when the users table is empty; after that, accounts
    # (and password changes) are managed inside the app and these two values are no longer used.
    admin_email: str = "admin@kamilightglobal.com"
    admin_password: str = DEV_ADMIN_PASSWORD
    admin_name: str = "Administrator"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_hours: int = 12
    cors_origins: str = "http://localhost:5173"
    enable_docs: bool = False  # /docs and /openapi.json stay off in production

    # Login protection: lock an email (or an address) out for a while after repeated wrong passwords
    login_max_failures: int = 5
    login_ip_max_failures: int = 20
    login_window_minutes: int = 15

    # WhatsApp Cloud API. Leave token empty to run in test mode (nothing is really sent).
    wa_token: str = ""
    wa_phone_number_id: str = ""
    wa_api_version: str = "v21.0"
    wa_verify_token: str = "kgl-verify"
    wa_app_secret: str = ""  # required for the webhook once wa_token is set

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

    # Automatic campaigns (win-back, quote follow-up, welcome) only run inside these local hours
    local_utc_offset_hours: int = 1  # Lagos = UTC+1
    automation_hours_start: int = 8
    automation_hours_end: int = 19
    automation_interval_seconds: int = 300

    run_worker: bool = True

    @property
    def is_production(self) -> bool:
        return not self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def assert_safe_to_run(settings: Settings) -> None:
    """Refuse to start a real (non-SQLite) deployment with development defaults: forgeable logins are worse than downtime."""
    if not settings.is_production:
        return
    if settings.jwt_secret == DEV_JWT_SECRET or len(settings.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET must be set to a random value of at least 32 characters in production.")
