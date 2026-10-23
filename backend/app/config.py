import os

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env (if it exists) into environment variables


class Settings:
    """All configuration comes from environment variables (12-factor style)."""

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./disputes.db")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # OpenSearch is optional: if not set, search falls back to the database.
    OPENSEARCH_URL: str | None = os.getenv("OPENSEARCH_URL")
    OPENSEARCH_INDEX: str = os.getenv("OPENSEARCH_INDEX", "disputes")

    # Business rules for routing to a human reviewer
    HUMAN_REVIEW_AMOUNT: float = float(os.getenv("HUMAN_REVIEW_AMOUNT", "1000"))
    HUMAN_REVIEW_FRAUD_SCORE: int = int(os.getenv("HUMAN_REVIEW_FRAUD_SCORE", "70"))
    MIN_AUTO_CONFIDENCE: float = float(os.getenv("MIN_AUTO_CONFIDENCE", "0.7"))

    # Authentication (JWT). ALWAYS set a long random JWT_SECRET outside local development.
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-only-secret-change-me-in-production-0123456789")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
    MAX_FAILED_LOGINS: int = int(os.getenv("MAX_FAILED_LOGINS", "5"))
    LOCKOUT_MINUTES: int = int(os.getenv("LOCKOUT_MINUTES", "15"))
    DEMO_PASSWORD: str = os.getenv("DEMO_PASSWORD", "Demo!2026")  # password for the seeded demo users

    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")


settings = Settings()