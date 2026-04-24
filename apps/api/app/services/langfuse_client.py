from functools import lru_cache

from langfuse import Langfuse
from langfuse.decorators import langfuse_context, observe

from app.config import get_settings


@lru_cache
def get_langfuse() -> Langfuse | None:
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        return None
    return Langfuse(
        public_key=s.langfuse_public_key,
        secret_key=s.langfuse_secret_key,
        host=s.langfuse_host,
    )


__all__ = ["get_langfuse", "observe", "langfuse_context"]
