from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://kbaas:kbaas@localhost:5432/kbaas"

    # S3 — when running on AWS with IAM roles, endpoint_url and keys can be empty
    s3_endpoint_url: str = ""  # Empty = use real AWS S3
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_name: str = "kbaas-docs"
    s3_region: str = "us-east-1"

    anthropic_api_key: str = ""

    jwt_secret_key: str = ""  # MUST be set via env var — app will fail on first auth if empty
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440

    cors_origins: str = "http://localhost:3000"  # Comma-separated

    model_config = {"env_file": str(_ENV_FILE), "extra": "ignore"}


settings = Settings()
