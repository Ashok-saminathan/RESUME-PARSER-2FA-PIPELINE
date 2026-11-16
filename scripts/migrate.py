"""Apply SQL files from migrations/ in filename order, once each.

Usage: DATABASE_URL=postgresql+asyncpg://... python scripts/migrate.py
"""
import asyncio
import os
from pathlib import Path

import asyncpg

DEFAULT_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/onboarding"


async def main() -> None:
    url = os.getenv("DATABASE_URL", DEFAULT_URL).replace("postgresql+asyncpg://", "postgresql://")
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        for path in sorted(migrations_dir.glob("*.sql")):
            if path.name in applied:
                print(f"skip    {path.name}")
                continue
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", path.name)
            print(f"applied {path.name}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
