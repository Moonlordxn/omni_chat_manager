import aiosqlite
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)


# ============================================================
#                    ИНИЦИАЛИЗАЦИЯ БАЗЫ
# ============================================================

async def init_db():
    """Создаёт все таблицы, если их нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Пользователи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT,
                full_name    TEXT,
                first_seen   DATETIME DEFAULT CURRENT_TIMESTAMP,
                omni_coins   INTEGER DEFAULT 0
            )
        """)

        # Чаты
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id      INTEGER PRIMARY KEY,
                title        TEXT,
                owner_id     INTEGER,
                settings     TEXT DEFAULT '{}',
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Администраторы (ранги)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                chat_id      INTEGER,
                user_id      INTEGER,
                rank         INTEGER NOT NULL,
                appointed_by INTEGER,
                appointed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # Варны
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id      INTEGER,
                user_id      INTEGER,
                admin_id     INTEGER,
                reason       TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Муты
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                chat_id      INTEGER,
                user_id      INTEGER,
                admin_id     INTEGER,
                until_date   DATETIME,
                reason       TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # Баны
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                chat_id      INTEGER,
                user_id      INTEGER,
                admin_id     INTEGER,
                reason       TEXT,
                banned_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        await db.commit()

    logger.info("✅ База данных инициализирована")


# ============================================================
#                    ПОЛЬЗОВАТЕЛИ
# ============================================================

async def upsert_user(user_id: int, username: str | None, full_name: str):
    """Добавляет или обновляет пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
            """,
            (user_id, username, full_name)
        )
        await db.commit()


async def get_user(user_id: int):
    """Возвращает данные пользователя или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, full_name, omni_coins FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            return await cursor.fetchone()


# ============================================================
#                       ЧАТЫ
# ============================================================

async def upsert_chat(chat_id: int, title: str, owner_id: int | None = None):
    """Добавляет или обновляет чат."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO chats (chat_id, title, owner_id)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                owner_id = COALESCE(excluded.owner_id, chats.owner_id)
            """,
            (chat_id, title, owner_id)
        )
        await db.commit()


# ============================================================
#                       РАНГИ
# ============================================================

async def get_admin_rank(chat_id: int, user_id: int) -> int | None:
    """Возвращает ранг админа или None, если он не назначен."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT rank FROM admins WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_admin_rank(chat_id: int, user_id: int, rank: int, appointed_by: int):
    """Назначает или меняет ранг."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO admins (chat_id, user_id, rank, appointed_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                rank = excluded.rank,
                appointed_by = excluded.appointed_by,
                appointed_at = CURRENT_TIMESTAMP
            """,
            (chat_id, user_id, rank, appointed_by)
        )
        await db.commit()


async def remove_admin(chat_id: int, user_id: int):
    """Снимает админа."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM admins WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()


async def list_admins(chat_id: int) -> list[tuple]:
    """Возвращает список (user_id, rank) для чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, rank FROM admins WHERE chat_id = ? ORDER BY rank DESC",
            (chat_id,)
        ) as cursor:
            return await cursor.fetchall()


# ============================================================
#                       ВАРНЫ
# ============================================================

async def add_warn(chat_id: int, user_id: int, admin_id: int, reason: str = "") -> int:
    """Добавляет варн и возвращает новое количество."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warns (chat_id, user_id, admin_id, reason) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, admin_id, reason)
        )
        await db.commit()

        async with db.execute(
            "SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_warns_count(chat_id: int, user_id: int) -> int:
    """Возвращает количество варнов."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def remove_last_warn(chat_id: int, user_id: int) -> bool:
    """Снимает последний варн. True, если сняли."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id FROM warns
            WHERE chat_id = ? AND user_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False

        await db.execute("DELETE FROM warns WHERE id = ?", (row[0],))
        await db.commit()
        return True


async def clear_warns(chat_id: int, user_id: int):
    """Удаляет все варны пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warns WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()


# ============================================================
#                       МУТЫ
# ============================================================

async def set_mute(chat_id: int, user_id: int, admin_id: int, until_date: str, reason: str = ""):
    """Сохраняет или обновляет мут."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO mutes (chat_id, user_id, admin_id, until_date, reason)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                until_date = excluded.until_date,
                admin_id = excluded.admin_id,
                reason = excluded.reason
            """,
            (chat_id, user_id, admin_id, until_date, reason)
        )
        await db.commit()


async def remove_mute(chat_id: int, user_id: int):
    """Удаляет запись о муте."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM mutes WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()


async def get_mute(chat_id: int, user_id: int):
    """Возвращает запись о муте или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT until_date FROM mutes WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            return await cursor.fetchone()


# ============================================================
#                       БАНЫ
# ============================================================

async def add_ban(chat_id: int, user_id: int, admin_id: int, reason: str = ""):
    """Сохраняет бан."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO bans (chat_id, user_id, admin_id, reason)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                admin_id = excluded.admin_id,
                reason = excluded.reason,
                banned_at = CURRENT_TIMESTAMP
            """,
            (chat_id, user_id, admin_id, reason)
        )
        await db.commit()


async def remove_ban(chat_id: int, user_id: int):
    """Удаляет запись о бане."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM bans WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()
