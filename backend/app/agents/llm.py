from langchain_openai import ChatOpenAI

from app.config import settings


def get_llm():
    """Single place to create the model, so tests can replace it with a fake one."""
    return ChatOpenAI(model=settings.OPENAI_MODEL, temperature=0, api_key=settings.OPENAI_API_KEY)