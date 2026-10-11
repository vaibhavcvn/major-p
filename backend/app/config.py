import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Ambulance Response Platform"
    API_V1_STR: str = "/api/v1"

    # SECRET_KEY must be set in the environment (.env file).
    # There is NO insecure fallback — a missing key raises a startup error.
    SECRET_KEY: str

    ALGORITHM: str = "HS256"
    # M-7: Token lifetime is configurable via environment variable.
    # Default is 1440 minutes (24 hours) — safer than the old 7-day value.
    # Override in .env: ACCESS_TOKEN_EXPIRE_MINUTES=480
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # DB Configuration: default PostgreSQL, fallback to SQLite for portable dev/testing
    DATABASE_URL: str = "sqlite:///./smart_ambulance.db"

    OSRM_BASE_URL: str = "https://router.project-osrm.org"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"

    ML_MODEL_PATH: str = os.path.join(os.path.dirname(__file__), "..", "ml_model.joblib")

    # CORS — comma-separated list of allowed frontend origins.
    # Example: ALLOWED_ORIGINS=http://localhost:3000,https://yourapp.com
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Traffic proximity threshold — how close (km) an ambulance must be to its
    # destination before a one-time proximity alert is sent to traffic.
    TRAFFIC_PROXIMITY_KM: float = 2.0

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
