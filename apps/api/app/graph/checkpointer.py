from __future__ import annotations

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings


def _dsn() -> str:
    s = get_settings()
    # AsyncPostgresSaver expects a libpq-style DSN (psycopg), not asyncpg.
    return (
        f"postgresql://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{s.postgres_db}"
    )


@asynccontextmanager
async def open_checkpointer():
    async with AsyncPostgresSaver.from_conn_string(_dsn()) as saver:
        await saver.setup()  # creates checkpoint tables first time; idempotent after
        yield saver
