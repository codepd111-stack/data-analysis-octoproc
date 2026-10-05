from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads backend/.env (run uvicorn from the backend/ folder)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str  # required: fail loudly if missing

    groq_api_key: str = ""
    groq_model_main: str = "openai/gpt-oss-120b"
    groq_model_fast: str = "openai/gpt-oss-20b"

    # "local" for development, "s3" for production (Supabase, R2, B2, ...)
    storage_backend: str = "local"
    upload_dir: str = "./data/uploads"
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_cache_dir: str = ""  # empty = a folder inside the system temp directory

    cors_origins: str = "http://localhost:3000"
    # True only when a reverse proxy (Render, nginx, ...) sits in front of the API and sets
    # X-Forwarded-For. Without a proxy the header is client-supplied and must be ignored.
    trust_proxy_headers: bool = False
    max_upload_mb: int = 50
    max_query_rows: int = 200
    duckdb_memory_limit: str = "1GB"
    include_sample_values: bool = True
    semantic_max_columns: int = 80

    # Sign-in. An empty ACCESS_CODE disables it (local development only!)
    access_code: str = ""
    auth_secret: str = ""
    auth_token_days: int = 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()