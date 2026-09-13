import os
from pathlib import Path
from typing import Any, List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-change_me_jwt_secret_min_32_chars"


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Report Studio VIP Pro"
    API_V1_STR: str = "/api/v1"
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"debug", "development", "dev"}:
                return True
        return value
    
    # Security
    JWT_SECRET: str = DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Storage Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
    STORAGE_LOCAL_ROOT: str = ""
    STORAGE_DIR: Path = BASE_DIR / "storage"
    UPLOAD_DIR: Path = STORAGE_DIR / "uploads"
    TEMPLATE_DIR: Path = STORAGE_DIR / "templates"
    EXPORT_DIR: Path = STORAGE_DIR / "exports"
    REPORTS_DIR: Path = STORAGE_DIR / "reports"
    ASSETS_DIR: Path = STORAGE_DIR / "assets"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3050",
        "http://127.0.0.1:3050",
        "http://localhost:8050",
        "http://127.0.0.1:8050",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",
    ]

    # Database (Default: Async SQLite for local dev, PostgreSQL for production)
    DATABASE_URL: str = f"sqlite+aiosqlite:///{Path(__file__).resolve().parent.parent.parent.parent / 'storage' / 'ai_report_studio.db'}"
    AUTO_MIGRATE_DATABASE: bool = True
    
    # AI Providers Configuration
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEFAULT_AI_PROVIDER: str = "gemini"  # gemini, openai, anthropic, ollama
    DEFAULT_AI_MODEL: str = "gemini-2.5-flash"
    AI_RUNTIME_MODE: str = "auto"  # auto, offline_demo, production
    
    # Search Providers Configuration
    SEARCH_PROVIDER: str = "tavily"  # tavily, brave, serpapi, duckduckgo
    TAVILY_API_KEY: str = ""
    BRAVE_SEARCH_API_KEY: str = ""
    SERPAPI_API_KEY: str = ""

    # Google OAuth Configuration
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3050/api/auth/callback/google"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def model_post_init(self, __context: Any) -> None:
        if self.STORAGE_LOCAL_ROOT:
            self.STORAGE_DIR = Path(self.STORAGE_LOCAL_ROOT)
            self.UPLOAD_DIR = self.STORAGE_DIR / "uploads"
            self.TEMPLATE_DIR = self.STORAGE_DIR / "templates"
            self.EXPORT_DIR = self.STORAGE_DIR / "exports"
            self.REPORTS_DIR = self.STORAGE_DIR / "reports"
            self.ASSETS_DIR = self.STORAGE_DIR / "assets"

    def init_storage(self):
        """Ensure all required storage directories exist."""
        for path in [self.STORAGE_DIR, self.UPLOAD_DIR, self.TEMPLATE_DIR, self.EXPORT_DIR, self.REPORTS_DIR, self.ASSETS_DIR]:
            path.mkdir(parents=True, exist_ok=True)

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in {"production", "prod"}

    @property
    def is_demo_mode(self) -> bool:
        return self.AI_RUNTIME_MODE.strip().lower() in {"offline_demo", "demo", "test"}

    @property
    def allow_ai_offline_fallback(self) -> bool:
        mode = self.AI_RUNTIME_MODE.strip().lower()
        if mode in {"offline_demo", "demo", "test"}:
            return True
        if mode == "production":
            return False
        return not self.is_production

    def validate_production_safety(self) -> List[str]:
        if not self.is_production:
            return []

        errors: List[str] = []
        jwt_secret = self.JWT_SECRET.strip()
        jwt_secret_lower = jwt_secret.lower()
        if jwt_secret == DEFAULT_JWT_SECRET or jwt_secret == "":
            errors.append("JWT_SECRET must be changed for production.")
        elif len(jwt_secret) < 32 or "change_me" in jwt_secret_lower or "placeholder" in jwt_secret_lower:
            errors.append("JWT_SECRET must be a strong non-placeholder value of at least 32 characters.")
        if "*" in self.CORS_ORIGINS:
            errors.append("CORS_ORIGINS must not contain '*' in production.")
        if self.DEBUG:
            errors.append("DEBUG must be false in production.")
        if self.AUTO_MIGRATE_DATABASE:
            errors.append(
                "AUTO_MIGRATE_DATABASE must be false in production; "
                "run the migration job before starting the API."
            )
        return errors

    def assert_production_safety(self) -> None:
        errors = self.validate_production_safety()
        if errors:
            raise RuntimeError("Unsafe production configuration: " + " ".join(errors))


settings = Settings()
settings.init_storage()
