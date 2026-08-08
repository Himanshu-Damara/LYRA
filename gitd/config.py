"""
Pydantic-settings configuration â€” reads from .env / environment variables.
Compatible with both pydantic v1 and v2.
"""

from pathlib import Path

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # pydantic v1 fallback â€” BaseSettings was in pydantic directly
    from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    # â”€â”€ Paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    base_dir: Path = Path(__file__).resolve().parent.parent
    db_path: Path = Path(__file__).resolve().parent.parent / "data" / "gitd.db"

    # â”€â”€ Server â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    host: str = "0.0.0.0"
    port: int = 5055

    # â”€â”€ Devices â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    default_device: str = ""  # ADB serial of primary phone (auto-detected if empty)

    # â”€â”€ iOS (feature-gated) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # iOS support (Appium/WebDriverAgent) ships dev-only for one release cycle:
    # OFF by default, so `ios:` device refs surface "not supported" errors and
    # iOS devices are excluded from discovery. Enable with GITD_ENABLE_IOS=1
    # (or ios_platform_enabled=true in .env). Flip the default once device
    # testing passes.
    ios_platform_enabled: bool = False

    # â”€â”€ Perception â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # After a UI action, append a before/after accessibility-tree diff to the
    # tool result so the model sees what its action changed (additive perception
    # aid). ON by default; set A11Y_DIFF_ENABLED=false to disable (kill-switch) â€”
    # the diff costs one extra UI-tree dump per UI action.
    a11y_diff_enabled: bool = True

    # â”€â”€ LLM â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Provider used when a session is created without an explicit one. Defaults
    # to claude-code (Claude subscription, no API key) â€” `android-agent login`
    # records this in .env.
    default_provider: str = "claude-code"

    # â”€â”€ API keys (optional, loaded from env) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    # Groq-compatible key used by the normal Grok chat provider.
    grok_api_key: str = ""
    grok_model: str = "llama-3.3-70b-versatile"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:5055/api/gmail/oauth/callback"

    # â”€â”€ Ollama â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ollama_base_url: str = "http://localhost:11434"

    # â”€â”€ vLLM (OpenAI-compatible, remote GPU) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Default assumes a chained tunnel:
    #   phone:8000 â†’ adb reverse â†’ mac:8000 â†’ ssh -L 8000:localhost:8000 <your-gpu-host>
    # On the Mac dev backend, the same URL works directly because the ssh
    # tunnel is already on `localhost`. Override via env GITD_VLLM_BASE_URL.
    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    vllm_api_key: str = "EMPTY"  # vLLM doesn't enforce auth; placeholder for OpenAI client

    class Config:
        # The launcher may run from android-agent while the shared workspace
        # .env lives one directory above it.
        env_file = (".env", "../.env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
