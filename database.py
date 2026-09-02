import aiosqlite
import json
import logging
from typing import Optional, Any
from config import Config

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Initialize database schema and tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS seen_models (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    created_at INTEGER,
                    raw_json TEXT,
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS drafts (
                    draft_id TEXT PRIMARY KEY,
                    model_id TEXT,
                    content TEXT,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Add image_url column if table was already created without it
            try:
                await db.execute("ALTER TABLE drafts ADD COLUMN image_url TEXT")
            except Exception:
                pass

            await db.commit()
        logger.info("Database initialized successfully at %s", self.db_path)

    async def get_all_seen_model_ids(self) -> set[str]:
        """Return a set of all model IDs already recorded."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id FROM seen_models") as cursor:
                rows = await cursor.fetchall()
                return {row[0] for row in rows}

    async def mark_model_seen(self, model: dict[str, Any]):
        """Save a newly discovered model to the database."""
        model_id = model.get("id")
        name = model.get("name", model_id)
        created_at = model.get("created", 0)
        raw_json = json.dumps(model)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO seen_models (id, name, created_at, raw_json)
                VALUES (?, ?, ?, ?)
                """,
                (model_id, name, created_at, raw_json),
            )
            await db.commit()

    async def mark_models_seen_bulk(self, models: list[dict[str, Any]]):
        """Bulk save models to the database (used on initial seed)."""
        async with aiosqlite.connect(self.db_path) as db:
            data = [
                (m.get("id"), m.get("name", m.get("id")), m.get("created", 0), json.dumps(m))
                for m in models
                if m.get("id")
            ]
            await db.executemany(
                """
                INSERT OR IGNORE INTO seen_models (id, name, created_at, raw_json)
                VALUES (?, ?, ?, ?)
                """,
                data,
            )
            await db.commit()

    async def get_total_seen_count(self) -> int:
        """Get the count of known models in DB."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM seen_models") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_recently_discovered(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most recently discovered models in the database."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, name, created_at, raw_json, discovered_at
                FROM seen_models
                ORDER BY discovered_at DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    try:
                        raw = json.loads(row[3])
                    except Exception:
                        raw = {}
                    results.append({
                        "id": row[0],
                        "name": row[1],
                        "created_at": row[2],
                        "raw": raw,
                        "discovered_at": row[4],
                    })
                return results

    # Settings operations
    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
            await db.commit()

    # Drafts operations
    async def save_draft(self, draft_id: str, model_id: str, content: str, image_url: Optional[str] = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO drafts (draft_id, model_id, content, image_url) VALUES (?, ?, ?, ?)",
                (draft_id, model_id, content, image_url),
            )
            await db.commit()

    async def get_draft(self, draft_id: str) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT draft_id, model_id, content, image_url FROM drafts WHERE draft_id = ?",
                (draft_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "draft_id": row[0],
                        "model_id": row[1],
                        "content": row[2],
                        "image_url": row[3],
                    }
                return None

    async def delete_draft(self, draft_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM drafts WHERE draft_id = ?", (draft_id,))
            await db.commit()
