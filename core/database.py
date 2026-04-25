import asyncpg
import asyncio
from core.config import settings

DB_CONFIG = {
    "user": settings.DB_USER,
    "password": settings.DB_PASSWORD,
    "database": settings.DB_NAME,
    "host": settings.DB_HOST,
    "port": settings.DB_PORT
}

pool = None

async def init_pools():
    global pool
    pool = await asyncpg.create_pool(**DB_CONFIG)
    await init_db()

async def init_db():
    async with pool.acquire() as conn:
        # Основная структура
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                user_name TEXT,
                user_first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS films (
                code INTEGER PRIMARY KEY,
                title TEXT,
                description TEXT,
                image_url TEXT
            );
            
            CREATE TABLE IF NOT EXISTS likedFilms (
                userId BIGINT,
                code INTEGER,
                PRIMARY KEY (userId, code),
                FOREIGN KEY (userId) REFERENCES users(user_id),
                FOREIGN KEY (code) REFERENCES films(code)
            );
            
            CREATE TABLE IF NOT EXISTS sponsores (
                id SERIAL PRIMARY KEY,
                channelName TEXT,
                channelUrl_pub TEXT,
                channelUrl_private TEXT,
                allowSkip BOOLEAN DEFAULT false
            );
        """)
        
        # Миграция: добавляем created_at если таблица уже была создана без него
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass

# === Users ===

async def add_user(user_id: int, user_name: str, first_name: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, user_name, user_first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, user_name, first_name)

async def get_user_count() -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")

async def get_all_users():
    async with pool.acquire() as conn:
        # Пытаемся сортировать по дате, если не выйдет (вдруг база совсем старая) - просто берем всех
        try:
            return await conn.fetch("SELECT * FROM users ORDER BY created_at DESC")
        except Exception:
            return await conn.fetch("SELECT * FROM users")

# === Films ===

async def add_movie(code: int, title: str, description: str, image_url: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO films (code, title, description, image_url)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (code) DO UPDATE 
            SET title = $2, description = $3, image_url = $4
        """, code, title, description, image_url)

async def delete_movie(code: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM films WHERE code = $1", code)

async def get_movie_by_code(code: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM films WHERE code = $1", code)

async def get_all_films():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM films ORDER BY code DESC")

async def get_all_films_count() -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM films")

async def get_free_code() -> int:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT code FROM films WHERE code >= 1000 AND code <= 9999 ORDER BY code")
        used_codes = {row['code'] for row in rows}
        for code in range(1000, 10000):
            if code not in used_codes:
                return code
        return None

# === Liked Films ===

async def get_liked_movies(user_id: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT code FROM likedFilms WHERE userId = $1", user_id)
        return [row['code'] for row in rows]

async def add_liked_movie(user_id: int, movie_code: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO likedFilms (userId, code)
            VALUES ($1, $2)
            ON CONFLICT (userId, code) DO NOTHING
        """, user_id, movie_code)

async def remove_liked_movie(user_id: int, movie_code: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM likedFilms WHERE userId = $1 AND code = $2", user_id, movie_code)

# === Sponsors ===

async def get_sponsors(only_required: bool = True):
    async with pool.acquire() as conn:
        if only_required:
            return await conn.fetch("SELECT * FROM sponsores WHERE allowSkip = false")
        return await conn.fetch("SELECT * FROM sponsores")

async def add_sponsor(name: str, url_pub: str, url_priv: str = None, allow_skip: bool = False):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO sponsores (channelName, channelUrl_pub, channelUrl_private, allowSkip)
            VALUES ($1, $2, $3, $4)
        """, name, url_pub, url_priv, allow_skip)

async def delete_sponsor(sponsor_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sponsores WHERE id = $1", sponsor_id)

async def update_sponsor(sponsor_id: int, name: str, url_pub: str, url_priv: str, allow_skip: bool):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE sponsores 
            SET channelName = $2, channelUrl_pub = $3, channelUrl_private = $4, allowSkip = $5
            WHERE id = $1
        """, sponsor_id, name, url_pub, url_priv, allow_skip)

# === Statistics ===

async def get_statistics():
    async with pool.acquire() as conn:
        u_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        f_count = await conn.fetchval("SELECT COUNT(*) FROM films")
        s_count = await conn.fetchval("SELECT COUNT(*) FROM sponsores")
        return {
            "users_count": u_count,
            "films_count": f_count,
            "sponsors_count": s_count
        }