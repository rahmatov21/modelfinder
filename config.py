import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # Telegram Bot Token
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    # Allowed Admin User IDs (supports single ID e.g. "12345678" or comma separated "123,456")
    _admin_ids_str: str = os.getenv("ADMIN_USER_ID", "").strip()
    ADMIN_USER_IDS: list[int] = [
        int(x.strip()) for x in _admin_ids_str.split(",") if x.strip().isdigit()
    ]

    # Target Telegram Channel (e.g. "@my_channel" or "-1001234567890")
    TELEGRAM_CHANNEL_ID: str = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()

    # OpenRouter API Key
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()

    # OpenRouter Model to use for generating and refining posts (100% free by default)
    DEFAULT_AI_MODEL: str = os.getenv("DEFAULT_AI_MODEL", "openrouter/free").strip()

    # Background polling interval in minutes
    CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "15"))

    # Auto-post to channel when new model is found:
    # True = directly publish to channel; False = send interactive draft to admin first
    AUTO_POST_TO_CHANNEL: bool = os.getenv("AUTO_POST_TO_CHANNEL", "false").lower() in ("1", "true", "yes")

    # SQLite Database path
    DB_PATH: str = str(BASE_DIR / "data.db")

    # OpenRouter API Endpoints
    OPENROUTER_MODELS_URL: str = "https://openrouter.ai/api/v1/models"
    OPENROUTER_CHAT_URL: str = "https://openrouter.ai/api/v1/chat/completions"

    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        """Check if a given user_id is authorized as an admin."""
        if not cls.ADMIN_USER_IDS:
            return False
        return user_id in cls.ADMIN_USER_IDS

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration values and return missing list."""
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.ADMIN_USER_IDS:
            missing.append("ADMIN_USER_ID")
        return missing
