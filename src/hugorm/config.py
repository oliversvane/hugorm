from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HUGORM_", extra="ignore")

    asr_model: str = Field(
        "small",
        description=(
            "faster-whisper model size or HF id. Recommended: 'large-v3-turbo' "
            "(fast and accurate) or 'small' (CPU-friendly multilingual). "
            "'tiny'/'base' trade quality for latency."
        ),
    )
    asr_beam_size: int = Field(5, description="Whisper beam size. 1 = fastest, 5 = default quality.")
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    device: str = "auto"
    compute_type: str = "auto"
    hf_token: str | None = None
    default_language: str | None = None

    window_s: float = 2.5
    overlap_s: float = 0.25
    diarization_interval_s: float = 5.0
    diarization_window_s: float = 30.0
    finalize_lag_s: float = 10.0
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None

    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    openai_api_key: str | None = None
    refinement_enabled: bool = True

    data_dir: str = "./data"

    supabase_jwt_secret: str | None = None
    supabase_jwt_audience: str = "authenticated"
    database_url: str | None = None
    gotrue_url: str = "http://localhost:9999"
    cors_origins: str = "http://localhost:3000"

    storage_backend: str = Field(
        "supabase",
        description="'supabase' (use storage-api) or 'local' (write to data/storage).",
    )
    storage_url: str = "http://localhost:5000"
    storage_service_key: str | None = None
    storage_bucket: str = "documents"
    storage_local_root: str = "./data/storage"

    frontend_url: str = "http://localhost:3000"
    invitation_expires_days: int = 7

    stripe_secret_key: str | None = None
    stripe_price_id: str | None = Field(
        None,
        description="Stripe Price ID for the Pro plan (e.g. price_1ABC...).",
    )
