import os


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

    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")


settings = Settings()