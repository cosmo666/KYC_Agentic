import os

def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example:11434")
    monkeypatch.setenv("CHAT_MODEL", "test-chat")
    monkeypatch.setenv("OCR_MODEL", "test-ocr")
    monkeypatch.setenv("EMBED_MODEL", "test-embed")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "test")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse:3000")

    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.chat_model == "test-chat"
    assert s.ollama_base_url == "http://example:11434"
    assert s.db_url.startswith("postgresql+asyncpg://u:p@")
